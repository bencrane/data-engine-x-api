# Executor Directive: SAM.gov Public Entity Extract Ingestion

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** SAM.gov (System for Award Management) is the US government's entity registration database containing ~900,000+ active entity registrations. We are adding SAM.gov as a new data source for data-engine-x. The first deliverable is a Supabase table and a Python ingestion service that can parse the SAM.gov public entity extract (a pipe-delimited `.dat` flat file with 368 positional columns, no header row) and bulk-load it into Postgres using the proven COPY-based persistence pattern already in production for FMCSA feeds.

This is a **new, independent data source** — it is not an extension of FMCSA work. The FMCSA bulk COPY persistence utilities (`app/services/fmcsa_daily_diff_common.py`) are referenced only as a proven pattern for the Postgres COPY bulk-write mechanics. The SAM.gov ingestion has its own table, its own parser, its own service, and its own internal endpoint.

This is a **lower-frequency ingest** than FMCSA. Monthly full dumps (~900K rows) and daily deltas (thousands of rows). There is no cron-scheduled Trigger.dev task in this directive. The ingestion will initially be triggered manually or via an internal API call.

---

## Reference Documents (Read Before Starting)

**Must read — SAM.gov data contract:**
- `docs/SAM_GOV_EXTRACT_SCHEMA_COMPREHENSION.md` — Complete field map, sensitivity tiers, delimiter rules, file format, data volume expectations. **This is the authoritative reference for all 368 columns, their positions, types, max lengths, and sensitivity levels.**

**Must read — column mapping source of truth:**
- `api-reference-docs-new/sam-gov/02-data-services-file-extracts/03-data-dictionary/04-entity-information/SAM_MASTER_EXTRACT_MAPPING_Feb2025.json` — Machine-readable JSON defining every column position, field name, data type, max length, and sensitivity level. **Use this file to generate the column list programmatically. Do not hand-type 368 columns.**

**Must read — existing bulk persistence pattern (reference only):**
- `app/services/fmcsa_daily_diff_common.py` — The working COPY-based bulk write utilities: connection pooling (`psycopg_pool`), temp staging table creation, COPY serialization, merge SQL generation, instrumentation. Study the mechanics of `upsert_fmcsa_daily_diff_rows()`, `_create_temp_staging_table()`, `_copy_rows_into_temp_table()`, and `_build_fmcsa_bulk_merge_sql()`.

**Must read — existing per-feed upsert service (reference for structure only):**
- `app/services/carrier_registrations.py` — Example of a per-feed row builder + upsert function. Shows the pattern: define `TABLE_NAME`, write a `_build_*_row()` function that maps raw fields to typed columns, export an `upsert_*()` function that delegates to the common bulk writer.

**Must read — existing artifact ingest service (reference for endpoint pattern):**
- `app/services/fmcsa_artifact_ingest.py` — Shows how an internal endpoint receives a manifest, downloads an artifact, verifies checksum, decompresses, parses rows, and persists in chunks. The SAM.gov equivalent will follow a similar structure but with its own parser for pipe-delimited `.dat` files instead of NDJSON.

**Must read — existing internal router (reference for endpoint wiring):**
- `app/routers/internal.py` — See the `/api/internal/fmcsa-artifact-ingest` endpoint for how an ingest endpoint is wired with `require_internal_key` auth.

**Must read — migration pattern:**
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — Shows the migration pattern: `entities` schema, source metadata columns, indexes, `updated_at` trigger, RLS enablement.

---

## SAM.gov Extract File Format Summary

| Property | Value |
|---|---|
| File type | `.dat` pipe-delimited flat file, delivered in `.ZIP` |
| Delimiter | Pipe `\|` between columns |
| Repeating fields | Tilde `~` separates multiple values within a single column |
| Header row | **None** — positional columns only, matched by `column_order` in the mapping JSON |
| Total columns | 368 positions (362 data + 6 flex reserved + end-of-record marker) |
| End of record | Column 368 (position 362 in mapping): `!end` marker |
| Encoding | UTF-8 |
| Primary key | UEI (column 1) — 12-char alphanumeric |

**SAM Extract Code (column 6):**
- Monthly: `A` = Active, `E` = Expired (complete records)
- Daily: `1` = Deleted, `2` = New Active, `3` = Updated Active, `4` = Expired
- Daily codes `1` and `4` send only UEI + a few identity fields; `2` and `3` send complete records

**Sensitivity tiers:** ~172 columns are populated in the public extract. The rest (FOUO/Sensitive) will be empty strings but must have column slots in the table for future FOUO access.

---

## SAM.gov Extracts API

**Endpoint:** `GET https://api.sam.gov/data-services/v1/extracts`

**Auth:** Query parameter `api_key` from Doppler env var `SAM_GOV_API_KEY`.

**Parameters:**

| Parameter | Value | Notes |
|---|---|---|
| `api_key` | `{SAM_GOV_API_KEY}` | Required |
| `fileType` | `ENTITY` | Entity registration extract |
| `sensitivity` | `PUBLIC` | Public-tier data |
| `frequency` | `MONTHLY` or `DAILY` | Full dump vs delta |
| `date` | `MM/DD/YYYY` | Target extract date |

**Response:** JSON containing a download URL for the `.ZIP` file. The ZIP contains one `.dat` file.

**Rate limits:** 50 requests/day. Do not burn credits carelessly. Log every API call. Do not retry on 429. Prefer the smallest possible file to validate before attempting large operations.

---

## Table Design

### Table name: `sam_gov_entities`

### Schema: `entities`

### Design principles

1. **Store all 368 column positions.** Every column from the mapping JSON becomes a column in the table. FOUO/Sensitive columns will be empty TEXT for now but must exist for future population.

2. **Column naming:** Convert SAM field names to snake_case. Examples:
   - `UNIQUE ENTITY ID` → `unique_entity_id`
   - `LEGAL BUSINESS NAME` → `legal_business_name`
   - `PHYSICAL ADDRESS LINE 1` → `physical_address_line_1`
   - `NAICS CODE STRING` → `naics_code_string`
   - `GOVT BUSINESS POC FIRST NAME` → `govt_business_poc_first_name`
   - `BLANK (DEPRECATED)` → `col_002_deprecated` (use positional name for deprecated/blank slots)
   - `FLEX FIELD 6` through `FLEX FIELD 20` → `flex_field_06` through `flex_field_20`
   - `END OF RECORD INDICATOR` → `end_of_record_indicator`

3. **Data types:** All columns are `TEXT`. The extract is a flat text file. Do not attempt to cast dates, integers, or booleans at the table level. Type parsing happens in the row builder at read time or in query views later. This keeps ingestion fast and lossless.

4. **Composite primary key:** `(extract_date, unique_entity_id)` — This allows loading multiple monthly snapshots side by side and supports daily delta upserts against the same extract_date partition.

5. **Extract metadata columns** (added beyond the 368 SAM columns):

| Column | Type | Notes |
|---|---|---|
| `id` | `UUID PRIMARY KEY DEFAULT gen_random_uuid()` | Surrogate PK for row identity |
| `extract_date` | `DATE NOT NULL` | The date of the extract file (from filename or API parameter) |
| `extract_type` | `TEXT NOT NULL` | `MONTHLY` or `DAILY` |
| `extract_code` | `TEXT` | Mirrors column 6 (SAM Extract Code) for fast filtering |
| `source_filename` | `TEXT NOT NULL` | Original `.dat` filename from the ZIP |
| `source_provider` | `TEXT NOT NULL DEFAULT 'sam_gov'` | Provider attribution |
| `source_download_url` | `TEXT` | URL the ZIP was downloaded from |
| `ingested_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | When this row was written |
| `row_position` | `INTEGER NOT NULL` | 1-based row number in the source file |
| `raw_source_row` | `TEXT` | The original pipe-delimited line, preserved verbatim for debugging |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |
| `updated_at` | `TIMESTAMPTZ NOT NULL DEFAULT NOW()` | Standard |

6. **Unique constraint:** `UNIQUE (extract_date, unique_entity_id)` — This is the upsert conflict target. A UEI can appear once per extract_date. Daily deltas upsert against this.

7. **Indexes:**
   - `(extract_date, unique_entity_id)` — unique constraint provides this
   - `(unique_entity_id)` — lookup by UEI across snapshots
   - `(extract_date DESC)` — find latest snapshot
   - `(extract_code)` — filter by record status
   - `(primary_naics)` — industry filtering
   - `(physical_address_province_or_state)` — state filtering
   - `(legal_business_name)` — name search (consider `text_pattern_ops` for prefix matching)

---

## Deliverables

### Deliverable 1: Column Name Mapping Module

Create `app/services/sam_gov_column_map.py`.

This module must:

1. Read `api-reference-docs-new/sam-gov/02-data-services-file-extracts/03-data-dictionary/04-entity-information/SAM_MASTER_EXTRACT_MAPPING_Feb2025.json` at import time (or use a hardcoded list generated from it — your call on which is cleaner).
2. Export a constant `SAM_GOV_COLUMNS: list[dict]` — ordered list of all 368 column definitions, each with: `position` (int), `sam_field_name` (str), `db_column_name` (str, snake_case), `datatype` (str), `max_length` (int | None), `sensitivity_level` (str).
3. Export `SAM_GOV_DB_COLUMN_NAMES: list[str]` — just the snake_case column names in positional order.
4. Export `SAM_GOV_COLUMN_COUNT: int` — should be 368.
5. The snake_case conversion must handle: spaces → underscores, special chars removed, all lowercase, leading numbers prefixed (e.g., `820S REQUEST FLAG` → `flag_820s_request` or similar valid identifier). Deprecated/blank columns get positional names like `col_002_deprecated`.

Write a small self-test at the bottom of the file (`if __name__ == "__main__"`) that loads the mapping, prints the column count, and asserts it equals 368.

Commit standalone.

---

### Deliverable 2: Migration — `sam_gov_entities` Table

Create `supabase/migrations/030_sam_gov_entities.sql`.

The migration must:

1. Create `entities.sam_gov_entities` with:
   - `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`
   - All 368 SAM columns as `TEXT` (use the column names from Deliverable 1)
   - All extract metadata columns listed in the Table Design section above
   - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
   - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

2. Add `UNIQUE (extract_date, unique_entity_id)` constraint.

3. Add the indexes listed in the Table Design section.

4. Add the `updated_at` trigger (follow the FMCSA migration pattern — `update_updated_at_column()` function already exists).

5. Enable RLS: `ALTER TABLE entities.sam_gov_entities ENABLE ROW LEVEL SECURITY;`

6. Wrap in `BEGIN; ... COMMIT;`

**Important:** Generate the 368 column definitions from the mapping JSON. Do not hand-type them. You can use the column map module from Deliverable 1 to generate the SQL, or write a small script. The migration file itself must be pure SQL (no runtime code), but you can use a script to generate it.

Commit standalone.

---

### Deliverable 3: SAM.gov Bulk Persistence Common Utilities

Create `app/services/sam_gov_common.py`.

This module provides the SAM.gov-specific bulk write utilities, following the proven mechanics from `app/services/fmcsa_daily_diff_common.py` but adapted for SAM.gov:

1. **Connection pool:** Create a dedicated `_sam_gov_pool` using `psycopg_pool.ConnectionPool` (same pattern as `_get_fmcsa_connection_pool()`). Min 1, max 4 connections. 30s timeout.

2. **Source context type:**
   ```
   SamGovSourceContext(TypedDict):
       extract_date: str          # YYYY-MM-DD
       extract_type: str          # MONTHLY or DAILY
       source_filename: str       # original .dat filename
       source_download_url: str   # download URL
   ```

3. **Row type:**
   ```
   SamGovExtractRow(TypedDict):
       row_number: int
       raw_line: str              # original pipe-delimited line
       fields: list[str]          # split fields (368 items)
   ```

4. **`parse_sam_gov_dat_line(line: str, row_number: int) -> SamGovExtractRow`**
   - Split on pipe `|` delimiter
   - Validate field count equals 368. If not, log warning and skip (return None or raise — your call, but do not silently drop rows without logging).
   - Verify last field is `!end` marker
   - Return `SamGovExtractRow` with the raw line preserved and fields as a list

5. **`build_sam_gov_entity_row(row: SamGovExtractRow, source_context: SamGovSourceContext) -> dict[str, Any]`**
   - Map positional fields to snake_case column names using `SAM_GOV_DB_COLUMN_NAMES` from Deliverable 1
   - Add extract metadata columns: `extract_date`, `extract_type`, `extract_code` (from field at position 5, which is column 6 — zero-indexed), `source_filename`, `source_provider` (hardcode `sam_gov`), `source_download_url`, `row_position`, `raw_source_row` (the original pipe-delimited line)
   - Empty strings from FOUO/Sensitive columns become `None` (NULL in DB)
   - Strip whitespace from all field values; convert empty strings to `None`

6. **`upsert_sam_gov_entities(source_context: SamGovSourceContext, rows: list[SamGovExtractRow]) -> dict[str, Any]`**
   - Follow the bulk COPY pattern from `upsert_fmcsa_daily_diff_rows()`:
     1. Build typed rows using `build_sam_gov_entity_row()`
     2. Create temp staging table: `CREATE TEMP TABLE ... (LIKE entities.sam_gov_entities INCLUDING DEFAULTS) ON COMMIT DROP`
     3. COPY rows into temp table using tab-delimited format
     4. Merge to live table: `INSERT INTO entities.sam_gov_entities (...) SELECT ... FROM tmp_table ON CONFLICT (extract_date, unique_entity_id) DO UPDATE SET ...`
   - Statement timeout: `600s` (10 minutes) — same as FMCSA
   - Include timing instrumentation (connection acquire, row build, COPY, merge, commit — same phases as FMCSA)
   - Return result dict: `{ table_name, extract_date, rows_received, rows_written }`

Commit standalone.

---

### Deliverable 4: SAM.gov Extract Ingest Service

Create `app/services/sam_gov_extract_ingest.py`.

This is the top-level service that orchestrates a full extract ingest:

1. **`ingest_sam_gov_extract(*, extract_file_path: str, extract_date: str, extract_type: str, source_filename: str, source_download_url: str | None = None, chunk_size: int = 50_000) -> dict[str, Any]`**
   - `extract_file_path` is the path to the unzipped `.dat` file on the local filesystem (or a file-like object — your call)
   - Opens the file, reads line by line
   - Parses each line with `parse_sam_gov_dat_line()`
   - Accumulates rows into chunks of `chunk_size`
   - Persists each chunk via `upsert_sam_gov_entities()`
   - Tracks and returns: total rows parsed, rows accepted, rows rejected (bad field count), rows written, chunk count, total elapsed time
   - Logs a summary at completion (same structured logging pattern as FMCSA)

2. **Daily delta handling:** When `extract_type` is `DAILY`, rows with SAM Extract Code `1` (Deleted) or `4` (Expired) contain only a few identity fields — the rest are empty. These rows should still be upserted (they update the `extract_code` to reflect the deletion/expiration status). The upsert ON CONFLICT handles this naturally.

3. **Error handling:** If a chunk fails, log the error with chunk number, rows processed so far, and re-raise. Do not swallow errors. This is a critical lesson from FMCSA — silent failures are the worst architectural flaw in this system.

Commit standalone.

---

### Deliverable 5: SAM.gov Extract Download Service

Create `app/services/sam_gov_extract_download.py`.

This service handles downloading the extract file from the SAM.gov Extracts API:

1. **`download_sam_gov_extract(*, extract_type: str, date: str, output_dir: str) -> dict[str, Any]`**
   - `extract_type`: `MONTHLY` or `DAILY`
   - `date`: target date in `MM/DD/YYYY` format (SAM.gov API format)
   - `output_dir`: directory to write the unzipped `.dat` file
   - Steps:
     1. Call `GET https://api.sam.gov/data-services/v1/extracts?api_key={key}&fileType=ENTITY&sensitivity=PUBLIC&frequency={extract_type}&date={date}` using `httpx`
     2. Parse response to extract the download URL for the ZIP file
     3. Download the ZIP file (stream to disk — these files can be 2-5 GB uncompressed)
     4. Extract the `.dat` file from the ZIP
     5. Return: `{ download_url, zip_path, dat_file_path, source_filename, file_size_bytes }`
   - Use `SAM_GOV_API_KEY` from `app.config.get_settings()` (add to settings if needed)
   - Timeout: 600s for the ZIP download (these are large files)
   - **Rate limit awareness:** Log every API call. Do not retry on 429 — just raise. We have 50 requests/day. Do not waste credits.

2. Add `sam_gov_api_key: str` to the settings model in `app/config.py` (mapped to env var `SAM_GOV_API_KEY`).

Commit standalone.

---

### Deliverable 6: Internal Ingest Endpoint

Wire a new internal endpoint in `app/routers/internal.py`:

**`POST /api/internal/sam-gov-entities/ingest`**

Auth: `require_internal_key` (same as FMCSA endpoints).

Request body (Pydantic model):
```
{
    "extract_file_path": str,      # Path to unzipped .dat file
    "extract_date": str,           # YYYY-MM-DD
    "extract_type": str,           # MONTHLY or DAILY
    "source_filename": str,        # Original .dat filename
    "source_download_url": str | None
}
```

Response: `DataEnvelope` wrapping the result dict from `ingest_sam_gov_extract()`.

Error handling: Catch `ValueError` → 422, `RuntimeError` → 500. Do not swallow exceptions.

Commit standalone.

---

### Deliverable 7: Tests

Create `tests/test_sam_gov_ingest.py`.

Test cases:

1. **Column map tests:**
   - `SAM_GOV_COLUMN_COUNT` equals 368
   - First column is `unique_entity_id` at position 1
   - Last column (position 368) is `end_of_record_indicator`
   - Column 6 is SAM Extract Code
   - Column 12 is Legal Business Name
   - All `db_column_name` values are valid snake_case identifiers (no spaces, no special chars)
   - No duplicate `db_column_name` values

2. **Line parser tests:**
   - Valid 368-field pipe-delimited line parses correctly
   - Line with wrong field count raises/returns error
   - Line without `!end` marker raises/returns error
   - Empty fields become `None` after stripping
   - Fields with whitespace are stripped

3. **Row builder tests:**
   - Positional fields map to correct column names
   - Extract metadata columns are populated correctly
   - `extract_code` is extracted from the correct position (column 6, zero-index 5)
   - Empty/whitespace-only fields become `None`

4. **Ingest service tests (mock DB):**
   - Mock `upsert_sam_gov_entities` and verify it receives correctly shaped rows
   - Verify chunking: feed 150K rows with chunk_size=50K, verify 3 chunks
   - Verify error propagation: if a chunk fails, the error is re-raised (not swallowed)

All tests must mock external calls (no live DB, no live API). Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No Trigger.dev task.** The ingestion is triggered via the internal API endpoint or manually for now. Scheduled Trigger tasks are a future directive.
- **No deploy commands.** Do not push, do not deploy to Railway or Trigger.dev.
- **No modifications to FMCSA code.** The FMCSA utilities are read-only reference. SAM.gov gets its own modules.
- **No query endpoints.** No `/api/v1/sam-gov-entities/query` endpoint in this directive. That is separate work.
- **No data transformation or derived tables.** Store the raw extract data as-is. Derived views, NAICS parsing, business type decoding, etc. are future work.
- **No changes to existing entity tables** (`company_entities`, `person_entities`, etc.). SAM.gov data lives in its own dedicated table for now.
- **No FOUO/Sensitive data handling.** The table has column slots for FOUO fields, but they will be empty. Do not build FOUO-specific logic.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) The column map: total columns, sample of first 5 and last 5 column name mappings
(b) The migration: table name, schema, column count, index count, constraint summary
(c) The bulk persistence: conflict target, chunk size, instrumentation phases
(d) The ingest service: chunking strategy, error handling approach, daily delta handling
(e) The download service: API endpoint, auth method, ZIP handling approach
(f) The internal endpoint: path, auth, request/response shape
(g) Test count and coverage summary
(h) Anything to flag — ambiguities, assumptions made, concerns
