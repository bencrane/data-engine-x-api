# Directive: FMCSA Daily Diff Ingestion System

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** FMCSA daily diff feeds are already proven to be downloadable via direct public HTTP GET from `https://data.transportation.gov/download/{dataset_id}/text%2Fplain`. We do not need browser automation, cookies, or interactive scraping. The goal is to bring these public daily trucking-signal feeds into `data-engine-x-api` as dedicated entity-database ingestion paths with confirmed writes and scheduled Trigger.dev cron tasks, starting with Revocation as the proof of concept and then extending the same architecture to the remaining feeds.

## External Feed Contract

Daily diff download rule:

- Use direct HTTP GET only.
- URL shape: `https://data.transportation.gov/download/{dataset_id}/text%2Fplain`
- No browser automation.
- No session/cookie flow.
- No auth.
- Do not use the Socrata JSON API as the primary ingestion path for this directive.

Feed inventory in scope:

- `Revocation` — `https://data.transportation.gov/download/pivg-szje/text%2Fplain`
- `Insurance` — `https://data.transportation.gov/download/mzmm-6xep/text%2Fplain`
- `Carrier` — `https://data.transportation.gov/download/6qg9-x4f8/text%2Fplain`
- `Rejected` — `https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain`
- `ActPendInsur` — `https://data.transportation.gov/download/chgs-tx6x/text%2Fplain`
- `AuthHist` — `https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain`
- `BOC3` — `https://data.transportation.gov/download/fb8g-ngam/text%2Fplain`
- `InsHist` — `https://data.transportation.gov/download/xkmg-ff2t/text%2Fplain`

Confirmed Revocation row shape:

- No header row
- Comma-delimited text
- Fields are quoted
- Sample business columns:
  - MC number
  - DOT number
  - authority type
  - authority date
  - revocation type
  - revocation date
- File size expectation is small enough for daily scheduled download. The confirmed sample was about `5,000` rows.

Column-mapping rule for all non-Revocation feeds:

- You must determine the exact business meaning and column order from the FMCSA data-definitions PDF linked on each feed’s public about page.
- Do not guess field meaning from feed names alone.
- If any PDF is ambiguous enough that the table name, typed columns, or dedup key would be guesswork, stop and report instead of inventing a schema.

## Existing code to read

- `CLAUDE.md` — project conventions, production truth, Trigger/FastAPI boundary, and the instruction to avoid adding new work to `run-pipeline.ts`
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule and persistence guardrails
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — naming, attribution, global-entity rules, additive schema rules
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — known dedicated-write failure modes and why confirmed writes matter
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — confirms there are currently no in-repo cron definitions and shows the dedicated-table reliability context
- `docs/SYSTEM_OVERVIEW.md` — existing FMCSA context and the note that FMCSA daily feeds currently live in a separate repo
- `research.md` — dataset IDs and current FMCSA feed inventory notes
- `app/providers/fmcsa.py` — existing FMCSA provider conventions and field-normalization style
- `app/routers/internal.py` — existing internal batch/dedicated upsert endpoint patterns
- `app/services/icp_job_titles.py` — simplest dedicated table upsert/query pattern
- `app/services/company_customers.py` — dedicated table bulk upsert pattern
- `app/services/company_ads.py` — dedicated table raw-payload preservation pattern
- `trigger/package.json` — Trigger.dev SDK version
- `trigger/src/workflows/internal-api.ts` — internal authenticated HTTP client pattern
- `trigger/src/workflows/persistence.ts` — confirmed-write helpers; do not introduce silent persistence
- `trigger/src/tasks/icp-job-titles-discovery.ts` — simplest dedicated task entrypoint pattern
- `trigger/src/workflows/icp-job-titles-discovery.ts` — dedicated workflow + confirmed-write reference

---

### Deliverable 1: Feed Mapping and Canonical Table Plan

Create `docs/FMCSA_DAILY_DIFF_FEED_MAPPINGS.md`.

For each of the eight feeds in scope, record:

- feed name
- Socrata dataset ID
- direct download URL
- public about page URL
- data-definitions PDF URL
- whether the file has a header row
- exact ordered source columns from the official PDF
- chosen canonical table name, named for the data concept and not the feed label
- chosen typed columns
- dedup key for rerun idempotency
- whether the table is global or tenant-scoped, with justification
- whether nullable linkage to `company_entities` is possible now or should stay out of scope
- any ambiguities or unresolved mapping questions

Design requirements:

- Revocation should be modeled as an event/history table, not as a current-state carrier snapshot.
- These public FMCSA daily diff rows are real-world public-signal data, not tenant-generated research output. Default to global tables rather than `org_id`-scoped tables unless you discover a real, existing platform constraint that forces tenant scoping. If you find such a constraint, report it explicitly before coding around it.
- Table names must describe what the data is. Do not create tables named `fmcsa_revocation`, `authhist_feed`, or similar source-shaped names.
- Provider/source attribution belongs in metadata columns, not in table names.

This deliverable is the contract lock. Do not start migrations or workflow code until this file is complete enough to remove guesswork.

Commit standalone.

### Deliverable 2: Revocation Proof of Concept End-to-End

Build the full vertical slice for Revocation first.

Create:

- `supabase/migrations/022_operating_authority_revocations.sql`
- `app/services/operating_authority_revocations.py`
- additions to `app/routers/internal.py` for a dedicated internal batch upsert endpoint
- `trigger/src/workflows/fmcsa-daily-diff.ts`
- `trigger/src/tasks/fmcsa-revocation-daily.ts`

Revocation table intent:

- Use a canonical business table for operating-authority revocation events.
- Store typed business columns for the six confirmed Revocation fields.
- Store source metadata such as dataset ID, download URL, and a preserved raw-row payload.
- Include standard timestamps.
- Make reruns idempotent by deduplicating the event row itself, not the carrier generally.
- Do not collapse distinct historical events into a single carrier snapshot row.

Internal API contract for the Revocation write path:

- Add a dedicated internal endpoint under `/api/internal/*`.
- The request must carry a batch of parsed revocation rows plus source metadata identifying the FMCSA dataset and download URL used for that run.
- The response must make write confirmation possible. It should return at minimum enough information to prove the batch landed and how many rows were persisted.

Trigger workflow requirements:

- Download the file via direct HTTP GET from the public FMCSA URL.
- Parse the file as quoted comma-delimited text with no header row.
- Use a real CSV-capable parser or an equivalently robust parser. Do not split on commas manually.
- Fail the workflow on non-200 responses, empty bodies, malformed rows, or column-count mismatches.
- Use the existing internal API client and confirmed-write helper so persistence failures surface as workflow failures.
- Return a run summary that includes at minimum the feed name, dataset ID, rows downloaded, rows parsed, rows written, and any validation failures.

Scheduling requirements:

- The Revocation task must be a real Trigger.dev scheduled cron task committed in code.
- Run it daily.
- Do not wire this through `run-pipeline.ts`.

Commit standalone.

### Deliverable 3: Extend the Same System to the Remaining Daily Diff Feeds

After Revocation is working end-to-end, extend the same architecture to:

- `Insurance`
- `Carrier`
- `Rejected`
- `ActPendInsur`
- `AuthHist`
- `BOC3`
- `InsHist`

Requirements:

- Reuse `trigger/src/workflows/fmcsa-daily-diff.ts` as the shared workflow body. Do not duplicate eight separate workflow implementations.
- Create one daily Trigger.dev cron task per feed.
- Stagger the cron schedules so all eight feeds do not fire at the same minute.
- For each feed, add the necessary migration and FastAPI persistence module(s) named after the chosen canonical data concept from Deliverable 1.
- For each feed, add a dedicated internal batch upsert endpoint under `/api/internal/*`.
- Preserve raw row payloads separately from typed business columns.
- Make each feed rerunnable without creating duplicate rows for the same event record.
- If two feeds describe the same business concept at different lifecycle stages, do not merge them blindly into one table unless the official PDFs and field semantics clearly support that choice.

Architecture constraints:

- Keep the shared ingestion logic small and explicit. A thin shared workflow plus concept-specific persistence is preferred over one giant generic branch table.
- Do not introduce browser automation.
- Do not introduce a separate orchestration stack outside Trigger.dev.
- Do not silently skip bad rows. Either validate and reject them explicitly with surfaced counts, or fail the run if the feed shape is broken enough that the batch is not trustworthy.

Commit standalone.

### Deliverable 4: Tests and Failure-Mode Coverage

Add test coverage for both the FastAPI persistence layer and the Trigger workflow layer.

At minimum, cover:

- Revocation parsing from quoted no-header rows
- idempotent rerun behavior for Revocation
- HTTP non-200 handling
- empty-body handling
- malformed row-width handling
- confirmed-write failure propagation from Trigger to workflow failure
- correct feed-to-dataset mapping for all scheduled tasks
- per-feed schedule existence for all eight feeds
- at least one representative non-Revocation feed mapping and persistence path beyond Revocation itself

Testing constraints:

- Mock all HTTP calls.
- Mock Trigger.dev SDK behavior where appropriate.
- Do not hit live FMCSA endpoints in tests.
- Do not rely on production data.

Commit standalone.

---

**What is NOT in scope:** No browser automation. No Vehicle Inspection File work. No full-snapshot ingestion of the FMCSA historical tables. No use of the Socrata JSON API as the primary ingestion mechanism. No changes to `trigger/src/tasks/run-pipeline.ts`. No public query endpoints unless you discover they are strictly required to validate or consume the new tables inside this repo’s existing architecture. No broad company-entity resolution project for every FMCSA row. Do not block ingestion on matching every row to `company_entities`; if nullable future linkage is useful, keep it additive and non-blocking. No deploy commands. No production backfill unless you discover a small, clearly necessary seed step to prove idempotency locally.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_DAILY_DIFF_FEED_MAPPINGS.md`, (b) the final canonical table names chosen for all eight feeds and why, (c) the exact internal endpoint paths added, (d) the Trigger task IDs and cron schedules for all eight feeds, (e) the proof-of-concept Revocation ingestion behavior and dedup key, (f) the files changed for the remaining feeds, (g) test count and what each test covers, and (h) anything to flag — especially any ambiguous FMCSA PDF mappings, any reason a table had to be tenant-scoped, or any Trigger.dev scheduling limitation discovered in the current SDK.
