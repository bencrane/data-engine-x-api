# Directive: FMCSA SMS Feed Ingestion Workflows

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The first two FMCSA ingestion batches established the correct pattern for this repo: direct HTTP `GET` of FMCSA `text/plain` downloads, robust parsing of quoted comma-delimited no-header rows, row-oriented storage tagged with `feed_date`, no business-level deduplication at ingestion time, confirmed writes through FastAPI internal endpoints, and daily Trigger.dev cron tasks. This directive extends that exact pattern to the FMCSA SMS feeds listed below, with one additional requirement up front: validate the download URLs first and skip any feed whose URL does not actually return a valid data file.

## Source Feed Inventory

These are source `text/plain` downloads, not `.csv` files by extension, even though their contents are CSV-formatted quoted comma-delimited rows with no header row.

Feeds requested in scope:

- `SMS Input - Crash`
  - candidate download URL: `https://data.transportation.gov/download/gwak-5bwn/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/21-sms-input-crash/`
- `SMS AB PassProperty`
  - download URL: `https://data.transportation.gov/download/4y6x-dmck/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/22-sms-ab-passproperty/`
- `SMS C PassProperty`
  - download URL: `https://data.transportation.gov/download/h9zy-gjn8/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/23-sms-c-passproperty/`
- `SMS Input - Violation`
  - download URL: `https://data.transportation.gov/download/8mt8-2mdr/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/`
- `SMS Input - Inspection`
  - download URL: `https://data.transportation.gov/download/rbkj-cgst/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/`
- `SMS Input - Motor Carrier Census`
  - download URL: `https://data.transportation.gov/download/kjg3-diqy/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/`
- `SMS AB Pass`
  - download URL: `https://data.transportation.gov/download/m3ry-qcip/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/33-sms-ab-pass/`
- `SMS C Pass`
  - download URL: `https://data.transportation.gov/download/h9zy-gjn8/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/34-sms-c-pass/`

Special constraints for this batch:

- `SMS Input - Crash` dataset ID `gwak-5bwn` is not fully trusted yet. You must confirm it by checking the authoritative about-page/doc context before building against it.
- `SMS C Pass` and `SMS C PassProperty` currently point at the same dataset ID (`h9zy-gjn8`). You must determine whether they actually return distinct source files or the same file. If they return the same file, skip one and report which one you kept and why.
- Any feed whose download URL does not return a valid FMCSA data file must be skipped, not forced through a broken ingestion path.

Common transport/parse contract for all valid feeds:

- direct HTTP `GET`
- no auth
- no browser automation
- no Socrata JSON API as the primary ingestion path
- source file is `text/plain`
- contents are quoted comma-delimited rows
- no header row
- parse with a real CSV-capable parser

Storage semantics to preserve:

- store every source row tagged with `feed_date`
- do not do business-level deduplication at ingestion time
- preserve source-row identity for idempotent reruns of the same `feed_date`
- treat each file as an observed source snapshot for that `feed_date`

## Existing code to read

- `CLAUDE.md` — project conventions, Trigger/FastAPI boundary, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule and persistence guardrails
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — concept-based table naming and additive schema rules
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — confirmed writes and no-silent-failure requirement
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — Trigger baseline/context
- `docs/EXECUTOR_DIRECTIVE_FMCSA_DAILY_DIFF_INGESTION_TOP5_FEEDS.md` — first FMCSA batch directive
- `docs/EXECUTOR_DIRECTIVE_FMCSA_NEXT_BATCH_SNAPSHOTS_AND_HISTORY_FEEDS.md` — second FMCSA batch directive
- `docs/api-reference-docs/fmcsa-open-data/21-sms-input-crash/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/21-sms-input-crash/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/22-sms-ab-passproperty/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/22-sms-ab-passproperty/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/23-sms-c-passproperty/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/23-sms-c-passproperty/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/33-sms-ab-pass/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/33-sms-ab-pass/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/34-sms-c-pass/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/34-sms-c-pass/overview-data-dictionary.md`
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — first-batch schema/storage reference
- `app/database.py` — schema-aware DB routing
- `app/services/fmcsa_daily_diff_common.py` — row-oriented FMCSA storage semantics (`feed_date`, `row_position`, raw row payload, confirmed upsert path)
- `app/services/insurance_policies.py`
- `app/services/insurance_policy_filings.py`
- `app/services/insurance_policy_history_events.py`
- `app/services/operating_authority_histories.py`
- `app/services/operating_authority_revocations.py`
- `app/routers/internal.py` — first/second-batch internal batch upsert endpoint pattern
- `trigger/src/workflows/fmcsa-daily-diff.ts` — shared Trigger workflow
- `trigger/src/tasks/fmcsa-authhist-daily.ts`
- `trigger/src/tasks/fmcsa-revocation-daily.ts`
- `trigger/src/tasks/fmcsa-insurance-daily.ts`
- `trigger/src/tasks/fmcsa-actpendinsur-daily.ts`
- `trigger/src/tasks/fmcsa-inshist-daily.ts`
- `trigger/src/workflows/internal-api.ts` — internal authenticated HTTP client
- `trigger/src/workflows/persistence.ts` — confirmed-write helpers
- `tests/test_fmcsa_daily_diff_persistence.py`
- `trigger/src/workflows/__tests__/fmcsa-daily-diff.test.ts`
- `trigger/src/tasks/__tests__/fmcsa-daily-diff-tasks.test.ts`

---

### Deliverable 1: Preflight Download Validation and Contract Lock

Create `docs/FMCSA_SMS_FEEDS_PREFLIGHT_AND_MAPPINGS.md`.

First, validate each requested download URL using the same curl-style preflight pattern used in previous FMCSA work. For each feed, confirm that the URL:

- returns HTTP `200`
- returns a `text/plain` body
- returns a non-empty body
- appears to contain parseable quoted comma-delimited FMCSA data rows rather than an HTML page, catalog page, or error payload

Then, for each feed that passes preflight, record:

- feed name
- download URL tested
- whether it passed or was skipped
- exact docs used
- exact ordered source fields from the data dictionary
- expected row width
- canonical business concept represented by the feed
- chosen canonical table name
- typed columns
- raw source row preservation plan
- required source metadata columns, including `feed_date`
- row identity / rerun idempotency strategy
- any feed-specific semantic caveats

Additional required investigation:

- confirm whether `SMS Input - Crash` dataset ID `gwak-5bwn` is correct by checking the authoritative about-page/doc context before you trust that URL
- compare the returned file for `SMS C PassProperty` and `SMS C Pass`
- if they return the same file, keep only one ingestion path, skip the duplicate, and explain the decision in the mapping doc

Hard requirements:

- Any feed that fails preflight must be skipped from the implementation deliverables below.
- Do not guess a contract for a feed whose URL or dataset identity is still ambiguous.
- Table names must follow `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.

Commit standalone.

### Deliverable 2: Extend the Shared FMCSA Ingestion Workflow and Scheduled Tasks

For every feed that passed Deliverable 1, extend the existing FMCSA ingestion workflow pattern.

Create or update the necessary Trigger task files under `trigger/src/tasks/`.

Requirements:

- reuse `trigger/src/workflows/fmcsa-daily-diff.ts` if it can cleanly support these SMS feeds
- do not create a second parallel FMCSA ingestion framework unless the existing shared workflow is truly incompatible; if you discover such incompatibility, stop and report before forking the architecture
- each valid feed must download via direct HTTP `GET`
- each valid feed must parse the source as a `text/plain` file whose contents are CSV-formatted quoted rows with no header
- validate row width against the contract from Deliverable 1
- preserve `feed_date`
- use confirmed writes through the existing internal API client and persistence helpers
- create real daily Trigger.dev cron tasks in code for each valid feed
- stagger schedules rather than firing all tasks at the same minute
- do not wire any of this through `run-pipeline.ts`

If one of the two `SMS C Pass*` feeds is skipped because the source file is identical, only create one task for the surviving feed.

Commit standalone.

### Deliverable 3: Persistence Path for Valid SMS Feeds

Build or extend the FastAPI persistence layer for the SMS feeds that passed preflight.

Create or update:

- one or more migrations in `supabase/migrations/`
- service modules in `app/services/`
- internal batch upsert endpoints in `app/routers/internal.py`

Persistence requirements:

- write to `entities`
- preserve every source row as observed for the given `feed_date`
- no business-level deduplication at ingestion time
- include `feed_date`
- preserve source-row identity sufficient for idempotent same-day reruns
- preserve typed business columns
- preserve raw source row payload
- preserve source metadata such as feed name, download URL, source variant, and run metadata
- keep confirmed-write semantics consistent with the prior FMCSA batches

Design constraints:

- choose canonical table names by data concept, not FMCSA shorthand
- if multiple SMS feeds represent the same underlying business concept with materially identical row structures, shared-table storage is allowed
- if structures differ or combining feeds would make downstream meaning ambiguous, use separate tables
- document whichever choice you make in Deliverable 1 and keep the implementation aligned with it

Commit standalone.

### Deliverable 4: Tests and Regression Coverage

Add or extend tests to verify the SMS-feed behavior.

At minimum, cover:

- preflight validation handling for a valid data file
- skip behavior for an invalid/non-data download response
- `SMS Input - Crash` dataset-ID verification logic or the resulting skip path if verification fails
- duplicate-file handling for `SMS C Pass` vs `SMS C PassProperty`
- parsing of representative SMS feeds
- row-width validation for representative feeds
- scheduling/task existence for all implemented feeds
- preservation of `feed_date`
- preservation of raw source rows
- no business-level deduplication at ingestion time
- idempotent same-`feed_date` rerun behavior using source-row identity
- coexistence of different `feed_date` snapshots for the same business row

Mock all HTTP calls and Trigger.dev behavior. Do not hit live FMCSA endpoints in tests.

Commit standalone.

---

**What is NOT in scope:** No browser automation. No Socrata JSON API as the primary ingestion path. No redesign of the existing FMCSA row-oriented storage semantics. No conversion of SMS feeds into deduplicated current-state company/person/job entity tables. No changes to `trigger/src/tasks/run-pipeline.ts`. No public query endpoints unless strictly required to validate internal architecture. No deploy commands. No downstream analytics or matching projects that join every SMS row to `company_entities`.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_SMS_FEEDS_PREFLIGHT_AND_MAPPINGS.md`, (b) the preflight result for each requested feed and which ones were skipped, (c) the outcome of the `gwak-5bwn` verification for `SMS Input - Crash`, (d) whether `SMS C Pass` and `SMS C PassProperty` returned the same file and which one, if any, was skipped, (e) the canonical table decision for each implemented feed, (f) the migration file paths created or updated, (g) the internal endpoint paths added or extended, (h) the Trigger task IDs and schedules for all implemented feeds, (i) the exact storage semantics for `feed_date` and source-row identity, and (j) anything to flag — especially any ambiguous SMS dictionary semantics or any feed that had to be skipped because the source download was not actually valid data.
