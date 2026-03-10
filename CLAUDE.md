# CLAUDE.md

Authoritative context for agents working in `data-engine-x-api`.

## Chief Agent Rules

When operating as chief agent (drafting executor directives, reviewing executor reports):

- **You do not write code, run commands, or execute anything.** Your deliverable is a directive document.
- **Directives specify intent, constraints, and acceptance criteria — not implementation.** Do not write SQL, Python, or TypeScript in directives. The executor writes the implementation. If the executor needs a specific file path, function signature, or API shape, provide that. Do not provide the body.
- **Use the standard directive boilerplate exactly.** Every directive includes the scope clarification on autonomy verbatim from `docs/WRITING_EXECUTOR_DIRECTIVES.md`. Do not paraphrase it.
- **Do not read infrastructure/setup docs to plan your own execution.** You are not the executor. Read system docs only to understand what exists, what's broken, and what constraints apply — so you can write an accurate directive.
- **Follow the template in `docs/WRITING_EXECUTOR_DIRECTIVES.md` exactly.** Reference the example directives in `docs/EXECUTOR_DIRECTIVE_*.md` for quality and format calibration.

## Strategic Directive (Read First)

Read `docs/STRATEGIC_DIRECTIVE.md` before architecture or implementation decisions.

## Production State (as of 2026-03-10)

This section is based on `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`, which was verified against live production SQL.

### What Works End-to-End

- The core pipeline loop works: submission -> pipeline run -> step execution -> entity state upsert. Production has `48` `submissions`, `837` `pipeline_runs`, `3283` `step_results`, `88` `company_entities`, `503` `person_entities`, `1` `job_posting_entities`, `4345` `entity_timeline` rows, and `93` `entity_snapshots`.
- Blueprints with at least one completed production submission:
  - `AlumniGTM Company Resolution Only v1` - `2` completed submissions
  - `AlumniGTM Company Workflow v1` - `5` completed submissions
  - `AlumniGTM Prospect Discovery v1` - `1` completed submission
  - `Company Intel Briefing v1` - `3` completed submissions
  - `ICP Job Titles Discovery v1` - `3` completed submissions
  - `Person Intel Briefing v1` - `1` completed submission
  - `Company Enrichment + Person Enrichment Fan Out` - `1` completed submission
  - `Staffing Enrichment v1` - `1` completed submission
- Healthy auto-persist paths in production:
  - `icp_job_titles` - healthy; `161` successful found steps materialized into `156` distinct table rows with `0` missing matches
  - `company_intel_briefings` - healthy; `3` successful steps materialized into `3` rows
  - `person_intel_briefings` - healthy; `1` successful step materialized into `1` row

### What Is Broken

- `company_customers` is broken. Production has `17` successful customer-producing steps and `331` emitted customer items, but the table has `0` rows.
- `gemini_icp_job_titles` is broken. Production has `20` successful upstream steps over `12` distinct company domains, but the table has `0` rows.
- `salesnav_prospects` is broken. Production has `17` successful prospect-producing steps and `349` emitted prospect rows, but the table has `0` rows. The most likely cause is context shape failure: successful `person.search.sales_nav_url` steps do not carry a usable `source_company_domain`, so the Trigger auto-persist branch never fires.
- `company_ads` is broken harder than the others. The prod table does not exist at all. The repo has `supabase/migrations/019_company_ads.sql`, but migration `019` never reached production.
- `8` `pipeline_runs` are stuck in `running` for `7-14` days.
- `7` `step_results` are stuck in `running`, and `190` are still `queued`.
- End-to-end pipeline reliability is not clean. Pipelines frequently fail to complete cleanly due to silent auto-persist failures, context-shape issues, and the deploy-sequencing landmine between Railway and Trigger.dev.

### What Has Never Been Used

- `46` executable operations in the current code catalog have never been called in production:
  - `address.search`
  - `address.search.residents`
  - `company.analyze.sec_10k`
  - `company.analyze.sec_10q`
  - `company.analyze.sec_8k_executive`
  - `company.derive.detect_changes`
  - `company.derive.extract_icp_titles`
  - `company.enrich.ecommerce`
  - `company.enrich.fmcsa`
  - `company.enrich.hiring_signals`
  - `company.enrich.locations`
  - `company.enrich.tech_stack`
  - `company.research.check_court_filings`
  - `company.research.fetch_sec_filings`
  - `company.research.get_docket_detail`
  - `company.resolve.domain_from_email`
  - `company.resolve.domain_from_linkedin`
  - `company.resolve.domain_from_name`
  - `company.resolve.linkedin_from_domain`
  - `company.resolve.linkedin_from_domain_blitzapi`
  - `company.resolve.location_from_domain`
  - `company.search`
  - `company.search.blitzapi`
  - `company.search.by_job_postings`
  - `company.search.by_tech_stack`
  - `company.search.ecommerce`
  - `company.search.fmcsa`
  - `company.signal.bankruptcy_filings`
  - `contractor.enrich`
  - `contractor.search`
  - `contractor.search.employees`
  - `market.enrich.geo_detail`
  - `market.enrich.metrics_current`
  - `market.enrich.metrics_monthly`
  - `market.search.cities`
  - `market.search.counties`
  - `market.search.jurisdictions`
  - `market.search.zipcodes`
  - `permit.search`
  - `person.contact.resolve_email_blitzapi`
  - `person.contact.resolve_mobile_phone`
  - `person.contact.verify_email`
  - `person.derive.detect_changes`
  - `person.resolve.linkedin_from_email`
  - `person.search.employee_finder_blitzapi`
  - `person.search.waterfall_icp_blitzapi`
- Unused blueprints:
  - `AlumniGTM Prospect Resolution v1`
  - `Phase6 Blueprint 1771280001`
  - `Revenue Activation / CRM Cleanup v1`
  - `Revenue Activation / CRM Enrichment v1`
  - `Revenue Activation / Staffing Enrichment v1`
  - `Staffing Activation / CRM Cleanup v1`
  - `Staffing Activation / CRM Enrichment v1`
- Tables with zero production usage:
  - `entity_relationships` has `0` rows
  - `extracted_icp_job_title_details` has `0` rows

### Known Architectural Problems

- See `docs/DATA_ENGINE_X_ARCHITECTURE.md`, section `7. Known Architectural Problems`, for the full list.
- Top 3 problems:
  - auto-persist silent failures: Trigger catches dedicated-table write failures and keeps the pipeline green, so `step_results` can be full while dedicated tables stay empty
  - `run-pipeline.ts` monolith: the orchestration, direct-provider execution, persistence side effects, fan-out control, and failure semantics are concentrated in one oversized task file
  - deploy-sequencing landmine: Railway must be live before Trigger.dev deploys, or new Trigger code calls internal FastAPI endpoints that do not exist yet

## Diagnostic Reports

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` - live production state audit
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` - full architecture doc including known problems

If `CLAUDE.md` or `docs/SYSTEM_OVERVIEW.md` conflict with these reports, the reports are correct.

## Entity Database Design

Read `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` before any schema work on entity tables.

## Project Overview

`data-engine-x-api` is a multi-tenant enrichment backend. It accepts operation and batch requests, executes deterministic provider-backed steps through Trigger.dev, and persists execution lineage plus canonical entity intelligence.

## Tech Stack

- **FastAPI (Python):** auth, API contracts, persistence, Trigger task triggering, internal callbacks.
- **Trigger.dev (TypeScript):** pipeline orchestration, cumulative context chaining, fail-fast behavior, fan-out child-run orchestration.
- **Supabase/Postgres:** tenancy, submissions/runs/step results, operation audit, entity state, timeline.

## Python vs TypeScript Boundary

- **FastAPI owns:** auth resolution, tenant checks, request validation, DB reads/writes, `/api/v1/*`, `/api/internal/*`.
- **Trigger owns:** `run-pipeline` task execution flow, per-step calls to `/api/v1/execute`, retries/failure propagation, fan-out continuation.
- Boundary is internal HTTP with service auth.

## Multi-Tenancy Model

Hierarchy:

`Org -> Company -> User`

Execution lineage:

`Company -> Submission -> Pipeline Run -> Step Result`

Roles:

- `org_admin`
- `company_admin`
- `member`

Scoping rules:

- Tenant-owned queries are scoped by `org_id`.
- Company-scoped auth paths enforce `company_id` ownership.
- Step registry is global; blueprints are org-scoped.

## Core Concepts

1. **Operations (`/api/v1/execute`)**: canonical operation IDs call provider adapters and return canonical output + provider attempts.
2. **Batch orchestration (`/api/v1/batch/submit`, `/api/v1/batch/status`)**: creates submission and root pipeline runs, then aggregates status/results.
3. **Fan-out**: operation steps can create child pipeline runs (`parent_pipeline_run_id`) and continue execution from a later step position.
4. **Entity state accumulation**: succeeded runs upsert canonical records into `company_entities` / `person_entities` / `job_posting_entities`.
5. **Entity timeline**: upserts and fan-out discoveries emit timeline events into `entity_timeline`.
6. **Output chaining**: each succeeded step merges `result.output` into cumulative context for the next step.

## Auth Model

All protected endpoints use `Authorization: Bearer <token>`, with four supported auth paths:

1. **Tenant JWT session**
   - Decoded by `decode_tenant_session_jwt(...)`.
   - Produces tenant `AuthContext`.
2. **Tenant API token**
   - SHA-256 hash lookup against `api_tokens`.
   - Produces tenant `AuthContext`.
3. **Super-admin API key**
   - Compared to `SUPER_ADMIN_API_KEY`.
   - Grants `SuperAdminContext` on super-admin endpoints, flexible super-admin routes, and `/api/v1/execute` (requires `org_id` + `company_id` in request body).
4. **Internal service auth (Trigger.dev -> FastAPI)**
   - `Authorization: Bearer <INTERNAL_API_KEY>`
   - `x-internal-org-id: <org_uuid>` (required)
   - `x-internal-company-id: <company_uuid>` (optional)

## API Endpoints (Current)

- `GET /health`
- `POST /api/auth/login`
- `POST /api/auth/me`
- `POST /api/super-admin/login`
- `POST /api/super-admin/me`
- `POST /api/super-admin/orgs/create`
- `POST /api/super-admin/orgs/list`
- `POST /api/super-admin/orgs/get`
- `POST /api/super-admin/orgs/update`
- `POST /api/super-admin/companies/create`
- `POST /api/super-admin/companies/list`
- `POST /api/super-admin/companies/get`
- `POST /api/super-admin/users/create`
- `POST /api/super-admin/users/list`
- `POST /api/super-admin/users/get`
- `POST /api/super-admin/users/deactivate`
- `POST /api/super-admin/steps/register`
- `POST /api/super-admin/steps/list`
- `POST /api/super-admin/steps/get`
- `POST /api/super-admin/steps/update`
- `POST /api/super-admin/steps/deactivate`
- `POST /api/super-admin/blueprints/create`
- `POST /api/super-admin/blueprints/list`
- `POST /api/super-admin/blueprints/get`
- `POST /api/super-admin/blueprints/update`
- `POST /api/super-admin/api-tokens/create`
- `POST /api/super-admin/api-tokens/list`
- `POST /api/super-admin/api-tokens/revoke`
- `POST /api/super-admin/submissions/create`
- `POST /api/super-admin/submissions/list`
- `POST /api/super-admin/submissions/get`
- `POST /api/super-admin/pipeline-runs/list`
- `POST /api/super-admin/pipeline-runs/get`
- `POST /api/super-admin/pipeline-runs/retry`
- `POST /api/super-admin/step-results/list`
- `POST /api/companies/list`
- `POST /api/companies/get`
- `POST /api/blueprints/list`
- `POST /api/blueprints/get`
- `POST /api/blueprints/create`
- `POST /api/steps/list`
- `POST /api/steps/get`
- `POST /api/users/list`
- `POST /api/users/get`
- `POST /api/submissions/create`
- `POST /api/submissions/list`
- `POST /api/submissions/get`
- `POST /api/pipeline-runs/list`
- `POST /api/pipeline-runs/get`
- `POST /api/step-results/list`
- `POST /api/v1/execute`
- `POST /api/v1/batch/submit`
- `POST /api/v1/batch/status`
- `POST /api/v1/entities/companies`
- `POST /api/v1/entities/persons`
- `POST /api/v1/entities/job-postings`
- `POST /api/v1/entities/timeline`
- `POST /api/v1/entity-relationships/query`
- `POST /api/v1/icp-job-titles/query`
- `POST /api/v1/company-customers/query`
- `POST /api/v1/gemini-icp-job-titles/query`
- `POST /api/v1/company-ads/query`
- `POST /api/v1/salesnav-prospects/query`
- `POST /api/v1/icp-title-details/query`
- `POST /api/v1/company-intel-briefings/query`
- `POST /api/v1/person-intel-briefings/query`
- `POST /api/internal/pipeline-runs/get`
- `POST /api/internal/pipeline-runs/update-status`
- `POST /api/internal/pipeline-runs/fan-out`
- `POST /api/internal/step-results/update`
- `POST /api/internal/step-results/mark-remaining-skipped`
- `POST /api/internal/submissions/update-status`
- `POST /api/internal/submissions/sync-status`
- `POST /api/internal/entity-state/upsert`
- `POST /api/internal/entity-timeline/record-step-event`
- `POST /api/internal/entity-relationships/record`
- `POST /api/internal/entity-relationships/record-batch`
- `POST /api/internal/entity-relationships/invalidate`
- `POST /api/internal/icp-job-titles/upsert`
- `POST /api/internal/company-customers/upsert`
- `POST /api/internal/gemini-icp-job-titles/upsert`
- `POST /api/internal/company-ads/upsert`
- `POST /api/internal/salesnav-prospects/upsert`
- `POST /api/internal/company-intel-briefings/upsert`
- `POST /api/internal/person-intel-briefings/upsert`

## Trigger.dev Conventions

- Tasks live in `trigger/src/tasks/`.
- `run-pipeline` is the active orchestrator.
- Generic `execute-step` remains legacy and is not used by the current pipeline runner.

## Common Commands

```bash
# API tests
pytest

# Trigger.dev local runtime
cd trigger && npx trigger.dev@latest dev

# Run API locally with Doppler-injected env
doppler run -- uvicorn app.main:app --reload

# Run tests with Doppler-injected env
doppler run -- pytest
```

## Deploy Protocol

**Deploy Railway FIRST, Trigger.dev SECOND. Never simultaneously.**

```bash
# Step 1: Push to main (Railway auto-deploys)
git push origin main
# WAIT 1-2 minutes for Railway deploy to complete

# Step 2: Deploy Trigger.dev (only after Railway is live)
cd trigger && npx trigger.dev@4.4.0 deploy
```

Trigger.dev calls FastAPI internal endpoints. If Trigger.dev deploys before Railway, new endpoint calls fail silently — pipeline succeeds but data doesn't persist to dedicated tables. See `docs/troubleshooting-fixes/` for incidents.

## Database / Migrations

Migration order:

1. `001_initial_schema.sql`
2. `002_users_password_hash.sql`
3. `003_api_tokens_user_id.sql`
4. `004_steps_executor_config.sql`
5. `005_operation_execution_history.sql`
6. `006_blueprint_operation_steps.sql`
7. `007_entity_state.sql`
8. `008_companies_domain.sql`
9. `009_entity_timeline.sql`
10. `010_fan_out.sql`
11. `011_entity_timeline_submission_lookup.sql`
12. `012_entity_snapshots.sql`
13. `013_job_posting_entities.sql`
14. `014_entity_relationships.sql`
15. `015_icp_job_titles.sql`
16. `016_intel_briefing_tables.sql`
17. `017_icp_title_extraction.sql`
18. `018_alumnigtm_persistence.sql`
19. `019_company_ads.sql`
20. `020_salesnav_prospects.sql`

## Environment Configuration

- App settings use non-prefixed env names (for example `DATABASE_URL`, `INTERNAL_API_KEY`, `LEADMAGIC_API_KEY`).
- `REVENUEINFRA_INGEST_API_KEY` — API key data-engine-x uses to authenticate against HQ ingest/validation endpoints (same value as `INGEST_API_KEY` in HQ).
- `RAPIDAPI_SALESNAV_SCRAPE_API_KEY` — API key for RapidAPI Sales Navigator scraper (alumni search).
- `PARALLEL_API_KEY` — API key for Parallel.ai Deep Research (set in Trigger.dev env vars, NOT in Doppler/Railway — this operation runs directly from Trigger.dev).
- Trigger task runtime supports `DATA_ENGINE_API_URL` / `DATA_ENGINE_INTERNAL_API_KEY` fallback in `run-pipeline.ts`.
- Docker runtime injects secrets via Doppler (`CMD ["doppler", "run", "--", ...]` in `Dockerfile`).
- Railway only needs `DOPPLER_TOKEN`; Doppler provides the rest at runtime.

## HQ Integration (api.revenueinfra.com)

data-engine-x calls HQ endpoints for:
- **Research lookups**: competitors, customers, alumni, champions, VC funding, similar companies, SEC filings
- **CRM resolution**: domain from email/LinkedIn/name, LinkedIn from domain, person LinkedIn from email, location from domain (6 `/single` endpoints)
- **Job validation**: Bright Data cross-source check (`/api/ingest/brightdata/validate-job`)
- **Sales Nav templates**: client-specific Sales Nav URL templates (`/api/hq/clients/salesnav-template`)

HQ is read-only from data-engine-x's perspective. data-engine-x never writes to HQ's DB.

## Live Orgs

| Org | ID | Companies |
|---|---|---|
| Staffing Activation | `58203c4a-1654-42f8-8486-bd37016223a5` | Sales Talent (`6749b0b9-3e9a-4382-8e4d-353771ef78d4`, domain: salestalent.inc) |
| Revenue Activation | `d319a533-356a-4592-bd7a-b79dd4d27802` | — |
| AlumniGTM | `b0293785-aa7a-4234-8201-cc47305295f8` | global (`8cc8b8f3-fc26-49eb-992b-abe8cb46ec53`, domain: global.alumnigtm.com) |

## Directory Structure

- `app/`
  - `app/providers/` — provider adapters (prospeo, blitzapi, enigma, theirstack, revenueinfra/, etc.)
    - includes HQ workflow `/run/` adapters for `infer_linkedin_url`, `icp_job_titles_gemini`, `discover_customers_gemini`, `icp_criterion`, `salesnav_url`, `evaluate_icp_fit`
  - `app/contracts/` — Pydantic output models
  - `app/services/` — operation service functions
    - `app/services/hq_workflow_operations.py` — HQ workflow operation services (6 RevenueInfra-backed workflow ops)
  - `app/routers/execute_v1.py` — operation dispatch + SUPPORTED_OPERATION_IDS
  - `app/routers/entities_v1.py` — entity query endpoints (companies, persons, job-postings, timeline)
  - `app/services/entity_state.py` — entity upsert + identity resolution (company, person, job)
  - `app/services/entity_timeline.py` — timeline event recording
  - `app/services/resolve_operations.py` — 7 CRM resolve operations
- `trigger/`
  - `trigger/src/tasks/run-pipeline.ts` — pipeline runner (supports company, person, job entity types + 4 Parallel.ai direct operations with direct API calls and auto-persist)
- `tests/`
- `scripts/` — backfill scripts for dedicated tables (icp_job_titles, company/person intel briefings)
- `supabase/migrations/`
- `docs/`
  - `docs/blueprints/` — blueprint definition JSON files
  - `docs/EXECUTOR_DIRECTIVE_*.md` — executor agent directives (documentation)
  - `docs/directives-hq/` — directives for HQ database work (job title matching, dedup)
  - `docs/troubleshooting-fixes/` — incident post-mortems and fixes
  - `docs/api-reference-docs/` — provider API documentation (Enigma, Parallel.ai)
- `Dockerfile`

