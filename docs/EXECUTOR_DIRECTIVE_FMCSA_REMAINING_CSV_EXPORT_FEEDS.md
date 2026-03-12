# Directive: FMCSA Remaining CSV Export Feeds Ingestion

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The prior FMCSA batches established the ingestion architecture for this repo: preflight source validation, deterministic contract lock from in-repo data dictionaries, source-row-oriented storage with `feed_date`, no business-level deduplication at ingestion time, confirmed writes through FastAPI internal endpoints, and scheduled Trigger.dev cron tasks. This directive finishes the remaining FMCSA feeds using the CSV export endpoint pattern. Unlike the prior `text/plain` source files, these feeds are downloaded through `/api/views/{id}/rows.csv?accessType=DOWNLOAD` and return CSV with header rows. The executor must preserve the established row-storage semantics while adapting the downloader/parser to this header-row CSV source class.

## Source Feed Inventory

These sources are CSV export endpoints:

- transport: direct HTTP `GET`
- auth: none
- endpoint shape: `https://data.transportation.gov/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD`
- expected format: CSV with a header row

Feeds requested in scope:

- `Crash File`
  - dataset ID: `aayw-vxb3`
  - download URL: `https://data.transportation.gov/api/views/aayw-vxb3/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/27-crash-file/`
- `Carrier - All With History`
  - dataset ID: `6eyk-hxee`
  - download URL: `https://data.transportation.gov/api/views/6eyk-hxee/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/`
- `Inspections Per Unit`
  - dataset ID: `wt8s-2hbx`
  - download URL: `https://data.transportation.gov/api/views/wt8s-2hbx/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/29-inspections-per-unit/`
- `Special Studies`
  - dataset ID: `5qik-smay`
  - download URL: `https://data.transportation.gov/api/views/5qik-smay/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/30-special-studies/`
- `Revocation - All With History`
  - dataset ID: `sa6p-acbp`
  - download URL: `https://data.transportation.gov/api/views/sa6p-acbp/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/`
- `Insur - All With History`
  - dataset ID: `ypjt-5ydn`
  - download URL: `https://data.transportation.gov/api/views/ypjt-5ydn/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/`
- `OUT OF SERVICE ORDERS`
  - dataset ID: `p2mt-9ige`
  - download URL: `https://data.transportation.gov/api/views/p2mt-9ige/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/18-out-of-service-orders/`
- `Inspections and Citations`
  - dataset ID: `qbt8-7vic`
  - download URL: `https://data.transportation.gov/api/views/qbt8-7vic/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/19-inspections-and-citations/`
- `Vehicle Inspections and Violations`
  - dataset ID: `876r-jsdb`
  - download URL: `https://data.transportation.gov/api/views/876r-jsdb/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/20-vehicle-inspections-and-violations/`
- `Company Census File`
  - dataset ID: `az4n-8mr2`
  - download URL: `https://data.transportation.gov/api/views/az4n-8mr2/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/`
- `Vehicle Inspection File`
  - dataset ID: `fx4q-ay7w`
  - download URL: `https://data.transportation.gov/api/views/fx4q-ay7w/rows.csv?accessType=DOWNLOAD`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/05-vehicle-introspection-file-daily-diff/`

Special constraints:

- The executor must test every URL first and skip any feed whose URL does not return a valid CSV data file.
- The `All With History` feeds should share tables with their daily counterparts where the column structures and semantics actually match. The executor must verify this from the dictionaries, not assume by name.
- `Company Census File` and `Vehicle Inspection File` are expected to be large. The executor must explicitly choose the best approach for large downloads and large batch upserts rather than blindly reusing a small-feed strategy.

## Existing code to read

- `CLAUDE.md` — project conventions, Trigger/FastAPI boundary, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule and persistence guardrails
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — concept-based table naming, additive schema rules, no provider/source names in table names
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — confirmed writes and no-silent-failure requirement
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — Trigger baseline/context
- `docs/EXECUTOR_DIRECTIVE_FMCSA_DAILY_DIFF_INGESTION_TOP5_FEEDS.md` — first FMCSA batch directive
- `docs/EXECUTOR_DIRECTIVE_FMCSA_NEXT_BATCH_SNAPSHOTS_AND_HISTORY_FEEDS.md` — second FMCSA batch directive
- `docs/EXECUTOR_DIRECTIVE_FMCSA_SMS_FEEDS_INGESTION.md` — third FMCSA batch directive with preflight validation requirement
- `docs/api-reference-docs/fmcsa-open-data/27-crash-file/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/27-crash-file/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/29-inspections-per-unit/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/29-inspections-per-unit/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/30-special-studies/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/30-special-studies/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/18-out-of-service-orders/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/18-out-of-service-orders/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/19-inspections-and-citations/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/19-inspections-and-citations/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/20-vehicle-inspections-and-violations/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/20-vehicle-inspections-and-violations/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/05-vehicle-introspection-file-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/05-vehicle-introspection-file-daily-diff/overview-data-dictionary.md`
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- all later FMCSA migrations added by the second and third batches; inspect the real migration files present in `supabase/migrations/`
- `app/database.py` — schema-aware DB routing
- `app/services/fmcsa_daily_diff_common.py` — row-oriented storage semantics from prior batches
- `app/services/carrier_registrations.py`
- `app/services/insurance_filing_rejections.py`
- `app/services/process_agent_filings.py`
- all first/second/third-batch FMCSA service modules that already persist related concepts
- `app/routers/internal.py` — existing FMCSA internal batch upsert endpoints
- `trigger/src/workflows/fmcsa-daily-diff.ts` — existing shared FMCSA workflow; assess whether it should be generalized/extended for header-row CSV
- all existing `trigger/src/tasks/fmcsa-*.ts` task files — current schedule/config pattern
- `trigger/src/workflows/internal-api.ts` — internal authenticated HTTP client
- `trigger/src/workflows/persistence.ts` — confirmed-write helpers
- `tests/test_fmcsa_daily_diff_persistence.py`
- `trigger/src/workflows/__tests__/fmcsa-daily-diff.test.ts`
- `trigger/src/tasks/__tests__/fmcsa-daily-diff-tasks.test.ts`

---

### Deliverable 1: Preflight Validation and Contract Lock

Create `docs/FMCSA_REMAINING_CSV_EXPORT_FEEDS_PREFLIGHT_AND_MAPPINGS.md`.

First, validate each requested download URL using the same preflight pattern used in prior FMCSA batches, adapted for CSV export endpoints. For each feed, confirm that the URL:

- returns HTTP `200`
- returns a non-empty body
- returns a valid CSV file rather than HTML or an error payload
- includes a header row
- can be parsed into rows matching the expected field count from the data dictionary

Then, for each feed that passes preflight, record:

- feed name
- dataset ID
- download URL tested
- whether it passed or was skipped
- exact docs used
- exact ordered source fields from the data dictionary
- expected row width excluding the header row
- whether the source header names align with the dictionary contract or require explicit column-index mapping
- canonical business concept represented by the feed
- chosen canonical table name
- whether the feed should write into an existing table from a prior batch or a new table
- if reusing an existing table, why the structure and semantics are truly compatible
- if using a new table, why separation is required
- typed columns
- raw source row preservation plan
- required source metadata columns, including `feed_date`
- row identity / rerun idempotency strategy
- any large-file handling decision if the feed is expected to be large

Hard requirements:

- Any feed that fails preflight must be skipped from implementation.
- Do not guess a contract for a feed whose CSV header or row structure conflicts with the data dictionary.
- For `Carrier - All With History`, `Revocation - All With History`, and `Insur - All With History`, explicitly determine whether they should share tables with their daily counterparts.
- Table names must follow `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.

Commit standalone.

### Deliverable 2: Extend the Shared FMCSA Workflow for Header-Row CSV Feeds

Extend the existing FMCSA ingestion workflow pattern to support the CSV export endpoint class.

Requirements:

- adapt or generalize `trigger/src/workflows/fmcsa-daily-diff.ts` so it can cleanly support header-row CSV sources in addition to the prior no-header text sources
- do not create a totally separate FMCSA orchestration framework unless the current shared workflow is truly incompatible; if so, stop and report before forking the architecture
- for each feed that passed Deliverable 1:
  - download via direct HTTP `GET`
  - parse CSV with header rows using a robust CSV-capable parser
  - validate header/row shape against the contract from Deliverable 1
  - preserve `feed_date`
  - use confirmed writes through the existing internal API client and persistence helpers
  - create a real daily Trigger.dev cron task in code
- stagger schedules rather than firing all tasks at the same minute
- do not wire any of this through `run-pipeline.ts`

Large-file constraint:

- for `Company Census File` and `Vehicle Inspection File`, explicitly choose the best implementation approach for large file downloads and persistence
- acceptable solutions may include streamed download, chunked parsing, chunked internal writes, or another robust strategy
- do not require the entire file to live in memory at once if that is unsafe at the expected scale
- whatever strategy you choose must preserve confirmed-write semantics and surfaced failure behavior

Commit standalone.

### Deliverable 3: Persistence Path for Valid Remaining Feeds

Build or extend the FastAPI persistence layer for the remaining feeds that passed preflight.

Create or update:

- one or more migrations in `supabase/migrations/`
- service modules in `app/services/`
- internal batch upsert endpoints in `app/routers/internal.py`

Persistence requirements:

- write to `entities`
- preserve every source row as observed for the given `feed_date`
- no business-level deduplication at ingestion time
- include `feed_date`
- preserve source-row identity sufficient for idempotent same-`feed_date` reruns
- preserve typed business columns
- preserve raw source row payload
- preserve source metadata such as feed name, dataset ID, download URL, source variant, and run metadata
- keep confirmed-write semantics consistent with prior FMCSA batches

Table-sharing rule:

- `All With History` feeds should share tables with their daily counterparts where column structures and row semantics match
- if structures differ or mixing the variants would make downstream meaning ambiguous, split the tables
- document the decision in Deliverable 1 and align the implementation with it

Commit standalone.

### Deliverable 4: Tests and Regression Coverage

Add or extend tests to verify the remaining CSV-export feed behavior.

At minimum, cover:

- preflight validation for a valid CSV export file
- skip behavior for an invalid/non-data URL
- header-row CSV parsing
- header-to-contract validation
- row-width validation for representative feeds
- scheduling/task existence for all implemented feeds
- preservation of `feed_date`
- preservation of raw source rows
- no business-level deduplication at ingestion time
- idempotent same-`feed_date` rerun behavior using source-row identity
- coexistence of different `feed_date` snapshots for the same business row
- at least one shared-table case for an all-history variant if you choose sharing
- large-file strategy coverage for `Company Census File` and/or `Vehicle Inspection File` at the level you can reasonably test without hitting live data

Mock all HTTP calls and Trigger.dev behavior. Do not hit live FMCSA endpoints in tests.

Commit standalone.

---

**What is NOT in scope:** No browser automation. No Socrata JSON API beyond the documented CSV export endpoint path. No redesign of the existing FMCSA row-oriented storage semantics. No conversion of these feeds into deduplicated current-state company/person/job entity tables. No changes to `trigger/src/tasks/run-pipeline.ts`. No public query endpoints unless strictly required to validate internal architecture. No deploy commands. No downstream analytics or matching projects joining every FMCSA row to `company_entities`.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_REMAINING_CSV_EXPORT_FEEDS_PREFLIGHT_AND_MAPPINGS.md`, (b) the preflight result for each requested feed and which ones were skipped, (c) the canonical table decision for each implemented feed, especially which all-history variants shared tables with daily counterparts and which did not, (d) the migration file paths created or updated, (e) the internal endpoint paths added or extended, (f) the Trigger task IDs and schedules for all implemented feeds, (g) the exact storage semantics for `feed_date` and source-row identity, (h) the large-file handling approach chosen for `Company Census File` and `Vehicle Inspection File`, and (i) anything to flag — especially any CSV header/dictionary mismatches, any skipped feeds, or any reason a shared-table decision proved unsafe.
