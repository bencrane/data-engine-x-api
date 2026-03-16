# Executor Directive: SAM.gov March 2026 Full Monthly Ingest

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SAM.gov Public V2 ingestion pipeline is built, validated against 100 real rows, and ready for a full ingest. The March 2026 monthly extract is already downloaded at `/Users/benjamincrane/Downloads/SAM_PUBLIC_MONTHLY_V2_20260301.ZIP`. It contains 874,709 records per the BOF header. This directive loads the full file into the `entities.sam_gov_entities` table.

**API credit rule:** This directive requires **zero** SAM.gov API calls. The file is already downloaded.

**Prerequisites:** The migration `030_sam_gov_entities.sql` has already been applied. The `entities.sam_gov_entities` table exists in production.

---

## Existing code to use

- `app/services/sam_gov_extract_ingest.py` — `ingest_sam_gov_extract()` — the top-level ingest function
- `app/services/sam_gov_common.py` — bulk COPY persistence utilities
- `app/services/sam_gov_column_map.py` — column definitions

---

## Deliverable: Ingest Script

Create `scripts/run_sam_gov_full_ingest.py`.

Runnable with: `doppler run -- python scripts/run_sam_gov_full_ingest.py`

The script must:

1. **Open the ZIP directly.** Use `zipfile.ZipFile` to read the `.dat` inside `/Users/benjamincrane/Downloads/SAM_PUBLIC_MONTHLY_V2_20260301.ZIP`. Extract the `.dat` to a temp directory, then pass the extracted file path to the ingest service. Clean up the temp file after completion.

2. **Call `ingest_sam_gov_extract()`** with:
   ```
   extract_file_path = <path to extracted .dat>
   extract_date = "2026-03-01"
   extract_type = "MONTHLY"
   source_filename = "SAM_PUBLIC_MONTHLY_V2_20260301.dat"
   source_download_url = None
   chunk_size = 50_000
   ```

3. **Print progress per chunk.** Before the script calls `ingest_sam_gov_extract()`, monkey-patch or wrap the chunk persistence to print progress. If the ingest service already logs per-chunk, that's sufficient — just make sure the output is visible. The user needs to see:
   ```
   Chunk 1/~18: rows 1-50000 written (elapsed: Xs)
   Chunk 2/~18: rows 50001-100000 written (elapsed: Xs)
   ...
   ```
   If the ingest service does not provide per-chunk logging to stdout, add `print()` statements in the script (not by modifying the service — keep the service clean). Alternatively, configure Python logging to output to stdout at INFO level so the service's existing log statements are visible.

4. **Print a final summary:**
   ```
   === SAM.GOV FULL INGEST COMPLETE ===
   File: SAM_PUBLIC_MONTHLY_V2_20260301.dat
   Extract date: 2026-03-01
   Total rows parsed: X
   Rows accepted: X
   Rows rejected: X
   Rows written: X
   Chunks: X
   Total elapsed: X minutes Y seconds
   ```

5. **Error handling:** If any chunk fails, the script must print which chunk failed, how many rows were successfully committed before the failure, and the error message. Then exit with code 1. Do not swallow the error. Do not retry the failed chunk automatically.

6. **Resumability note:** The upsert on `(extract_date, unique_entity_id)` makes this idempotent. If the script fails mid-way and is re-run, already-committed rows will be updated (same data) and uncommitted rows will be inserted. Print a note about this at script start:
   ```
   NOTE: This ingest is idempotent. If interrupted, re-run safely — committed chunks are preserved.
   ```

Commit standalone. Do not push.

---

## What is NOT in scope

- No migration work. The table already exists.
- No API calls to SAM.gov. The file is on disk.
- No modifications to the ingest service, parser, or common utilities. Use them as-is.
- No deploy commands. Do not push.

## Commit convention

One commit. Do not push.

## When done

Run the script with `doppler run -- python scripts/run_sam_gov_full_ingest.py` and report back with:
(a) The full final summary output
(b) If it failed: which chunk, the error, and how many rows committed before failure
(c) Total wall-clock time
(d) Anything to flag
