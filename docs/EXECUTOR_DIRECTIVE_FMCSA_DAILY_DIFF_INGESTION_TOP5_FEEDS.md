# Directive: FMCSA Daily Diff Ingestion Workflows — Top 5 Feeds

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** FMCSA daily diff files are confirmed downloadable via direct public HTTP GET. The repo now contains usable data dictionaries for the five highest-signal feeds for the factoring/insurance use case: `AuthHist`, `Revocation`, `Insurance`, `ActPendInsur`, and `InsHist`. The goal is to ingest those five feeds daily via Trigger.dev scheduled tasks, parse the quoted comma-delimited no-header files, and persist canonical records into the `entities` schema with `first_observed_at` and `last_observed_at` so the system can detect when a public-signal row first appeared and when it was last re-seen.

This directive is intentionally narrower than the older broad FMCSA ingestion directive. The remaining three daily diff feeds (`Carrier`, `BOC3`, `Rejected`) are follow-on work only after these five are working end-to-end.

## External Feed Contract

All five feeds in scope are direct-download text files:

- transport: direct HTTP `GET`
- auth: none
- browser automation: forbidden
- primary format: quoted comma-delimited text rows
- header row: none
- cadence: daily (FMCSA docs target daily updates by `9:30 AM US Eastern Time`)

Top-5 feed inventory:

- `AuthHist`
  - download URL: `https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/08-authhist-daily-difference-daily-diff/`
- `Revocation`
  - download URL: `https://data.transportation.gov/download/pivg-szje/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/`
- `Insurance`
  - download URL: `https://data.transportation.gov/download/mzmm-6xep/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/`
- `ActPendInsur`
  - download URL: `https://data.transportation.gov/download/chgs-tx6x/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/07-actpendinsur-daily-difference-daily-diff/`
- `InsHist`
  - download URL: `https://data.transportation.gov/download/xkmg-ff2t/text%2Fplain`
  - docs folder: `docs/api-reference-docs/fmcsa-open-data/10-inshist-daily-diff/`

Documentation rule:

- Use `data-dictionary.json` as the exact source of column positions, names, and field counts.
- Use `overview-data-dictionary.md` as supporting semantic context.
- If the two conflict, do not guess. Stop and report the conflict before coding around it.

Critical feed-specific semantics to preserve:

- `Insurance` daily diff uses blank/zeroed rows to signal policy removals; the ingestion path must preserve that deletion/removal signal rather than silently discarding it as malformed noise.
- `AuthHist` is authority lifecycle history, not current authority state.
- `Revocation` is authority revocation-event/history data, not a carrier snapshot.
- `ActPendInsur` is active/pending insurance timing and filing state, not the same concept as current active insurance policy inventory.
- `InsHist` is historical outgoing insurance-policy state (cancelled/replaced/name-changed/transferred), not the replacement/current policy.

## Existing code to read

- `CLAUDE.md` — project conventions, Trigger/FastAPI boundary, deploy protocol, current migration rules
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule and persistence guardrails
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — canonical naming and schema rules for entity/intelligence tables
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — why silent persistence is unacceptable and why dedicated workflows should use confirmed writes
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — current production baseline and Trigger state context
- `docs/EXECUTOR_DIRECTIVE_FMCSA_DAILY_DIFF_INGESTION.md` — prior broader FMCSA directive; use only as background, not as the scope boundary for this work
- `docs/api-reference-docs/fmcsa-open-data/08-authhist-daily-difference-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/08-authhist-daily-difference-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/07-actpendinsur-daily-difference-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/07-actpendinsur-daily-difference-daily-diff/overview-data-dictionary.md`
- `docs/api-reference-docs/fmcsa-open-data/10-inshist-daily-diff/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/10-inshist-daily-diff/overview-data-dictionary.md`
- `app/database.py` — schema-aware DB routing
- `app/providers/fmcsa.py` — existing FMCSA provider conventions and normalization style
- `app/routers/internal.py` — internal batch upsert endpoint patterns
- `app/services/icp_job_titles.py` — simple dedicated-table upsert/query pattern
- `app/services/company_customers.py` — bulk upsert pattern with typed fields + raw input handling
- `app/services/company_ads.py` — raw-payload preservation pattern
- `trigger/package.json` — Trigger.dev SDK version
- `trigger/src/workflows/internal-api.ts` — internal authenticated HTTP client pattern
- `trigger/src/workflows/persistence.ts` — confirmed-write helpers
- `trigger/src/tasks/icp-job-titles-discovery.ts` — minimal dedicated task entrypoint pattern
- `trigger/src/workflows/icp-job-titles-discovery.ts` — dedicated workflow + confirmed-write reference

---

### Deliverable 1: Contract Lock and Canonical Table Plan

Create `docs/FMCSA_TOP5_DAILY_DIFF_MAPPINGS.md`.

For each of the five feeds in scope, record:

- feed name
- direct download URL
- data-dictionary file path
- overview file path
- exact ordered source fields from the data dictionary
- row width expected in the raw file
- chosen canonical table name in the `entities` schema, named for the business concept rather than the feed label
- chosen typed columns
- how raw row payload and source metadata will be preserved
- dedup/idempotency key for the canonical record
- how `first_observed_at` and `last_observed_at` will behave
- whether the dataset is global or tenant-scoped, with justification
- whether nullable linkage to existing entities is appropriate now or explicitly deferred
- any special handling required for feed-specific semantics such as removals, cancellations, or multiple records per entity

Hard requirements:

- Table names must follow `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`. Do not name tables after the feed labels themselves if the feed label is just an FMCSA source shorthand.
- These are public FMCSA signal tables, not tenant-generated research results. Default to global tables in `entities` unless you find a real platform constraint that forces tenant scoping. If you do, report it explicitly.
- Do not collapse distinct historical/event rows into a current snapshot model.
- Do not start migrations or workflow code until this file is complete enough to eliminate guesswork.

Commit standalone.

### Deliverable 2: Shared Ingestion Foundation

Build the shared ingestion path for these daily diff feeds.

Create:

- `trigger/src/workflows/fmcsa-daily-diff.ts`
- `trigger/src/tasks/fmcsa-authhist-daily.ts`
- `trigger/src/tasks/fmcsa-revocation-daily.ts`
- `trigger/src/tasks/fmcsa-insurance-daily.ts`
- `trigger/src/tasks/fmcsa-actpendinsur-daily.ts`
- `trigger/src/tasks/fmcsa-inshist-daily.ts`

The shared workflow must:

- download the feed via direct HTTP GET
- parse quoted comma-delimited no-header rows using a robust CSV-capable parser
- validate row width against the feed contract from Deliverable 1
- surface non-200 responses, empty bodies, malformed rows, and column-count mismatches as failures
- produce a normalized batch payload for FastAPI persistence
- use the existing internal API client and confirmed-write helpers so a persistence failure fails the workflow
- return a run summary including at minimum feed name, rows downloaded, rows parsed, rows accepted, rows rejected, and rows written

Scheduling requirements:

- each of the five task files must be a real daily Trigger.dev scheduled task committed in code
- stagger schedules rather than firing all five feeds at the same minute
- do not wire any of this through `run-pipeline.ts`

Commit standalone.

### Deliverable 3: Entities Schema Persistence for the Top 5 Feeds

Build the canonical persistence path for the five feeds in scope.

Create:

- one or more new migrations in `supabase/migrations/` for the canonical `entities` tables chosen in Deliverable 1
- one service module per canonical concept in `app/services/`, named consistently with the chosen concept
- internal batch upsert endpoints in `app/routers/internal.py` for each canonical concept

Persistence requirements for every top-5 concept:

- write to `entities`
- preserve typed business columns from the FMCSA contract
- preserve raw source row payload
- preserve source metadata at minimum:
  - feed name
  - download URL
  - source file variant (`daily diff`)
  - observed-at/run metadata sufficient for lineage
- include `first_observed_at` and `last_observed_at`
- include `created_at` and `updated_at`
- make reruns idempotent at the canonical-record level

Design constraints:

- `Insurance` and `ActPendInsur` are related but not identical concepts. Do not merge them into a single table unless the contract-lock work proves that is semantically correct.
- `InsHist` is historical outgoing insurance state and should remain distinct from current active/pending insurance state.
- `Revocation` and `AuthHist` are authority-history concepts and should not be flattened into a current authority flag table.
- Do not block ingestion on matching rows to existing `company_entities`. If nullable future linkage is useful, keep it additive and non-blocking.
- Keep raw payloads out of entity records intended to serve as current best-known company/person/job state. These canonical FMCSA concept tables may keep raw-row payloads because they are dedicated intelligence/history tables, not the core company/person/job entity tables.

Commit standalone.

### Deliverable 4: Tests and Failure-Mode Coverage

Add explicit tests for both the FastAPI persistence layer and the Trigger workflow layer.

At minimum, cover:

- parsing of quoted comma-delimited no-header rows
- row-width validation per feed
- non-200 HTTP handling
- empty-body handling
- malformed-row handling
- confirmed-write failure propagation from Trigger to workflow failure
- idempotent rerun behavior with `first_observed_at` preserved and `last_observed_at` updated
- `Insurance` daily-diff blank-row removal handling
- one representative successful persistence path for each of the five feeds
- existence of all five scheduled tasks and their feed-to-URL mapping

Mock all HTTP calls and Trigger.dev behavior. Do not hit live FMCSA endpoints in tests.

Commit standalone.

---

**What is NOT in scope:** No browser automation. No Socrata JSON API as the primary ingestion path. No `Carrier`, `BOC3`, or `Rejected` daily diff ingestion in this directive. No full-snapshot “All With History” ingestion. No changes to `trigger/src/tasks/run-pipeline.ts`. No public query endpoints unless strictly required to validate the new tables inside this repo’s existing architecture. No broad entity-linkage project tying every FMCSA row to `company_entities`. No deploy commands. No production backfill beyond whatever minimal local/dev validation is required for tests.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_TOP5_DAILY_DIFF_MAPPINGS.md`, (b) the final canonical table names chosen for all five feeds and why, (c) the migration file paths created, (d) the internal endpoint paths added, (e) the Trigger task IDs and daily schedules for all five feeds, (f) how `first_observed_at` and `last_observed_at` behave for reruns, (g) how `Insurance` blank-row removals are represented, (h) test count and what each test covers, and (i) anything to flag — especially any ambiguity left in FMCSA semantics, any forced tenant-scoping decision, or any Trigger.dev scheduling limitation discovered in the current SDK.
