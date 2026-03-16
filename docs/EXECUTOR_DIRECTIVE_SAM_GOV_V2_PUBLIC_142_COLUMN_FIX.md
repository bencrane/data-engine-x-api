# Executor Directive: SAM.gov V2 Public Extract — 142-Column Fix

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The SAM.gov ingestion pipeline built in the prior directive assumed 368 pipe-delimited fields per record based on the full SAM Master Extract Mapping. Validation against real downloaded files revealed that the **Public V2 extract contains 142 fields per record, not 368.** The FOUO and Sensitive columns are omitted entirely from the Public extract — they are not sent as empty fields. This was confirmed across all 4 downloaded files (March and February 2026, both encoding variants). All 4 files show exactly 142 fields ending with `!end`.

Additionally, the `.dat` file has a **BOF (Beginning Of File) header line** as its first line (e.g., `BOF PUBLIC V2 00000000 20260301 0874709 0008190`) that is not a data record and must be skipped.

The 142 fields map exactly to the columns marked `sensitivity_level: "Public"` in `SAM_MASTER_EXTRACT_MAPPING_Feb2025.json`, in their original array order. The positional mapping from V2 file position to original 368-column position is not 1:1 — FOUO/Sensitive columns are removed, so positions shift after column 26.

**What needs to change:** Column map, migration, parser, and tests. The bulk COPY persistence mechanics, metadata columns, composite unique key, chunking, error propagation, download service, internal endpoint, and test structure are all correct and do not change.

---

## Existing code to read

- `app/services/sam_gov_column_map.py` — Current 368-column map. Replace with 142.
- `app/services/sam_gov_common.py` — Parser expects 368 fields. Fix to 142 + BOF skip.
- `app/services/sam_gov_extract_ingest.py` — Ingest service reads lines. Must skip BOF.
- `supabase/migrations/030_sam_gov_entities.sql` — Current 368-column migration. Replace with 142.
- `tests/test_sam_gov_ingest.py` — Tests assert 368. Fix to 142.
- `api-reference-docs-new/sam-gov/02-data-services-file-extracts/03-data-dictionary/04-entity-information/SAM_MASTER_EXTRACT_MAPPING_Feb2025.json` — Source of truth. Filter to `sensitivity_level == "Public"` only.

---

## The 142 Public V2 Columns (Verified)

These are the exact 142 fields in the Public V2 `.dat` file, in order. The V2 position is the 0-based pipe-split index in the file. The original column is the `column_order` from the 368-column mapping.

| V2 Pos | Orig Col | Field Name |
|---:|---:|---|
| 1 | 1 | UNIQUE ENTITY ID |
| 2 | 2 | BLANK (DEPRECATED) |
| 3 | 3 | ENTITY EFT INDICATOR |
| 4 | 4 | CAGE CODE |
| 5 | 5 | DODAAC |
| 6 | 6 | SAM EXTRACT CODE |
| 7 | 7 | PURPOSE OF REGISTRATION |
| 8 | 8 | INITIAL REGISTRATION DATE |
| 9 | 9 | REGISTRATION EXPIRATION DATE |
| 10 | 10 | LAST UPDATE DATE |
| 11 | 11 | ACTIVATION DATE |
| 12 | 12 | LEGAL BUSINESS NAME |
| 13 | 13 | DBA NAME |
| 14 | 14 | ENTITY DIVISION NAME |
| 15 | 15 | ENTITY DIVISION NUMBER |
| 16 | 16 | PHYSICAL ADDRESS LINE 1 |
| 17 | 17 | PHYSICAL ADDRESS LINE 2 |
| 18 | 18 | PHYSICAL ADDRESS CITY |
| 19 | 19 | PHYSICAL ADDRESS PROVINCE OR STATE |
| 20 | 20 | PHYSICAL ADDRESS ZIP/POSTAL CODE |
| 21 | 21 | PHYSICAL ADDRESS ZIP CODE +4 |
| 22 | 22 | PHYSICAL ADDRESS COUNTRY CODE |
| 23 | 23 | PHYSICAL ADDRESS CONGRESSIONAL DISTRICT |
| 24 | 24 | D&B OPEN DATA FLAG |
| 25 | 25 | ENTITY START DATE |
| 26 | 26 | FISCAL YEAR END CLOSE DATE |
| 27 | 29 | ENTITY URL |
| 28 | 30 | ENTITY STRUCTURE |
| 29 | 31 | STATE OF INCORPORATION |
| 30 | 32 | COUNTRY OF INCORPORATION |
| 31 | 33 | BUSINESS TYPE COUNTER |
| 32 | 34 | BUS TYPE STRING |
| 33 | 36 | PRIMARY NAICS |
| 34 | 37 | NAICS CODE COUNTER |
| 35 | 38 | NAICS CODE STRING |
| 36 | 39 | PSC CODE COUNTER |
| 37 | 40 | PSC CODE STRING |
| 38 | 41 | CREDIT CARD USAGE |
| 39 | 42 | CORRESPONDENCE FLAG |
| 40 | 43 | MAILING ADDRESS LINE 1 |
| 41 | 44 | MAILING ADDRESS LINE 2 |
| 42 | 45 | MAILING ADDRESS CITY |
| 43 | 46 | MAILING ADDRESS ZIP/POSTAL CODE |
| 44 | 47 | MAILING ADDRESS ZIP CODE +4 |
| 45 | 48 | MAILING ADDRESS COUNTRY |
| 46 | 49 | MAILING ADDRESS STATE OR PROVINCE |
| 47 | 50 | GOVT BUS POC FIRST NAME |
| 48 | 51 | GOVT BUS POC MIDDLE INITIAL |
| 49 | 52 | GOVT BUS POC LAST NAME |
| 50 | 53 | GOVT BUS POC TITLE |
| 51 | 54 | GOVT BUS POC ST ADD 1 |
| 52 | 55 | GOVT BUS POC ST ADD 2 |
| 53 | 56 | GOVT BUS POC CITY |
| 54 | 57 | GOVT BUS POC ZIP/POSTAL CODE |
| 55 | 58 | GOVT BUS POC ZIP CODE +4 |
| 56 | 59 | GOVT BUS POC COUNTRY CODE |
| 57 | 60 | GOVT BUS POC STATE OR PROVINCE |
| 58 | 66 | ALT GOVT BUS POC FIRST NAME |
| 59 | 67 | ALT GOVT BUS POC MIDDLE INITIAL |
| 60 | 68 | ALT GOVT BUS POC LAST NAME |
| 61 | 69 | ALT GOVT BUS POC TITLE |
| 62 | 70 | ALT GOVT BUS POC ST ADD 1 |
| 63 | 71 | ALT GOVT BUS POC ST ADD 2 |
| 64 | 72 | ALT GOVT BUS POC CITY |
| 65 | 73 | ALT GOVT BUS POC ZIP/POSTAL CODE |
| 66 | 74 | ALT GOVT BUS POC ZIP CODE +4 |
| 67 | 75 | ALT GOVT BUS POC COUNTRY CODE |
| 68 | 76 | ALT GOVT BUS POC STATE OR PROVINCE |
| 69 | 82 | PAST PERF POC POC FIRST NAME |
| 70 | 83 | PAST PERF POC POC MIDDLE INITIAL |
| 71 | 84 | PAST PERF POC POC LAST NAME |
| 72 | 85 | PAST PERF POC POC TITLE |
| 73 | 86 | PAST PERF POC ST ADD 1 |
| 74 | 87 | PAST PERF POC ST ADD 2 |
| 75 | 88 | PAST PERF POC CITY |
| 76 | 89 | PAST PERF POC ZIP/POSTAL CODE |
| 77 | 90 | PAST PERF POC ZIP CODE +4 |
| 78 | 91 | PAST PERF POC COUNTRY CODE |
| 79 | 92 | PAST PERF POC STATE OR PROVINCE |
| 80 | 98 | ALT PAST PERF POC FIRST NAME |
| 81 | 99 | ALT PAST PERF POC MIDDLE INITIAL |
| 82 | 100 | ALT PAST PERF POC LAST NAME |
| 83 | 101 | ALT PAST PERF POC TITLE |
| 84 | 102 | ALT PAST PERF POC ST ADD 1 |
| 85 | 103 | ALT PAST PERF POC ST ADD 2 |
| 86 | 104 | ALT PAST PERF POC CITY |
| 87 | 105 | ALT PAST PERF POC ZIP/POSTAL CODE |
| 88 | 106 | ALT PAST PERF POC ZIP CODE +4 |
| 89 | 107 | ALT PAST PERF POC COUNTRY CODE |
| 90 | 108 | ALT PAST PERF POC STATE OR PROVINCE |
| 91 | 114 | ELEC BUS POC FIRST NAME |
| 92 | 115 | ELEC BUS POC MIDDLE INITIAL |
| 93 | 116 | ELEC BUS POC LAST NAME |
| 94 | 117 | ELEC BUS POC TITLE |
| 95 | 118 | ELEC BUS POC ST ADD 1 |
| 96 | 119 | ELEC BUS POC ST ADD 2 |
| 97 | 120 | ELEC BUS POC CITY |
| 98 | 121 | ELEC BUS POC ZIP/POSTAL CODE |
| 99 | 122 | ELEC BUS POC ZIP CODE +4 |
| 100 | 123 | ELEC BUS POC COUNTRY CODE |
| 101 | 124 | ELEC BUS POC STATE OR PROVINCE |
| 102 | 130 | ALT ELEC POC BUS POC FIRST NAME |
| 103 | 131 | ALT ELEC POC BUS POC MIDDLE INITIAL |
| 104 | 132 | ALT ELEC POC BUS POC LAST NAME |
| 105 | 133 | ALT ELEC POC BUS POC TITLE |
| 106 | 134 | ALT ELEC POC BUS ST ADD 1 |
| 107 | 135 | ALT ELEC POC BUS ST ADD 2 |
| 108 | 136 | ALT ELEC POC BUS CITY |
| 109 | 137 | ALT ELEC POC BUS ZIP/POSTAL CODE |
| 110 | 138 | ALT ELEC POC BUS ZIP CODE +4 |
| 111 | 139 | ALT ELEC POC BUS COUNTRY CODE |
| 112 | 140 | ALT ELEC POC BUS STATE OR PROVINCE |
| 113 | 285 | NAICS EXCEPTION COUNTER |
| 114 | 286 | NAICS EXCEPTION STRING |
| 115 | 287 | DEBT SUBJECT TO OFFSET FLAG |
| 116 | 288 | EXCLUSION STATUS FLAG |
| 117 | 289 | SBA BUSINESS TYPES COUNTER |
| 118 | 290 | SBA BUSINESS TYPES STRING |
| 119 | 293 | NO PUBLIC DISPLAY FLAG |
| 120 | 294 | DISASTER RESPONSE COUNTER |
| 121 | 295 | DISASTER RESPONSE STRING |
| 122 | 342 | ENTITY EVS SOURCE |
| 123-137 | 347-361 | FLEX FIELD 6 through FLEX FIELD 20 |
| 138-141 | N/A | FLEX FIELD 21 through FLEX FIELD 24 |
| 142 | 362 | END OF RECORD INDICATOR |

---

## Deliverables

### Deliverable 1: Fix Column Map

Rewrite `app/services/sam_gov_column_map.py`.

Changes:
1. Filter the mapping JSON to **only** columns where `sensitivity_level == "Public"`. Preserve array order from the JSON — this is the V2 file positional order.
2. `SAM_GOV_COLUMN_COUNT` must be **142**.
3. `SAM_GOV_COLUMNS` must contain 142 entries, each with V2 position (1-142), the original 368-mapping column_order (for reference), `sam_field_name`, `db_column_name` (snake_case), `datatype`, `max_length`, `sensitivity_level`.
4. `SAM_GOV_DB_COLUMN_NAMES` must be 142 snake_case names in V2 positional order.
5. Keep the same snake_case naming rules from the prior directive.
6. Update the self-test to assert 142.

Commit standalone.

---

### Deliverable 2: Fix Migration

Rewrite `supabase/migrations/030_sam_gov_entities.sql`.

Changes:
1. Replace the 368 SAM TEXT columns with the **142** Public V2 columns.
2. All metadata columns, unique constraint, indexes, trigger, and RLS remain the same.
3. Indexes that reference specific SAM columns (`primary_naics`, `physical_address_province_or_state`, `legal_business_name`) — verify these column names still exist in the 142-column set (they do — all are Public).
4. Generate from the updated column map. Do not hand-type.

Commit standalone.

---

### Deliverable 3: Fix Parser and Ingest Service

Update `app/services/sam_gov_common.py`:

1. `SAM_GOV_FIELD_COUNT` (or however it's named) must be **142**.
2. `parse_sam_gov_dat_line()` must validate field count against **142**.
3. `build_sam_gov_entity_row()` must map 142 positional fields to the 142 snake_case column names.

Update `app/services/sam_gov_extract_ingest.py`:

4. The ingest service must **skip the first line** of the `.dat` file (the BOF header). The BOF line starts with `BOF` and is not pipe-delimited data. Log it for informational purposes (it contains record counts) but do not parse it as a data row.
5. Optionally: parse the BOF line to extract the expected record count (the 5th space-separated token, e.g., `0874709`) and log it alongside the actual rows parsed at completion. This is a nice-to-have for validation, not required.

Commit standalone.

---

### Deliverable 4: Fix Tests

Update `tests/test_sam_gov_ingest.py`:

1. All assertions on `SAM_GOV_COLUMN_COUNT` → **142**.
2. All test pipe-delimited lines must have **142** fields, not 368.
3. Column position assertions: field 1 = `unique_entity_id`, field 142 = `end_of_record_indicator`, field 6 = SAM Extract Code, field 12 = Legal Business Name. These V2 positions are unchanged for fields 1-26. Field 27 onwards shifted — update any position-specific assertions.
4. Add a test for BOF line skipping: verify that a line starting with `BOF` is skipped by the ingest service and not passed to the parser.
5. Update the test pipe-delimited line generator to produce 142 fields ending with `!end`.

Commit standalone.

---

## What is NOT in scope

- No changes to `app/services/sam_gov_extract_download.py` — the download service is correct.
- No changes to `app/routers/internal.py` — the internal endpoint is correct.
- No new files. This is a fix to existing files only.
- No deploy commands. Do not push.
- No FOUO column handling. The 142-column map is for the Public V2 extract only. If we later get FOUO access, that will be a separate table or migration.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Column map: total columns, first 3 and last 3 name mappings, self-test result
(b) Migration: column count, index count, any column name changes from prior version
(c) Parser: new field count, BOF skip handling, any changes to row builder logic
(d) Tests: total test count, all passing, list any tests added or removed
(e) Anything to flag
