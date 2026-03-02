# CLAUDE.md

Authoritative context for agents working in `data-engine-x-api`.

## Strategic Directive (Read First)

Read `docs/STRATEGIC_DIRECTIVE.md` before architecture or implementation decisions.

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
  - `app/contracts/` — Pydantic output models
  - `app/services/` — operation service functions
  - `app/routers/execute_v1.py` — operation dispatch + SUPPORTED_OPERATION_IDS
  - `app/routers/entities_v1.py` — entity query endpoints (companies, persons, job-postings, timeline)
  - `app/services/entity_state.py` — entity upsert + identity resolution (company, person, job)
  - `app/services/entity_timeline.py` — timeline event recording
  - `app/services/resolve_operations.py` — 7 CRM resolve operations
- `trigger/`
  - `trigger/src/tasks/run-pipeline.ts` — pipeline runner (supports company, person, job entity types + 3 Parallel Deep Research operations with direct API calls and auto-persist)
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

