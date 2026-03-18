# data-engine-x Architecture

**Last updated:** 2026-03-18T06:30:00Z

Ground-truth architecture note as of `2026-03-18`.

This document is not aspirational. It describes the production system that actually exists, the parts that are healthy, and the parts that are broken.

## 1. Runtime Boundary

`data-engine-x-api` currently runs as a split system:

- `FastAPI` owns auth, request validation, `/api/v1/*`, `/api/internal/*`, and database writes.
- `Trigger.dev` owns orchestration in `trigger/src/tasks/run-pipeline.ts`.
- `Supabase/Postgres` is the production system of record.

The active execution loop is:

1. `POST /api/v1/batch/submit`
2. create `submissions` + `pipeline_runs`
3. trigger `run-pipeline`
4. execute steps
5. merge step outputs into cumulative context
6. optionally fan out child runs
7. write entity state
8. write timeline / snapshots

That loop is real in production.

## 2. Production Database Shape

Production is still running in `public`.

There is no live `ops` schema and no live `entities` schema yet.

Observed production application tables live in `public`, including:

- `submissions`
- `pipeline_runs`
- `step_results`
- `operation_runs`
- `operation_attempts`
- `company_entities`
- `person_entities`
- `job_posting_entities`
- `entity_timeline`
- `entity_snapshots`
- `icp_job_titles`
- `company_intel_briefings`
- `person_intel_briefings`
- `company_customers`
- `gemini_icp_job_titles`
- `salesnav_prospects`

Important drift:

- `company_ads` does not exist in production even though the repo contains `supabase/migrations/019_company_ads.sql`.

## 3. What Works in Production

Core infrastructure with live evidence:

- `48` `submissions`
- `837` `pipeline_runs`
- `3283` `step_results`
- `1899` `operation_runs`
- `88` `company_entities`
- `503` `person_entities`
- `1` `job_posting_entities`
- `4345` `entity_timeline`
- `93` `entity_snapshots`

Healthy end-to-end blueprint paths:

- `AlumniGTM Company Resolution Only v1` - `2` completed submissions
- `AlumniGTM Company Workflow v1` - `5`
- `AlumniGTM Prospect Discovery v1` - `1`
- `Company Intel Briefing v1` - `3`
- `ICP Job Titles Discovery v1` - `3`
- `Person Intel Briefing v1` - `1`
- `Company Enrichment + Person Enrichment Fan Out` - `1`
- `Staffing Enrichment v1` - `1`

Healthy dedicated persistence:

- `icp_job_titles`
- `company_intel_briefings`
- `person_intel_briefings`

## 4. What Is Broken in Production

Broken materialization paths:

- `company_customers` - successful upstream steps, `0` rows in table
- `gemini_icp_job_titles` - successful upstream steps, `0` rows in table
- `salesnav_prospects` - successful upstream steps, `0` rows in table
- `company_ads` - table missing entirely in prod

Broken runtime state:

- `8` `pipeline_runs` stuck in `running`
- `7` `step_results` stuck in `running`
- `190` `step_results` still `queued`

Reliability problem:

- Pipeline success is not trustworthy as a proxy for data landing correctly.
- Dedicated-table failures can be swallowed while step execution still looks successful.
- Some persistence branches are broken by context shape mismatches, not by provider failure.

## 5. What Has Never Been Used

The executable code catalog currently contains `82` operations:

- `78` from `app/routers/execute_v1.py`
- `4` Trigger-direct operations in `run-pipeline.ts`

Only `36` have ever been called in production.

Never-used production surfaces include:

- `46` never-called operations from the executable code catalog
- `entity_relationships` table has `0` rows
- `extracted_icp_job_title_details` table has `0` rows
- several blueprints have never been used at all:
  - `AlumniGTM Prospect Resolution v1`
  - `Phase6 Blueprint 1771280001`
  - `Revenue Activation / CRM Cleanup v1`
  - `Revenue Activation / CRM Enrichment v1`
  - `Revenue Activation / Staffing Enrichment v1`
  - `Staffing Activation / CRM Cleanup v1`
  - `Staffing Activation / CRM Enrichment v1`

## 6. Implications for the Schema Split

Any `public` -> `ops` / `entities` split must preserve the paths that are actually healthy today:

- `submissions`
- `pipeline_runs`
- `step_results`
- `operation_runs`
- `operation_attempts`
- `company_entities`
- `person_entities`
- `job_posting_entities`
- `entity_timeline`
- `entity_snapshots`
- `icp_job_titles`
- `company_intel_briefings`
- `person_intel_briefings`

Do not treat these already-broken paths as regressions introduced by the schema split:

- `company_customers`
- `gemini_icp_job_titles`
- `salesnav_prospects`
- `company_ads`

Those need explicit repair work regardless of the schema move.

## 7. Known Architectural Problems

### 1. Auto-persist silent failures

This is the worst architectural flaw in the current production system.

`run-pipeline.ts` wraps dedicated-table writes in `try/catch` and logs warnings instead of failing the run. That means:

- the pipeline can look successful
- `step_results` can contain valid output
- the dedicated table can still be empty

This is not theoretical. Production shows it for:

- `company_customers`
- `gemini_icp_job_titles`

### 2. `run-pipeline.ts` is a monolith

The orchestrator owns too many responsibilities at once:

- step dispatch
- direct-provider execution
- cumulative context merge
- freshness checks
- fan-out
- step status mutation
- timeline side effects
- dedicated-table side effects
- final entity upsert semantics

This makes the file brittle, hard to reason about, and dangerous to change.

### 3. Deploy sequencing is a landmine

Railway must deploy first. Trigger.dev must deploy second.

If Trigger deploys before Railway is live, Trigger can call internal endpoints that do not exist yet on the old FastAPI container. The result is silent persistence loss.

This has already happened in production.

### 4. Production schema drift exists

The repo and production are not in sync.

The clearest example is `company_ads`:

- migration exists in the repo
- code expects the table
- production does not have the table

### 5. Context-shape assumptions are fragile

Some persistence branches assume fields exist in `cumulative_context` when they often do not.

The production `salesnav_prospects` failure is the clearest example: successful step outputs exist, but the expected `source_company_domain` is blank, so persistence never happens.

### 6. Stuck run state is not self-healing

Production contains stale `running` pipeline runs and stale `running` step results that did not get reconciled back to terminal states.

That means status synchronization is not strong enough to recover all failure modes.

### 7. Documentation has been more optimistic than production

Core source-of-truth docs historically described features as if “built” meant “working in prod.”

That is not safe.

Use:

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`
- this document

as the ground truth before architecture changes.
