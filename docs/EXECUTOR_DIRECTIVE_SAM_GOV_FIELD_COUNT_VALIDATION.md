# Executor Directive: SAM.gov Extract Field Count Validation

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SAM.gov entity extract ingestion pipeline (see `docs/EXECUTOR_DIRECTIVE_SAM_GOV_ENTITY_EXTRACT_INGESTION.md`) was built expecting 368 pipe-delimited fields per line in the `.dat` file. The column mapping JSON has `column_order` values 1-362, plus 6 additional elements without explicit `column_order` that were assigned sequential positions to reach 368. Before we run a real ingest against the full monthly extract (~900K rows, multi-GB file), we need to validate the actual field count on a real extract file. A mismatch would cause every row to be rejected.

**The strategy:** Download a **daily delta** extract instead of the monthly full dump. Daily deltas contain only thousands of rows and are far smaller. We only need one line to count the fields. This costs exactly **1 API call** — do not make more than 2 API calls total (1 for the extract metadata, 1 for the download). If either call fails, stop and report the error. Do not retry.

**API credit rule:** This directive authorizes a maximum of **2 SAM.gov API calls**. Do not exceed this under any circumstances.

---

## Existing code to read

- `app/services/sam_gov_extract_download.py` — The download service built in the prior directive. Use it.
- `app/services/sam_gov_common.py` — The parser (`parse_sam_gov_dat_line`) and column map imports.
- `app/services/sam_gov_column_map.py` — `SAM_GOV_COLUMN_COUNT` (expected: 368) and `SAM_GOV_DB_COLUMN_NAMES`.
- `docs/SAM_GOV_EXTRACT_SCHEMA_COMPREHENSION.md` — Section 1 (Extract File Format) for delimiter and end-of-record rules.

---

## Deliverable 1: Validation Script

Create `scripts/validate_sam_gov_field_count.py`.

This script:

1. Uses `download_sam_gov_extract()` to download a **DAILY** extract for **yesterday's date** (or the most recent available date — if yesterday fails with a "not found" response, try the day before, but that counts as your second API call — stop after that).

2. Opens the downloaded `.dat` file.

3. Reads the **first 10 lines** only. Does not read the entire file.

4. For each line:
   - Counts the number of pipe `|` delimiters (field count = delimiter count + 1... or the fields after split — just count the split result)
   - Checks whether the last field is `!end`
   - Prints: `Line {n}: {field_count} fields, last_field='{last_field}'`

5. Compares the observed field count against `SAM_GOV_COLUMN_COUNT` (368).

6. Prints a clear verdict:
   - `MATCH: .dat file has {n} fields, column map expects {SAM_GOV_COLUMN_COUNT}. Parser will work.`
   - or `MISMATCH: .dat file has {n} fields, column map expects {SAM_GOV_COLUMN_COUNT}. Parser needs adjustment before ingest.`

7. If MISMATCH, also prints:
   - The raw first line (truncated to 500 chars) for inspection
   - The difference: `Δ = {observed - expected}` fields

8. Cleans up: deletes the downloaded ZIP and `.dat` file after validation.

The script must be runnable with: `doppler run -- python scripts/validate_sam_gov_field_count.py`

Do not import or modify any production service code beyond what's listed above. This is a read-only validation — it does not write to any database.

Commit standalone.

---

## Deliverable 2: Report

Do not create a second commit. Just report back.

If the field counts **match**: Report the match and we proceed to first real ingest.

If the field counts **do not match**: Report the exact observed count, the raw first line (truncated), and your assessment of which columns in `sam_gov_column_map.py` need adjustment. Do NOT attempt to fix the column map or migration in this directive — just report.

---

## What is NOT in scope

- No database writes. This is a read-only validation.
- No modifications to the column map, migration, or ingestion code. Report only.
- No more than 2 SAM.gov API calls. If both fail, report the failure and stop.
- No deploy commands. Do not push.
- No downloading the monthly full extract. Use daily delta only.

## Commit convention

One commit for the validation script. Do not push.

## When done

Report back with:
(a) API calls made (count and endpoints hit)
(b) File downloaded: filename, size, line count (of first 10 lines)
(c) Observed field count per line
(d) Match/mismatch verdict against SAM_GOV_COLUMN_COUNT
(e) If mismatch: raw first line (truncated) and recommended adjustment
(f) Anything to flag
