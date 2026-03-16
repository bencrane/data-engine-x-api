# Executor Directive: SBA 7(a) Loan Data Full Ingest

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SBA 7(a) loan ingestion pipeline is built, validated against 100 real rows, and ready for a full ingest. The CSV file is already on disk at `/Users/benjamincrane/Downloads/sba_7a_fy2020_present.csv`. It contains 357,866 rows. This directive loads the full file into the `entities.sba_7a_loans` table.

**API credit rule:** This directive requires **zero** API calls. The file is already downloaded.

**Prerequisites:** The migration `032_sba_7a_loans.sql` has already been applied. The `entities.sba_7a_loans` table exists in production.

---

## Existing code to use

- `app/services/sba_ingest.py` — `ingest_sba_csv()` — the top-level ingest function
- `app/services/sba_common.py` — bulk COPY persistence utilities
- `app/services/sba_column_map.py` — column definitions

---

## Deliverable: Ingest Script

Create `scripts/run_sba_full_ingest.py`.

Runnable with: `doppler run -- python scripts/run_sba_full_ingest.py`

The script must:

1. **Derive `extract_date` from the file.** Open the CSV, read the first data row's `asofdate` value (e.g., `12/31/2025`), convert it from `MM/DD/YYYY` to `YYYY-MM-DD` format (e.g., `2025-12-31`), and use that as the `extract_date`. Print the derived value before starting the ingest.

2. **Call `ingest_sba_csv()`** with:
   ```
   csv_file_path = "/Users/benjamincrane/Downloads/sba_7a_fy2020_present.csv"
   extract_date = <derived from step 1>
   source_filename = "foia-7a-fy2020-present-asof-250930.csv"
   source_url = "https://data.sba.gov/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087/resource/d67d3ccb-2002-4134-a288-481b51cd3479/download/foia-7a-fy2020-present-asof-250930.csv"
   chunk_size = 50_000
   ```

3. **Print progress per chunk.** Configure Python logging to output to stdout at INFO level so the ingest service's existing log statements are visible. The user needs to see:
   ```
   Chunk 1/~8: rows 1-50000 written (elapsed: Xs)
   Chunk 2/~8: rows 50001-100000 written (elapsed: Xs)
   ...
   ```

4. **Print a final summary:**
   ```
   === SBA 7(a) FULL INGEST COMPLETE ===
   File: foia-7a-fy2020-present-asof-250930.csv
   Extract date: YYYY-MM-DD (derived from asofdate)
   Total rows parsed: X
   Rows accepted: X
   Rows rejected: X
   Rows written: X
   Duplicates deduplicated: X
   Chunks: X
   Total elapsed: X minutes Y seconds
   ```

5. **Error handling:** If any chunk fails, print which chunk failed, how many rows were successfully committed before the failure, and the error message. Then exit with code 1. Do not swallow the error. Do not retry automatically.

6. **Resumability note:** The upsert on the 7-column composite key makes this idempotent. Print at script start:
   ```
   NOTE: This ingest is idempotent. If interrupted, re-run safely — committed chunks are preserved.
   ```

Commit standalone. Do not push.

---

## What is NOT in scope

- No migration work. The table already exists.
- No API calls. The file is on disk.
- No modifications to the ingest service, parser, or common utilities. Use them as-is.
- No deploy commands. Do not push.

## Commit convention

One commit. Do not push.

## When done

Run the script with `doppler run -- python scripts/run_sba_full_ingest.py` and report back with:
(a) The full final summary output
(b) The derived extract_date (from the asofdate column)
(c) If it failed: which chunk, the error, and how many rows committed before failure
(d) Total wall-clock time
(e) Anything to flag — especially: how many duplicates were deduplicated on the composite key?
