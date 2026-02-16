# CLAUDE.md

Authoritative context for AI agents working in `data-engine-x-api`.

## Project Overview

`data-engine-x-api` is a multi-tenant data processing backend for internal/operator teams that need to ingest raw CRM/company data, run deterministic processing pipelines, and return transformed outputs to dashboards, CRMs, or both.

## Tech Stack

- **FastAPI on Railway**: API layer (auth, routing, validation, persistence).
- **Trigger.dev**: orchestration + compute execution for processing steps.
- **Supabase (Postgres)**: tenant data, blueprint definitions, submissions, run state, step results.

## Python vs TypeScript Boundary

- **Python (FastAPI)**: owns authentication, authorization, request validation, DB writes/reads, and run triggering.
- **TypeScript (Trigger.dev)**: owns pipeline execution and retries; tasks are stateless and run from provided input + persisted state.
- Boundary contract is HTTP: FastAPI triggers Trigger.dev runs through Trigger API calls.

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

- **Step**: globally registered atomic processor mapped to a Trigger.dev task.
- **Blueprint**: org-scoped ordered list of steps with per-step config.
- **Submission**: org/company data batch tied to one blueprint.
- **Pipeline Run**: one execution attempt for a submission (multiple runs allowed).
- **Step Result**: status + input/output/error/timing for one step execution.

## Auth Model

Two auth methods produce the same `AuthContext`:

- **API token** (machine-to-machine): hashed token lookup in DB.
- **JWT session** (user-facing): validated signature and mapped identity.

`AuthContext` contains: `org_id`, `user_id`, `company_id` (nullable), `role`, `auth_method`.

JWT identities must be mirrored in `users` (no transient identities).

## API Conventions

- All endpoints are `POST`.
- `AuthContext` dependency on every endpoint.
- Endpoints stay thin: validate -> delegate to service/db/orchestrator -> return.

## Trigger.dev Conventions

- Tasks live in `trigger/src/tasks/`.
- Pipeline orchestration logic lives in the Trigger project and executes blueprint steps in order.
- Default behavior is fail-fast; cancellation marks pending steps as skipped.

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

# Install Trigger dependencies
cd trigger && npm install && cd ..

# Run migration (manual execution by operator)
psql "$DATA_ENGINE_DATABASE_URL" -f supabase/migrations/001_initial_schema.sql
```

## Database Connection

- `DATA_ENGINE_DATABASE_URL=<postgres-connection-string>`
- Keep real credentials in `.env`; never hardcode secrets in source files.

## Directory Structure

- `app/` — FastAPI app (routers, auth, models, services, config)
- `trigger/` — Trigger.dev code (tasks + orchestration)
- `supabase/migrations/` — SQL migrations
- `docs/` — system docs and architecture decisions
