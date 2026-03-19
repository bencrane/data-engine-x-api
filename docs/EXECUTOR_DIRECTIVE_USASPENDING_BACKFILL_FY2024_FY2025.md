# Executor Directive: USASpending FY2024 + FY2025 Historical Backfill

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The USASpending contract ingestion pipeline is production-verified — it loaded 1,340,862 FY2026 rows in 18 minutes with zero rejections. We now need to backfill FY2024 and FY2025 contract award data through the same pipeline. The purpose is to improve the first-time awardee signal in `entities.mv_federal_contract_leads`: currently "first-time" means "first time in FY2026 data only." With 3 years of history, it means "first time across FY2024–FY2026" — a much stronger outbound signal.

**No code changes.** The ingestion pipeline, ingest service, column map, persistence utilities — everything already works. This directive is download files + run the existing pipeline + refresh the materialized view.

**API credit rule:** Zero API calls. These are direct file downloads from a public website.

---

## Reference Code (Read Before Starting)

- `scripts/run_usaspending_full_ingest.py` — The FY2026 ingest script. Your FY2024 and FY2025 scripts follow this exact pattern.
- `app/services/usaspending_extract_ingest.py` — `ingest_usaspending_zip()` — the ingest function you'll call
- `app/services/usaspending_common.py` — Bulk COPY persistence (do not modify)
- `app/services/usaspending_column_map.py` — Column map (do not modify)

---

## Deliverable 1: Download FY2024 and FY2025 Files

Go to the USASpending Award Data Archive page:
`https://www.usaspending.gov/download_center/award_data_archive`

Download two files:
- **FY2024** — "All Contracts" full file for Fiscal Year 2024
- **FY2025** — "All Contracts" full file for Fiscal Year 2025

These are pre-built ZIP files — direct downloads, no API, no auth.

Save them to `/Users/benjamincrane/Downloads/`:
- `/Users/benjamincrane/Downloads/FY2024_All_Contracts_Full_<date>.zip`
- `/Users/benjamincrane/Downloads/FY2025_All_Contracts_Full_<date>.zip`

(The `<date>` suffix is assigned by USASpending and varies — use whatever the actual filename is.)

**File size warning:** Each file is 2–5 GB compressed. The download may take several minutes.

After download, verify each ZIP:
1. Open with Python `zipfile.ZipFile` and list CSV filenames inside
2. Read the header row of the first CSV — confirm 297 columns
3. Read the first data row — confirm `contract_transaction_unique_key` is non-empty
4. Print: filename, CSV count, total size, column count, first row's action_date (to confirm fiscal year)

Print the verification results before proceeding.

---

## Deliverable 2: FY2024 Ingest Script

Create `scripts/run_usaspending_fy2024_ingest.py`.

This is a copy of `scripts/run_usaspending_full_ingest.py` with these changes:
- `ZIP_FILE_PATH` = the FY2024 file path from Deliverable 1
- `EXTRACT_DATE` = derive from the ZIP filename date suffix (e.g., if the file is `FY2024_All_Contracts_Full_20260310.zip`, use `2026-03-10`). This is the date the extract was generated, not the fiscal year.
- Title/print strings updated to say "FY2024" instead of "FY2026"

Everything else is identical — same `ingest_usaspending_zip()` call, same progress handler, same error handling.

**Run it:** `doppler run -- python scripts/run_usaspending_fy2024_ingest.py`

**Expected behavior:**
- Multiple CSVs in the ZIP (likely 2-4 files split at 1M rows)
- 15-30 minutes total depending on row count
- Zero rejections (same 297-column format as FY2026)

**Wait for FY2024 to complete successfully before starting FY2025.**

Report the full final summary output.

Commit the script standalone (before running).

---

## Deliverable 3: FY2025 Ingest Script

Create `scripts/run_usaspending_fy2025_ingest.py`.

Same pattern as Deliverable 2 but for FY2025:
- `ZIP_FILE_PATH` = the FY2025 file path
- `EXTRACT_DATE` = derive from the ZIP filename date suffix

**Run it:** `doppler run -- python scripts/run_usaspending_fy2025_ingest.py`

**Only run after FY2024 completes successfully.**

Report the full final summary output.

Commit the script standalone (before running).

---

## Deliverable 4: Refresh Materialized View

After both FY2024 and FY2025 ingests complete, refresh the materialized view so the first-time awardee flags recalculate against the full 3-year dataset.

Run this via the internal API endpoint (the server should be running locally or accessible):

```bash
doppler run -- python -c "
from app.services.federal_leads_refresh import refresh_federal_contract_leads, get_federal_leads_view_stats
print('Refreshing materialized view (this may take several minutes)...')
result = refresh_federal_contract_leads(concurrent=False)
print(f'Refresh completed in {result[\"elapsed_ms\"]}ms')
stats = get_federal_leads_view_stats()
print(f'Total rows: {stats[\"total_rows\"]:,}')
print(f'Unique companies: {stats[\"unique_companies\"]:,}')
print(f'First-time awardees: {stats[\"first_time_awardees\"]:,}')
"
```

Use `concurrent=False` since this is a full rebuild with significantly more data.

Report the stats before and after refresh (the "before" is the current FY2026-only stats, the "after" is the 3-year stats).

---

## Execution Order

1. Download both files (Deliverable 1)
2. Verify both files (Deliverable 1)
3. Commit FY2024 script, then run it (Deliverable 2) — wait for completion
4. Commit FY2025 script, then run it (Deliverable 3) — wait for completion
5. Refresh materialized view (Deliverable 4)

**Do not run FY2024 and FY2025 in parallel.** Run them sequentially. The database connection pool and bulk COPY operations are resource-intensive — running both simultaneously risks timeouts and connection pool exhaustion.

---

## What is NOT in scope

- **No code modifications.** The ingestion pipeline is production-verified. Do not modify any service files, column maps, persistence utilities, or the ingest function.
- **No schema migrations.** The `entities.usaspending_contracts` table already handles multiple extract dates.
- **No delta file processing.** Full files only.
- **No deploy commands.** Do not push.
- **No Trigger.dev tasks.**
- **No query endpoint changes.**

## Commit convention

Each ingest script is one commit (before running it). Do not push.

## When done

Report back with:
(a) Download verification: both files — filename, CSV count, column count, first-row fiscal year confirmation, file sizes
(b) FY2024 ingest: full summary output — rows parsed, accepted, rejected, written, chunks, elapsed time, per-file breakdown
(c) FY2025 ingest: full summary output — same fields
(d) View refresh: elapsed time, stats before (FY2026 only) and stats after (FY2024–FY2026) — specifically: total rows, unique companies, first-time awardees. The first-time awardee count should decrease significantly with 3 years of data (companies that looked "new" in FY2026 may have prior awards in FY2024/FY2025).
(e) Total data loaded across all 3 fiscal years: combined row count in `entities.usaspending_contracts`
(f) Anything to flag — especially: were there any rejections? Any duplicate transaction keys across fiscal years?
