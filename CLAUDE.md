# CLAUDE.md

Authoritative context for AI agents working in `data-engine-x-api`.

## Strategic Directive (Read First)

Before making architecture or implementation decisions, read:

- `docs/STRATEGIC_DIRECTIVE.md`

This directive is mandatory guidance for:

- no-guessing behavior,
- canonical operation/action structure,
- config-driven provider ordering,
- durable execution logging requirements,
- current locked v1 provider decisions.

## Project Overview

`data-engine-x-api` is a multi-tenant data processing backend for internal/operator teams that ingest entity inputs, execute deterministic operation pipelines, and persist canonical entity intelligence with full run lineage.

## Tech Stack

- **FastAPI on Railway**: API layer (auth, routing, validation, persistence, Trigger orchestration trigger point).
- **Trigger.dev**: orchestration/runtime for ordered step execution and retries.
- **Supabase (Postgres)**: tenant data, blueprint definitions, submissions/runs/step results, operation history, entity state.

## Python vs TypeScript Boundary

- **Python (FastAPI)**: owns authentication/authorization, request validation, DB writes/reads, batch submission/status APIs, and Trigger run triggering.
- **TypeScript (Trigger.dev)**: owns pipeline run execution, cumulative context chaining, internal status callbacks, and fail-fast step orchestration.
- Boundary contract is HTTP: FastAPI triggers Trigger.dev task runs; Trigger.dev calls FastAPI internal endpoints.

## Multi-Tenancy Model

Hierarchy:

`Org -> Company -> User`

Execution lineage:

`Company -> Submission -> Pipeline Run -> Step Result`

Roles:

- `org_admin`: full org scope.
- `company_admin`: company scope.
- `member`: restricted read/limited action scope.

Scoping rules:

- Every tenant-owned query must include `org_id`.
- Company-scoped operations must validate `company_id` belongs to `org_id`.
- Step registry is global; blueprints are org-scoped.

## Core Concepts

- **Operation execution (v1 execute):** canonical operation IDs run through provider adapters and emit canonical outputs plus provider attempts.
- **Batch orchestration:** `/api/v1/batch/submit` creates one submission and per-entity pipeline runs; `/api/v1/batch/status` returns normalized run progress and final context.
- **Output chaining:** each successful step merges canonical output into cumulative context used as input for the next operation.
- **Entity state accumulation:** successful pipeline runs are upserted into `company_entities` or `person_entities` with versioned records and canonical payload snapshots.
- **Blueprint + Steps:** ordered org-scoped operation workflow definition via `blueprints` + `blueprint_steps`.

## Auth Model

Two external auth methods produce the same `AuthContext`:

- **API token** (machine-to-machine): hashed token lookup in DB.
- **JWT session** (user-facing): validated signature and mapped identity.

Internal service auth path (Trigger.dev -> FastAPI):

- `Authorization: Bearer <DATA_ENGINE_INTERNAL_API_KEY>`
- `x-internal-org-id: <org_uuid>` (required)
- `x-internal-company-id: <company_uuid>` (optional for org-wide calls, passed for run execution calls)

`AuthContext` contains: `org_id`, `user_id`, `company_id` (nullable), `role`, `auth_method`.

JWT identities must be mirrored in `users` (no transient identities).

## API Conventions

- All endpoints are `POST`.
- `AuthContext` dependency on tenant endpoints.
- Endpoints stay thin: validate -> delegate to service/db/orchestrator -> return.

Primary v1 endpoints:

- Single operation: `/api/v1/execute`
- Batch: `/api/v1/batch/submit`, `/api/v1/batch/status`
- Entities: `/api/v1/entities/companies`, `/api/v1/entities/persons`
- Internal callbacks: `/api/internal/*` (requires internal API key)

## Trigger.dev Conventions

- Tasks live in `trigger/src/tasks/`.
- `run-pipeline` is the active orchestrator task.
- Default behavior is fail-fast; cancellation/failure marks remaining queued steps as skipped.

Commands:

```bash
# Trigger.dev local dev
cd trigger && npx trigger.dev@latest dev

# Trigger.dev deploy
cd trigger && npx trigger.dev@latest deploy
```

## Common Commands

```bash
# Install Python dependencies
pip install -r requirements.txt

# Run API locally
uvicorn app.main:app --reload

# Run tests
pytest

# Install Trigger dependencies
cd trigger && npm install && cd ..

# Run migration (manual execution by operator)
psql "$DATA_ENGINE_DATABASE_URL" -f supabase/migrations/001_initial_schema.sql
```

## Migrations

Current migration order:

- `001_initial_schema.sql`
- `002_users_password_hash.sql`
- `003_api_tokens_user_id.sql`
- `004_steps_executor_config.sql`
- `005_operation_execution_history.sql`
- `006_blueprint_operation_steps.sql`
- `007_entity_state.sql`

## Database Connection

- `DATA_ENGINE_DATABASE_URL=<postgres-connection-string>`
- Keep real credentials in `.env`; never hardcode secrets in source files.

## Directory Structure

- `app/` — FastAPI app (`routers/`, `auth/`, `models/`, `services/`, `providers/`, `contracts/`, `config`)
- `trigger/` — Trigger.dev tasks/orchestration runtime
- `tests/` — pytest suite for contracts, batch flow, and entity state
- `supabase/migrations/` — SQL migrations
- `docs/` — system docs and architecture decisions
