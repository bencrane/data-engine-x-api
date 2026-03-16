# Executor Directive: USASpending.gov FY2026 Full Contract Ingest

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The USASpending.gov contract transaction ingestion pipeline is built, validated against 100 real rows (full) and 10 real rows (delta), and ready for a full ingest. The FY2026 full contract download is already on disk at `/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip`. It contains 1,340,862 rows across 2 CSV files. This directive loads the full file into the `entities.usaspending_contracts` table.

**API credit rule:** This directive requires **zero** API calls. The file is already downloaded.

**Prerequisites:** The migration `031_usaspending_contracts.sql` has already been applied. The `entities.usaspending_contracts` table exists in production.

---

## Existing code to use

- `app/services/usaspending_extract_ingest.py` — `ingest_usaspending_zip()` — the top-level ingest function (handles multi-CSV ZIPs)
- `app/services/usaspending_common.py` — bulk COPY persistence utilities
- `app/services/usaspending_column_map.py` — column definitions

---

## Deliverable: Ingest Script

Create `scripts/run_usaspending_full_ingest.py`.

Runnable with: `doppler run -- python scripts/run_usaspending_full_ingest.py`

The script must:

1. **Call `ingest_usaspending_zip()`** with:
   ```
   zip_file_path = "/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip"
   extract_date = "2026-03-06"
   extract_type = "FULL"
   chunk_size = 50_000
   ```

   The `ingest_usaspending_zip()` function already handles opening the ZIP, iterating CSVs, extracting to temp files, and cleaning up. Do not duplicate that logic in the script.

2. **Print progress per chunk.** Configure Python logging to output to stdout at INFO level so the ingest service's existing log statements are visible. If the service does not provide per-chunk logging to stdout, add `print()` statements in the script wrapper (not by modifying the service). The user needs to see:
   ```
   File 1/2: FY2026_All_Contracts_Full_20260306_1.csv
     Chunk 1/~27: rows 1-50000 written (elapsed: Xs)
     Chunk 2/~27: rows 50001-100000 written (elapsed: Xs)
     ...
   File 2/2: FY2026_All_Contracts_Full_20260306_2.csv
     Chunk 1/~7: rows 1-50000 written (elapsed: Xs)
     ...
   ```

3. **Print a final summary:**
   ```
   === USASPENDING FULL INGEST COMPLETE ===
   ZIP: FY2026_All_Contracts_Full_20260306.zip
   Extract date: 2026-03-06
   Files processed: 2
   Total rows parsed: X
   Rows accepted: X
   Rows rejected: X
   Rows written: X
   Chunks: X
   Total elapsed: X minutes Y seconds
   ```

4. **Error handling:** If any chunk fails, the script must print which file and chunk failed, how many rows were successfully committed before the failure, and the error message. Then exit with code 1. Do not swallow the error. Do not retry the failed chunk automatically.

5. **Resumability note:** The upsert on `(extract_date, contract_transaction_unique_key)` makes this idempotent. If the script fails mid-way and is re-run, already-committed rows will be updated (same data) and uncommitted rows will be inserted. Print a note about this at script start:
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
- No delta file ingestion. This directive is for the full file only.

## Commit convention

One commit. Do not push.

## When done

Run the script with `doppler run -- python scripts/run_usaspending_full_ingest.py` and report back with:
(a) The full final summary output
(b) Per-file breakdown (rows per CSV)
(c) If it failed: which file, which chunk, the error, and how many rows committed before failure
(d) Total wall-clock time
(e) Anything to flag
