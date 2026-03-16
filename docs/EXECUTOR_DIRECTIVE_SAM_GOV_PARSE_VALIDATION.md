# Executor Directive: SAM.gov Extract Parse Validation Against Real File

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SAM.gov ingestion pipeline has been updated to expect 142 fields per record (Public V2 format) and to skip the BOF header line. We need to validate the parser against a real downloaded extract file before attempting a full ingest. The file is already on disk — no API calls needed.

**API credit rule:** This directive requires **zero** SAM.gov API calls. The file is already downloaded.

---

## Existing code to use

- `app/services/sam_gov_column_map.py` — `SAM_GOV_COLUMN_COUNT`, `SAM_GOV_COLUMNS`, `SAM_GOV_DB_COLUMN_NAMES`
- `app/services/sam_gov_common.py` — `parse_sam_gov_dat_line()`, `build_sam_gov_entity_row()`

---

## Deliverable: Validation Script

Create `scripts/validate_sam_gov_parse.py`.

Runnable with: `doppler run -- python scripts/validate_sam_gov_parse.py`

The script must:

1. Open the file at `/Users/benjamincrane/Downloads/SAM_PUBLIC_MONTHLY_V2_20260301.ZIP`. Use `zipfile.ZipFile` to read the `.dat` inside the ZIP directly — do not require unzipping first.

2. Read the first line. Confirm it starts with `BOF`. Print the BOF line and skip it.

3. Parse the next **100 data lines** using `parse_sam_gov_dat_line()` from `sam_gov_common.py`.

4. For each successfully parsed row, call `build_sam_gov_entity_row()` with a dummy source context:
   ```
   source_context = {
       "extract_date": "2026-03-01",
       "extract_type": "MONTHLY",
       "source_filename": "SAM_PUBLIC_MONTHLY_V2_20260301.dat",
       "source_download_url": ""
   }
   ```

5. For each built row, validate:
   - `unique_entity_id` is non-empty (12-char UEI)
   - `end_of_record_indicator` equals `!end`
   - `sam_extract_code` is `A` or `E` (monthly file)
   - `extract_date` equals `2026-03-01`
   - `source_filename` is populated
   - `row_position` matches the line number

6. Print a per-line summary for the first 10 rows:
   ```
   Row 1: UEI=C111ATT311C8 | name=K & K CONSTRUCTION SUPPLY INC | state=CA | naics=444110 | extract_code=A | OK
   ```

7. Print a summary after all 100 rows:
   ```
   === VALIDATION SUMMARY ===
   BOF line: [the BOF line]
   Lines read: 100
   Parsed OK: X
   Parse failures: Y
   Row build OK: X
   Row build failures: Y
   Validation checks passed: X
   Validation checks failed: Y

   Sample field mapping verification (row 1):
     unique_entity_id (V2 pos 1) = "C111ATT311C8"
     legal_business_name (V2 pos 12) = "K & K CONSTRUCTION SUPPLY INC"
     entity_url (V2 pos 27) = "www.kkconstructionsupply.com"
     primary_naics (V2 pos 33) = "444110"
     physical_address_province_or_state (V2 pos 19) = "CA"
     end_of_record_indicator (V2 pos 142) = "!end"
   ```

8. If any failures occur, print the failing line number, the raw line (truncated to 200 chars), and the error.

9. Exit with code 0 if all 100 rows pass, exit code 1 if any fail.

**Do not write to any database.** This is a read-only parse validation.

Commit standalone. Do not push.

## When done

Report back with the full validation summary output.
