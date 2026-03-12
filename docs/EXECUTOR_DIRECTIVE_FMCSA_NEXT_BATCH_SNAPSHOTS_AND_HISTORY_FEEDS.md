# Directive: FMCSA Next Batch Ingestion — Snapshot and All-With-History Feeds

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The first FMCSA batch established the ingestion pattern: direct HTTP `GET` of `text/plain` source files, robust parsing of quoted comma-delimited no-header rows, confirmed writes through FastAPI internal endpoints, and daily Trigger.dev scheduled tasks. This directive extends that pattern to the next batch of FMCSA feeds. Important correction to preserve in design: the government labels some of these feeds as “daily diff,” but for our purposes you must treat them as full snapshot files to be stored as observed for each `feed_date`, not as business-diff streams to be deduplicated or merged at ingestion time. The “All With History” variants are separate source artifacts that include historical records.

## Source Feed Inventory

These are source `text/plain` downloads, not `.csv` files by extension, even though their contents are CSV-formatted quoted comma-delimited rows with no header row.

### Daily feeds in scope

- `Carrier`
  - download URL: `https://data.transportation.gov/download/6qg9-x4f8/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/`
- `Rejected`
  - download URL: `https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/06-rejected-daily-diff/`
- `BOC3`
  - download URL: `https://data.transportation.gov/download/fb8g-ngam/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/09-boc3-daily-diff/`

### All With History feeds in scope

- `InsHist - All With History`
  - download URL: `https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/12-inshist-all-with-history/`
- `BOC3 - All With History`
  - download URL: `https://data.transportation.gov/download/gmxu-awv7/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/13-boc3-all-with-history/`
- `ActPendInsur - All With History`
  - download URL: `https://data.transportation.gov/download/y77m-3nfx/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/14-actpendinsur-all-with-history/`
- `Rejected - All With History`
  - download URL: `https://data.transportation.gov/download/9m5y-imtw/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/15-rejected-all-with-history/`
- `AuthHist - All With History`
  - download URL: `https://data.transportation.gov/download/wahn-z3rq/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/`

Common transport/parse contract for all feeds:

- direct HTTP `GET`
- no auth
- no browser automation
- no Socrata JSON API as the primary ingestion path
- source file is `text/plain`
- contents are quoted comma-delimited rows
- no header row
- parse with a real CSV-capable parser

Critical ingestion semantic for this directive:

- store every source row tagged with `feed_date`
- do not do business-level deduplication at ingestion time
- preserve row order / row identity for rerun idempotency
- treat daily files as full snapshots as observed, not as true semantic diffs

That means the first-batch notion of rerun safety still applies, but it must remain source-row-oriented, not concept-dedup-oriented. The executor should preserve the same ingestion semantics already established by the first batch: reruns for the same `feed_date` should update the same source-row slot, while different `feed_date` values produce distinct stored observations.

## Existing code to read

- `CLAUDE.md` — project conventions, Trigger/FastAPI boundary, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule and persistence guardrails
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — concept-based table naming, additive schema rules, no provider/source names in table names
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — confirmed writes and no-silent-failure requirement
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — Trigger baseline/context
- `docs/EXECUTOR_DIRECTIVE_FMCSA_DAILY_DIFF_INGESTION_TOP5_FEEDS.md` — first-batch directive; this is the reference scope and pattern to extend
- `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/06-rejected-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/06-rejected-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/09-boc3-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/09-boc3-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/12-inshist-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/12-inshist-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/13-boc3-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/13-boc3-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/14-actpendinsur-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/14-actpendinsur-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/15-rejected-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/15-rejected-all-with-history/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/overview-data-dictionary.md`
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — first-batch table design reference
- `app/services/fmcsa_daily_diff_common.py` — shared persistence/parsing semantics from the first batch
- `app/services/insurance_policies.py`
- `app/services/insurance_policy_filings.py`
- `app/services/insurance_policy_history_events.py`
- `app/services/operating_authority_revocations.py`
- `app/services/operating_authority_histories.py` if present in the repo; if the symbol exists but the file path differs, locate and use the real file
- `app/routers/internal.py` — first-batch internal batch upsert endpoints
- `app/database.py` — schema-aware DB routing
- `trigger/src/workflows/fmcsa-daily-diff.ts` — shared Trigger workflow built in batch one
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

### Deliverable 1: Contract Lock for the Next Batch

Create `docs/FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_MAPPINGS.md`.

For each feed in scope, record:

- source feed name
- source variant (`daily` vs `all_with_history`)
- direct download URL
- exact source docs used
- exact ordered source fields from the data dictionary
- row width expected in the raw file
- canonical business concept represented by the feed
- chosen canonical table name
- whether the feed should write into an existing first-batch table or a new table
- if reusing an existing table, why the structures and semantics are compatible
- if using a new table, why the structures or semantics differ enough to require separation
- typed columns
- raw source row preservation plan
- required source metadata columns, including `feed_date`
- row identity / rerun idempotency strategy
- any source-specific semantic caveats

This deliverable must explicitly answer the design question:

- should the `All With History` feeds share tables with their daily counterparts or not?

Decision rule:

- do not decide by feed-name similarity alone
- compare the actual dictionaries and row semantics
- if structure and meaning are materially identical, shared-table storage is allowed
- if structure differs, or if mixing snapshot rows and all-history rows in one table would make downstream interpretation ambiguous, split the tables

Hard requirements:

- Table names must follow `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.
- Do not name a table after a source shorthand if the table is really modeling a broader concept.
- Do not collapse source rows into deduplicated current-state records at ingestion time.
- Preserve the “store everything as-is by feed_date” rule.

Commit standalone.

### Deliverable 2: Extend the Shared FMCSA Ingestion Workflow and Scheduled Tasks

Extend the existing first-batch shared workflow pattern rather than creating a second parallel ingestion framework.

Create or update the necessary Trigger task files under `trigger/src/tasks/` for:

- `Carrier` daily
- `Rejected` daily
- `BOC3` daily
- `InsHist - All With History`
- `BOC3 - All With History`
- `ActPendInsur - All With History`
- `Rejected - All With History`
- `AuthHist - All With History`

Requirements:

- reuse `trigger/src/workflows/fmcsa-daily-diff.ts` if it can cleanly support both daily and all-history variants
- if the current shared workflow name is too daily-specific but the implementation can be generalized, extend/refactor it narrowly rather than duplicating a new workflow body
- each feed must download via direct HTTP `GET`
- each feed must parse the source as a `text/plain` file whose contents are CSV-formatted quoted rows with no header
- validate row width against the contract from Deliverable 1
- preserve feed-level metadata including `feed_date`
- use confirmed writes through the existing internal API client and persistence helpers
- create real scheduled Trigger.dev daily cron tasks in code
- stagger schedules rather than firing all tasks at the same minute
- do not wire any of this through `run-pipeline.ts`

Commit standalone.

### Deliverable 3: Persistence Path for the Next Batch Feeds

Build or extend the FastAPI persistence layer for the next batch.

Create or update:

- one or more new migrations in `supabase/migrations/`
- service modules in `app/services/` for the chosen canonical concepts
- internal batch upsert endpoints in `app/routers/internal.py`

Persistence requirements:

- write to `entities`
- preserve every row as observed for the given `feed_date`
- no business-level deduplication at ingestion time
- include `feed_date`
- preserve row-position or equivalent source-row identity sufficient for idempotent same-day reruns
- preserve typed business columns
- preserve raw source row payload
- preserve source metadata such as feed name, download URL, source variant, and run metadata
- keep confirmed-write semantics consistent with the first batch

Important semantics:

- `Carrier` daily is a snapshot-style carrier feed; do not convert it into a “changed fields only” model
- `Rejected` daily is a row-level rejected-filing snapshot feed; store all rows as observed
- `BOC3` daily is a row-level process-agent snapshot feed; store all rows as observed
- `All With History` feeds should also store all rows as observed for their run date; they are full historical source snapshots, not deduped entity histories at ingestion time

Commit standalone.

### Deliverable 4: Tests and Regression Coverage

Add or extend tests to verify the next-batch behavior.

At minimum, cover:

- the new feed-to-dictionary mappings
- parsing of the new daily and all-history feeds
- row-width validation for representative feeds
- scheduling/task existence for all new feeds
- preservation of `feed_date`
- preservation of raw source rows
- no business-level deduplication at ingestion time
- idempotent same-`feed_date` rerun behavior using source-row identity
- coexistence of different `feed_date` snapshots for the same business row
- at least one representative shared-table case if you choose to share tables
- at least one representative separate-table case if you choose to split tables

Mock all HTTP calls and Trigger.dev behavior. Do not hit live FMCSA endpoints in tests.

Commit standalone.

---

**What is NOT in scope:** No browser automation. No Socrata JSON API as the primary ingestion path. No redesign of the first-batch storage semantics away from feed-date-tagged row storage. No conversion of these feeds into deduplicated current-state company/person/job entity tables. No changes to `trigger/src/tasks/run-pipeline.ts`. No public query endpoints unless strictly required to validate internal architecture for these new tables. No deploy commands. No consumption-layer analytics or downstream matching projects that join every FMCSA row to `company_entities`.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_NEXT_BATCH_SNAPSHOT_HISTORY_MAPPINGS.md`, (b) the canonical table decision for each feed, especially whether each all-history variant shares or does not share a table with its daily counterpart, (c) the migration file paths created or updated, (d) the internal endpoint paths added or extended, (e) the Trigger task IDs and schedules for all new feeds, (f) the exact storage semantics for `feed_date` and source-row identity, (g) test count and what each test covers, and (h) anything to flag — especially any dictionary mismatches between daily and all-history variants or any ambiguity that made shared-table storage unsafe.
