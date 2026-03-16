# Executor Directive: SBA 7(a) Loan Data Ingestion

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SBA (Small Business Administration) publishes 7(a) loan data as a public FOIA dataset — every SBA-guaranteed loan since FY2020 with borrower name, address, loan amount, NAICS code, lender, and more. We are adding it as a third bulk data source for data-engine-x, alongside SAM.gov entity registrations (867K entities) and USASpending contract transactions (1.34M rows). Unlike those datasets, SBA loan data has **no unique federal entity identifier** (no UEI, DUNS, or EIN) — deduplication relies on a composite key of borrower + loan attributes.

The data is a single flat CSV file with 43 columns and 357,866 rows. It is updated quarterly by the SBA (full replacement, not deltas). The file is a direct public download — no API auth, no rate limits.

This directive follows the **exact same architecture** as the SAM.gov and USASpending ingestion pipelines: column map → migration → bulk COPY persistence → CSV parser → ingest service → internal endpoint → tests.

This is a **new, independent data source** — it is not an extension of SAM.gov or USASpending work. SBA gets its own modules, its own table, its own parser.

---

## Reference Documents (Read Before Starting)

**Must read — SBA data contract:**
- `docs/SBA_DATA_INSPECTION_REPORT.md` — Complete 43-column manifest, sample records, data types, field descriptions, completeness analysis. **This is the authoritative reference for all columns and their behavior.**

**Must read — SAM.gov implementation (your primary code pattern reference):**
- `app/services/sam_gov_column_map.py` — Column map structure
- `app/services/sam_gov_common.py` — Bulk COPY utilities: connection pool, source context, row parser, row builder, upsert function
- `app/services/sam_gov_extract_ingest.py` — Ingest orchestrator: chunked persistence, error handling
- `supabase/migrations/030_sam_gov_entities.sql` — Migration pattern
- `tests/test_sam_gov_ingest.py` — Test structure

**Must read — USASpending implementation (second reference):**
- `app/services/usaspending_column_map.py` — CSV-based column map (closer to SBA's format)
- `app/services/usaspending_common.py` — CSV row parsing with `csv.DictReader`
- `app/services/usaspending_extract_ingest.py` — CSV ingest with header validation

---

## SBA 7(a) CSV Format Summary

| Property | Value |
|---|---|
| File type | CSV (comma-delimited), direct download (no ZIP) |
| Header row | **Yes** — first line is column names |
| Columns | **43** |
| Encoding | UTF-8/ASCII |
| Rows (current file) | 357,866 |
| Update cadence | Quarterly, full replacement (not delta) |
| Unique identifier | **None** — no UEI, DUNS, or EIN |
| Download URL | `https://data.sba.gov/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087/resource/d67d3ccb-2002-4134-a288-481b51cd3479/download/foia-7a-fy2020-present-asof-250930.csv` |

**Key columns:** `borrname` (borrower name), `borrstreet`/`borrcity`/`borrstate`/`borrzip` (borrower address), `naicscode`, `grossapproval` (loan amount), `approvaldate`, `bankname`, `jobssupported`, `businesstype`, `businessage`, `loanstatus`.

**The `asofdate` column:** Every row in a given quarterly file has the same `asofdate` value (e.g., `09/30/2025`). This is the SBA's data-as-of date and serves as the snapshot identifier.

**No deltas:** Each quarterly release is a complete replacement file. To support loading multiple quarters side by side, the table uses a composite key that includes the extract date.

---

## Deduplication Strategy

There is no single unique identifier for SBA 7(a) loans in this dataset. The closest approximation to a unique loan record is:

**Composite dedup key:** `(extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval)`

This identifies: "In this quarterly snapshot, this borrower at this address received a loan of this amount on this date." Edge cases where the same borrower gets two identical-amount loans on the same day at the same address are theoretically possible but extremely unlikely. If duplicates exist in the source file, last occurrence wins (same as SAM.gov/USASpending).

The `extract_date` prefix ensures quarterly snapshots can coexist — the March 2025 file and June 2025 file can both be loaded, and the same loan will appear in both with different `extract_date` values.

---

## Table Design

### Table name: `sba_7a_loans`

### Schema: `entities`

### Design principles

1. **Store all 43 columns as TEXT.** Same strategy as SAM.gov and USASpending — lossless ingestion. Type casting happens at query time.

2. **Column naming:** The CSV header names are already lowercase single-word identifiers (e.g., `borrname`, `naicscode`, `grossapproval`). Use them directly as database column names — no renaming needed.

3. **Composite unique key:** `(extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval)` — supports loading multiple quarterly snapshots side by side.

4. **Extract metadata columns:**

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID PRIMARY KEY DEFAULT gen_random_uuid()` | Surrogate PK |
| `extract_date` | `DATE NOT NULL` | Derived from `asofdate` column in the CSV (e.g., `09/30/2025` → `2025-09-30`) |
| `source_filename` | `TEXT NOT NULL` | Original CSV filename |
| `source_url` | `TEXT` | Download URL the file came from |
| `source_provider` | `TEXT NOT NULL DEFAULT 'sba'` | Provider attribution |
| `ingested_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | When this row was written |
| `row_position` | `INTEGER NOT NULL` | 1-based row number in the source file |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |

5. **Indexes:**
   - `(extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval)` — unique constraint provides this
   - `(borrname)` — borrower name lookup
   - `(borrstate)` — state filtering
   - `(naicscode)` — industry filtering
   - `(approvaldate)` — time-series queries
   - `(extract_date DESC)` — find latest snapshot
   - `(loanstatus)` — status filtering

---

## Deliverables

### Deliverable 1: Column Name Mapping Module

Create `app/services/sba_column_map.py`.

Follow the same structure as `usaspending_column_map.py` (which is the closer CSV pattern):

1. Export `SBA_COLUMNS: list[dict]` — ordered list of all 43 column definitions. Each dict: `position` (int, 1-based), `csv_header_name` (str, original CSV header), `db_column_name` (str, Postgres column name), `description` (str, brief).

2. **Column name conversion:** The SBA CSV headers are already valid Postgres identifiers (`asofdate`, `borrname`, `naicscode`, etc.) — use them directly. No renaming should be needed, but verify all 43 are valid (no spaces, no hyphens, no leading digits, all lowercase).

3. Export `SBA_DB_COLUMN_NAMES: list[str]` — just the db_column_names in order.

4. Export `SBA_COLUMN_COUNT: int` — must be 43.

5. Export `SBA_CSV_TO_DB_MAP: dict[str, str]` — maps CSV header → db_column_name (identity mapping in this case, but needed for the row builder pattern).

6. **Generate programmatically.** Download the CSV from the URL above and read the header row to get the exact 43 column names. Then hardcode the result as a constant (no runtime download dependency). Save the downloaded file to `/Users/benjamincrane/Downloads/sba_7a_fy2020_present.csv` for use in Deliverable 7.

7. Self-test at the bottom: load, print count, assert 43, assert first column is `asofdate`, assert last is `soldsecmrktind`, assert no duplicate db_column_names.

Commit standalone.

---

### Deliverable 2: Migration — `sba_7a_loans` Table

Create `supabase/migrations/032_sba_7a_loans.sql`.

Follow the exact pattern of `030_sam_gov_entities.sql`:

1. Create `entities.sba_7a_loans` with:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - All 43 CSV columns as `TEXT`
   - All extract metadata columns from the Table Design section
   - `created_at` and `updated_at`

2. `UNIQUE (extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval)` constraint. Use a named constraint: `uq_sba_7a_loans_extract_date_composite`.

3. All indexes from the Table Design section.

4. `updated_at` trigger (reuse `update_updated_at_column()` function).

5. Enable RLS.

6. Wrap in `BEGIN; ... COMMIT;`

Generate the 43 column definitions from the column map module. Do not hand-type them.

Commit standalone.

---

### Deliverable 3: SBA Bulk Persistence Common Utilities

Create `app/services/sba_common.py`.

Follow the same structure as `app/services/usaspending_common.py` (CSV-based pattern):

1. **Connection pool:** Dedicated `_sba_pool` using `psycopg_pool.ConnectionPool`. Min 1, max 4, 30s timeout.

2. **Constants:**
   ```
   SBA_TABLE_NAME = "sba_7a_loans"
   SBA_SCHEMA = "entities"
   SBA_CONFLICT_COLUMNS = ("extract_date", "borrname", "borrstreet", "borrcity", "borrstate", "approvaldate", "grossapproval")
   SBA_INSERT_ONLY_ON_CONFLICT_COLUMNS = frozenset({"created_at"})
   ```

3. **Source context type:**
   ```
   SbaSourceContext(TypedDict):
       extract_date: str          # YYYY-MM-DD (derived from asofdate)
       source_filename: str       # original CSV filename
       source_url: str            # download URL
   ```

4. **Row type:**
   ```
   SbaCsvRow(TypedDict):
       row_number: int
       fields: dict[str, str]     # CSV header -> value mapping
   ```

5. **`parse_sba_csv_row(row_dict: dict[str, str], row_number: int) -> SbaCsvRow | None`**
   - `row_dict` is what Python's `csv.DictReader` yields
   - Validate column count equals 43
   - Validate `borrname` is non-empty (reject rows with no borrower name)
   - Return `SbaCsvRow` or None (with warning log) on validation failure

6. **`build_sba_loan_row(row: SbaCsvRow, source_context: SbaSourceContext) -> dict[str, Any]`**
   - Map CSV header names to db_column_names using `SBA_CSV_TO_DB_MAP`
   - Add extract metadata: `extract_date`, `source_filename`, `source_url`, `source_provider` (hardcode `sba`), `row_position`, `ingested_at`
   - Strip whitespace from all values; convert empty strings to None

7. **`upsert_sba_loans(source_context: SbaSourceContext, rows: list[SbaCsvRow]) -> dict[str, Any]`**
   - Follow the exact bulk COPY pattern from `upsert_sam_gov_entities()` / `upsert_usaspending_contracts()`:
     1. Build typed rows
     2. Deduplicate on composite key — last occurrence wins
     3. Create temp staging table
     4. COPY rows into temp table
     5. Merge via INSERT...ON CONFLICT
   - Statement timeout: `600s`
   - Phase timing instrumentation
   - Return result dict: `{ table_name, extract_date, rows_received, rows_deduplicated, rows_written }`

Commit standalone.

---

### Deliverable 4: SBA CSV Ingest Service

Create `app/services/sba_ingest.py`.

Follow the same structure as `app/services/usaspending_extract_ingest.py`:

1. **`ingest_sba_csv(*, csv_file_path: str, extract_date: str, source_filename: str, source_url: str = "", chunk_size: int = 50_000) -> dict[str, Any]`**
   - `csv_file_path` is the path to the downloaded CSV file (already on disk)
   - Opens the CSV file using `csv.DictReader` (which uses the header row automatically)
   - Validates the column count from the header equals 43
   - Parses each row with `parse_sba_csv_row()`
   - Accumulates rows into chunks of `chunk_size`
   - Persists each chunk via `upsert_sba_loans()`
   - Returns summary dict: total_rows_parsed, accepted, rejected, written, chunks, elapsed_ms

2. **No ZIP handling needed.** This is a single flat CSV — no multi-file logic.

3. **No download logic in the ingest service.** The file must already be on disk. Download is handled separately (by the user or a future download utility).

4. **Error handling:** Same as SAM.gov/USASpending — chunk failures logged with chunk number and rows processed, then re-raised. Never swallowed.

Commit standalone.

---

### Deliverable 5: Internal Ingest Endpoint

Wire a new internal endpoint in `app/routers/internal.py`:

**`POST /api/internal/sba-7a-loans/ingest`**

Auth: `require_internal_key` (same as SAM.gov and USASpending endpoints).

Request body (Pydantic model):
```
class InternalSbaIngestRequest(BaseModel):
    csv_file_path: str           # Path to CSV file on disk
    extract_date: str            # YYYY-MM-DD (derived from asofdate in file)
    source_filename: str         # Original filename
    source_url: str = ""         # Download URL (optional)
    chunk_size: int = 50_000
```

Calls `ingest_sba_csv()`.

Response: `DataEnvelope` wrapping the result dict.

Error handling: `ValueError` → 422, `RuntimeError` → 500.

Commit standalone.

---

### Deliverable 6: Tests

Create `tests/test_sba_ingest.py`.

Follow the same structure as `tests/test_usaspending_ingest.py`:

1. **Column map tests:**
   - `SBA_COLUMN_COUNT` equals 43
   - First column is `asofdate`
   - Last column is `soldsecmrktind`
   - Key columns present: `borrname`, `naicscode`, `grossapproval`, `approvaldate`, `borrstate`, `loanstatus`
   - All `db_column_name` values are valid Postgres identifiers
   - No duplicate `db_column_name` values

2. **CSV parser tests:**
   - Valid 43-column row parses correctly
   - Row with missing `borrname` returns None
   - Row with wrong column count returns None

3. **Row builder tests:**
   - CSV headers map to correct db_column_names
   - Extract metadata columns populated correctly
   - Empty strings become None
   - Whitespace is stripped

4. **Ingest service tests (mock DB):**
   - Mock `upsert_sba_loans` and verify correctly shaped rows
   - Verify chunking behavior
   - Verify error propagation

All tests mock external calls. Use `pytest`.

Commit standalone.

---

### Deliverable 7: Parse Validation Against Real File

Create `scripts/validate_sba_parse.py`.

Runnable with: `doppler run -- python scripts/validate_sba_parse.py`

The script must:

1. Open `/Users/benjamincrane/Downloads/sba_7a_fy2020_present.csv` (downloaded in Deliverable 1).

2. Parse the first **100 data rows** using `parse_sba_csv_row()`.

3. For each parsed row, call `build_sba_loan_row()` with source context:
   ```
   source_context = {
       "extract_date": <derived from the asofdate value in the first data row, converted from MM/DD/YYYY to YYYY-MM-DD>,
       "source_filename": "foia-7a-fy2020-present-asof-250930.csv",
       "source_url": "https://data.sba.gov/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087/resource/d67d3ccb-2002-4134-a288-481b51cd3479/download/foia-7a-fy2020-present-asof-250930.csv"
   }
   ```

4. Validate each built row:
   - `borrname` is non-empty
   - `extract_date` is a valid date string
   - `source_filename` is populated
   - `row_position` matches the line number
   - `naicscode` is populated (6-digit)
   - `borrstate` is a 2-letter state code

5. Print per-row summary for first 10 rows:
   ```
   Row 1: name=EXAMPLE CORP | city=DALLAS | state=TX | naics=332710 | amount=350000 | date=07/18/2025 | status=EXEMPT | OK
   ```

6. Print validation summary and field mapping verification for row 1.

7. Exit code 0 if all pass, 1 if any fail.

**No database writes.** Read-only validation.

Commit standalone.

---

## What is NOT in scope

- **No Trigger.dev task.** Manual ingestion only for now.
- **No deploy commands.** Do not push.
- **No modifications to SAM.gov or USASpending code.** SBA gets its own modules.
- **No query endpoints.** No `/api/v1/sba-7a-loans/query`.
- **No data transformation.** Store raw CSV data as-is.
- **No entity resolution.** No fuzzy matching to SAM.gov, USASpending, or company_entities. That is future work.
- **No full ingest run.** Build and validate the pipeline. The full 357K-row ingest will be a separate directive after validation passes.
- **No changes to existing entity tables.**
- **No download automation.** The file must be manually downloaded and placed on disk before ingestion.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Column map: total columns, first 3 and last 3 name mappings, any columns that needed renaming, self-test result
(b) Migration: table name, schema, column count, index count, constraint summary (especially the composite unique key)
(c) Bulk persistence: conflict target (the 7-column composite), chunk size, dedup key
(d) Ingest service: CSV parsing approach, chunk error handling
(e) Internal endpoint: path, auth, request/response shape
(f) Tests: total count, all passing
(g) Parse validation: full summary output against real file — including the `asofdate` value found and the derived `extract_date`
(h) Anything to flag — especially: were there any duplicate rows in the first 100 that collided on the composite key? Were there any rows with empty `borrname`?
