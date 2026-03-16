# Executor Directive: USASpending.gov Contract Transaction Ingestion

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** USASpending.gov is the US government's public database of federal contract awards. We are adding it as a second bulk data source for data-engine-x, alongside the SAM.gov entity registration data already in production (867K entities in `entities.sam_gov_entities`). The join key between the two datasets is UEI — `recipient_uei` in USASpending maps to `unique_entity_id` in SAM.gov.

The USASpending bulk download is a ZIP containing one or more CSV files with a header row. The FY2026 full download has **297 columns** and **1,340,862 rows** across 2 CSV files. Delta files have **299 columns** (297 + 2 prepended delta-only columns). Complete schema documentation is in `docs/USASPENDING_EXTRACT_SCHEMA_COMPREHENSION.md`.

This directive follows the **exact same architecture** as the SAM.gov ingestion: column map → migration → bulk COPY persistence → CSV parser → ingest service → internal endpoint → tests. The SAM.gov implementation is your primary reference for code patterns, naming conventions, and structural decisions.

This is a **new, independent data source** — it is not an extension of SAM.gov work. USASpending gets its own modules, its own table, its own parser.

---

## Reference Documents (Read Before Starting)

**Must read — USASpending data contract:**
- `docs/USASPENDING_EXTRACT_SCHEMA_COMPREHENSION.md` — Complete field map (297 columns), data types, delimiter rules, file format, multi-file splits, delta handling, boolean formats, semicolon-delimited fields, dollar amount semantics, action type codes. **This is the authoritative reference for all columns, their positions, types, and behavior.**

**Must read — SAM.gov implementation (your code pattern reference):**
- `app/services/sam_gov_column_map.py` — Column map structure: `SAM_GOV_COLUMNS` list of dicts, derived exports, self-test
- `app/services/sam_gov_common.py` — Bulk COPY utilities: connection pool, source context TypedDict, row parser, row builder, upsert function with temp table + COPY + merge pattern, phase timing
- `app/services/sam_gov_extract_ingest.py` — Ingest orchestrator: chunked file reading, BOF skip, chunk persistence, error handling
- `supabase/migrations/030_sam_gov_entities.sql` — Migration pattern: `entities` schema, TEXT columns, metadata columns, indexes, trigger, RLS
- `tests/test_sam_gov_ingest.py` — Test structure: column map tests, parser tests, row builder tests, ingest service tests

**Must read — existing bulk persistence pattern:**
- `app/services/fmcsa_daily_diff_common.py` — The original COPY-based bulk write utilities that SAM.gov was modeled on

---

## USASpending CSV Format Summary

| Property | Value |
|---|---|
| File type | CSV (comma-delimited), delivered in ZIP |
| Delimiter | Comma (`,`) with double-quote (`"`) quoting (RFC 4180) |
| Header row | **Yes** — first line is column names |
| Columns (full) | **297** |
| Columns (delta) | **299** (2 prepended: `correction_delete_ind`, `agency_id`) |
| Encoding | ASCII |
| Multi-file | ZIP may contain multiple CSVs, split at 1,000,000 rows per file |
| Primary key | `contract_transaction_unique_key` (column 1) — unique per transaction row |
| Award grouping key | `contract_award_unique_key` (column 2) — groups all transactions on one award |

**Delta columns are PREPENDED, not appended.** In delta files, columns 1-2 are delta-specific, and columns 3-299 correspond to full file columns 1-297.

**Boolean flags:** 86 columns use lowercase `t`/`f` format (not TRUE/FALSE, not Y/N).

**Dollar amounts:** Decimal with 2 places, can be negative (deobligations), empty string when no value.

**Semicolon-delimited fields:** Columns 41-44 (treasury accounts, federal accounts, object classes, program activities) and column 17 (DEFC codes) contain semicolon-separated lists within a single CSV cell.

---

## Table Design

### Table name: `usaspending_contracts`

### Schema: `entities`

### Design principles

1. **Store all 297 columns as TEXT.** Same strategy as SAM.gov — keeps ingestion lossless. Type casting happens at query time.

2. **Column naming:** The CSV header names are already snake_case. Use them directly as database column names. Exception: column names starting with a digit need a prefix (e.g., `1862_land_grant_college` → `col_1862_land_grant_college`).

3. **Delta-only columns included:** Add `correction_delete_ind` and `agency_id` as nullable TEXT columns. These are populated only when ingesting delta files.

4. **Composite unique key:** `(extract_date, contract_transaction_unique_key)` — supports loading multiple snapshots side by side.

5. **Extract metadata columns** (same pattern as SAM.gov):

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID PRIMARY KEY DEFAULT gen_random_uuid()` | Surrogate PK |
| `extract_date` | `DATE NOT NULL` | Date of the extract file |
| `extract_type` | `TEXT NOT NULL` | `FULL` or `DELTA` |
| `source_filename` | `TEXT NOT NULL` | Original CSV filename from the ZIP |
| `source_provider` | `TEXT NOT NULL DEFAULT 'usaspending'` | Provider attribution |
| `ingested_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | When this row was written |
| `row_position` | `INTEGER NOT NULL` | 1-based row number in the source file |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |

6. **Indexes:**
   - `(extract_date, contract_transaction_unique_key)` — unique constraint provides this
   - `(contract_transaction_unique_key)` — lookup across snapshots
   - `(contract_award_unique_key)` — award grouping queries
   - `(recipient_uei)` — SAM.gov join
   - `(action_date)` — time-series queries
   - `(awarding_agency_code)` — agency filtering
   - `(naics_code)` — industry filtering
   - `(extract_date DESC)` — find latest snapshot

---

## Deliverables

### Deliverable 1: Column Name Mapping Module

Create `app/services/usaspending_column_map.py`.

Follow the same structure as `sam_gov_column_map.py`:

1. Export `USASPENDING_COLUMNS: list[dict]` — ordered list of all 297 column definitions. Each dict: `position` (int, 1-based), `csv_header_name` (str, original CSV header), `db_column_name` (str, Postgres-safe name), `description` (str, brief).

2. **Column name conversion rules:**
   - Most CSV headers are already valid snake_case — use them directly
   - Column names starting with a digit: prefix with `col_` (e.g., `1862_land_grant_college` → `col_1862_land_grant_college`)
   - The hyphenated column names like `outlayed_amount_from_COVID-19_supplementals_for_overall_award` need hyphens converted to underscores: `outlayed_amount_from_covid_19_supplementals_for_overall_award` (also lowercase)
   - Verify all `db_column_name` values are valid Postgres identifiers (no spaces, no hyphens, no leading digits, all lowercase)

3. Export `USASPENDING_DB_COLUMN_NAMES: list[str]` — just the db_column_names in order.

4. Export `USASPENDING_COLUMN_COUNT: int` — must be 297.

5. Export `USASPENDING_DELTA_EXTRA_COLUMNS: list[dict]` — the 2 delta-only columns (`correction_delete_ind`, `agency_id`) with their metadata.

6. Export `USASPENDING_DELTA_COLUMN_COUNT: int` — must be 299.

7. **Generate programmatically.** Read the header row from `/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip` (first CSV inside the ZIP) to get the exact 297 column names. Then hardcode the result as a constant (no runtime ZIP dependency). Also read the delta header from `/Users/benjamincrane/Downloads/FY(All)_All_Contracts_Delta_20260306.zip` to confirm the 2 extra columns.

8. Self-test at the bottom: load, print count, assert 297, assert first column is `contract_transaction_unique_key`, assert last is `last_modified_date`, assert no duplicate db_column_names.

Commit standalone.

---

### Deliverable 2: Migration — `usaspending_contracts` Table

Create `supabase/migrations/031_usaspending_contracts.sql`.

Follow the exact pattern of `030_sam_gov_entities.sql`:

1. Create `entities.usaspending_contracts` with:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - All 297 CSV columns as `TEXT` (use db_column_names from Deliverable 1)
   - The 2 delta-only columns as `TEXT` (nullable)
   - All extract metadata columns from the Table Design section
   - `created_at` and `updated_at`

2. `UNIQUE (extract_date, contract_transaction_unique_key)` constraint.

3. All indexes from the Table Design section.

4. `updated_at` trigger (reuse `update_updated_at_column()` function).

5. Enable RLS.

6. Wrap in `BEGIN; ... COMMIT;`

Generate the 297 column definitions from the column map module. Do not hand-type them.

Commit standalone.

---

### Deliverable 3: USASpending Bulk Persistence Common Utilities

Create `app/services/usaspending_common.py`.

Follow the same structure as `app/services/sam_gov_common.py`:

1. **Connection pool:** Dedicated `_usaspending_pool` using `psycopg_pool.ConnectionPool`. Min 1, max 4, 30s timeout. Same pattern as `_get_sam_gov_connection_pool()`.

2. **Constants:**
   ```
   USASPENDING_TABLE_NAME = "usaspending_contracts"
   USASPENDING_SCHEMA = "entities"
   USASPENDING_CONFLICT_COLUMNS = ("extract_date", "contract_transaction_unique_key")
   USASPENDING_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset({"created_at"})
   ```

3. **Source context type:**
   ```
   UsaspendingSourceContext(TypedDict):
       extract_date: str          # YYYY-MM-DD
       extract_type: str          # FULL or DELTA
       source_filename: str       # original CSV filename
   ```

4. **Row type:**
   ```
   UsaspendingCsvRow(TypedDict):
       row_number: int
       fields: dict[str, str]     # CSV header -> value mapping
   ```

5. **`parse_usaspending_csv_row(row_dict: dict[str, str], row_number: int, is_delta: bool = False) -> UsaspendingCsvRow | None`**
   - `row_dict` is what Python's `csv.DictReader` yields (header -> value mapping)
   - Validate the expected column count: 297 for full, 299 for delta
   - Validate `contract_transaction_unique_key` is non-empty
   - Return `UsaspendingCsvRow` or None (with warning log) on validation failure

6. **`build_usaspending_contract_row(row: UsaspendingCsvRow, source_context: UsaspendingSourceContext, is_delta: bool = False) -> dict[str, Any]`**
   - Map CSV header names to db_column_names using `USASPENDING_DB_COLUMN_NAMES` from Deliverable 1
   - For delta files: also map `correction_delete_ind` and `agency_id` from the 2 extra columns
   - For full files: `correction_delete_ind` and `agency_id` are None
   - Add extract metadata: `extract_date`, `extract_type`, `source_filename`, `source_provider` (hardcode `usaspending`), `row_position`, `ingested_at`
   - Strip whitespace from all values; convert empty strings to None

7. **`upsert_usaspending_contracts(source_context: UsaspendingSourceContext, rows: list[UsaspendingCsvRow], is_delta: bool = False) -> dict[str, Any]`**
   - Follow the exact bulk COPY pattern from `upsert_sam_gov_entities()`:
     1. Build typed rows using `build_usaspending_contract_row()`
     2. Deduplicate on `(extract_date, contract_transaction_unique_key)` — last occurrence wins
     3. Create temp staging table: `CREATE TEMP TABLE ... (LIKE entities.usaspending_contracts INCLUDING DEFAULTS) ON COMMIT DROP`
     4. COPY rows into temp table using tab-delimited format
     5. Merge: `INSERT INTO entities.usaspending_contracts (...) SELECT ... FROM tmp_table ON CONFLICT (extract_date, contract_transaction_unique_key) DO UPDATE SET ...`
   - Statement timeout: `600s`
   - Phase timing instrumentation (same phases as SAM.gov)
   - Return result dict: `{ table_name, extract_date, rows_received, rows_deduplicated, rows_written }`

Commit standalone.

---

### Deliverable 4: USASpending CSV Ingest Service

Create `app/services/usaspending_extract_ingest.py`.

Follow the same structure as `app/services/sam_gov_extract_ingest.py`:

1. **`ingest_usaspending_csv(*, csv_file_path: str, extract_date: str, extract_type: str, source_filename: str, is_delta: bool = False, chunk_size: int = 50_000) -> dict[str, Any]`**
   - `csv_file_path` is the path to a single CSV file (already extracted from ZIP)
   - Opens the CSV file using `csv.DictReader` (which uses the header row automatically)
   - Validates the column count from the header: 297 for full, 299 for delta
   - Parses each row with `parse_usaspending_csv_row()`
   - Accumulates rows into chunks of `chunk_size`
   - Persists each chunk via `upsert_usaspending_contracts()`
   - Returns summary dict: total_rows_parsed, accepted, rejected, written, chunks, elapsed_ms

2. **`ingest_usaspending_zip(*, zip_file_path: str, extract_date: str, extract_type: str, chunk_size: int = 50_000) -> dict[str, Any]`**
   - Opens the ZIP file, iterates over all CSV files inside
   - For each CSV: extracts to a temp location, calls `ingest_usaspending_csv()`, cleans up
   - Aggregates results across all CSVs in the ZIP
   - Returns combined summary dict with per-file breakdowns

3. **Multi-file handling:** USASpending ZIPs can contain 2-3 CSVs (split at 1M rows each). Each CSV has its own header row. Process them sequentially — each one is an independent `ingest_usaspending_csv()` call with the same `extract_date` but different `source_filename`.

4. **Error handling:** Same as SAM.gov — chunk failures logged with chunk number and rows processed, then re-raised. Never swallowed.

Commit standalone.

---

### Deliverable 5: Internal Ingest Endpoint

Wire a new internal endpoint in `app/routers/internal.py`:

**`POST /api/internal/usaspending-contracts/ingest`**

Auth: `require_internal_key` (same as SAM.gov endpoint).

Request body (Pydantic model):
```
class InternalUsaspendingIngestRequest(BaseModel):
    zip_file_path: str           # Path to ZIP file containing CSVs
    extract_date: str            # YYYY-MM-DD
    extract_type: str            # FULL or DELTA
```

Calls `ingest_usaspending_zip()`.

Response: `DataEnvelope` wrapping the result dict.

Error handling: `ValueError` → 422, `RuntimeError` → 500.

Commit standalone.

---

### Deliverable 6: Tests

Create `tests/test_usaspending_ingest.py`.

Follow the same structure as `tests/test_sam_gov_ingest.py`:

1. **Column map tests:**
   - `USASPENDING_COLUMN_COUNT` equals 297
   - `USASPENDING_DELTA_COLUMN_COUNT` equals 299
   - First column is `contract_transaction_unique_key`
   - Last column is `last_modified_date`
   - Column 49 (`recipient_uei`) is present
   - Column 110 (`naics_code`) is present
   - All `db_column_name` values are valid Postgres identifiers
   - No duplicate `db_column_name` values
   - No hyphens in any `db_column_name`
   - Columns starting with digits are prefixed with `col_`

2. **CSV parser tests:**
   - Valid 297-column row parses correctly
   - Valid 299-column delta row parses correctly
   - Row with missing `contract_transaction_unique_key` returns None
   - Empty/whitespace values are handled correctly

3. **Row builder tests:**
   - CSV headers map to correct db_column_names
   - Extract metadata columns populated correctly
   - Delta columns (correction_delete_ind, agency_id) populated for delta rows
   - Delta columns are None for full file rows
   - Empty strings become None

4. **Ingest service tests (mock DB):**
   - Mock `upsert_usaspending_contracts` and verify correctly shaped rows
   - Verify chunking: feed 150K rows with chunk_size=50K, verify 3 chunks
   - Verify error propagation
   - Verify multi-CSV ZIP handling calls ingest once per CSV

All tests mock external calls. Use `pytest`.

Commit standalone.

---

### Deliverable 7: Parse Validation Against Real File

Create `scripts/validate_usaspending_parse.py`.

Runnable with: `doppler run -- python scripts/validate_usaspending_parse.py`

The script must:

1. Open `/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip` using `zipfile.ZipFile`. Read the first CSV inside the ZIP.

2. Parse the first **100 data rows** using `parse_usaspending_csv_row()`.

3. For each parsed row, call `build_usaspending_contract_row()` with a dummy source context (`extract_date="2026-03-07"`, `extract_type="FULL"`, `source_filename` = the CSV filename).

4. Validate each built row:
   - `contract_transaction_unique_key` is non-empty
   - `recipient_uei` is populated (12-char)
   - `extract_date` equals `2026-03-07`
   - `source_filename` is populated

5. Print per-row summary for first 10 rows:
   ```
   Row 1: txn_key=8900_-NONE-_89303020DMA000020_P00010... | UEI=GHDAN1FNERA8 | name=THE MATTHEWS GROUP INC | naics=236220 | agency=DOE | OK
   ```

6. Print validation summary and field mapping verification for row 1.

7. Exit code 0 if all pass, 1 if any fail.

**Also validate the delta file:** Open `/Users/benjamincrane/Downloads/FY(All)_All_Contracts_Delta_20260306.zip`, parse 10 rows with `is_delta=True`, verify the 2 extra columns are captured.

**No database writes.** Read-only validation.

Commit standalone.

---

## What is NOT in scope

- **No Trigger.dev task.** Manual ingestion only for now.
- **No deploy commands.** Do not push.
- **No modifications to SAM.gov code.** USASpending gets its own modules.
- **No query endpoints.** No `/api/v1/usaspending-contracts/query`.
- **No data transformation.** Store raw CSV data as-is.
- **No delta deletion handling.** Store delta rows with `correction_delete_ind` values, but do not implement soft-delete logic. That is future work.
- **No full ingest run.** Build and validate the pipeline. The full 1.34M-row ingest will be a separate directive after validation passes.
- **No changes to existing entity tables.**

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Column map: total columns, first 3 and last 3 name mappings, any columns that needed renaming (digit prefix, hyphen conversion), self-test result
(b) Migration: table name, schema, column count, index count, constraint summary
(c) Bulk persistence: conflict target, chunk size, instrumentation phases, dedup key
(d) Ingest service: CSV parsing approach, multi-file ZIP handling, chunk error handling
(e) Internal endpoint: path, auth, request/response shape
(f) Tests: total count, all passing
(g) Parse validation: full summary output against real FY2026 file AND delta file
(h) Anything to flag — ambiguities, assumptions, concerns
