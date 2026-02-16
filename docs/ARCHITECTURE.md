# Architecture

## Why Trigger.dev Over Modal + Prefect

Trigger.dev is the execution platform because this system is dominated by API-call workloads, sequencing, retries, and observability rather than long-lived high-compute containers.

Key reasons:

- Single tool for orchestration and compute execution.
- Built-in retries, task-level observability, and execution history.
- Lower operational complexity than split orchestration/compute stacks.
- Better fit for stepwise data enrichment pipelines than heavy container scheduling.

## Why FastAPI Stays Python

FastAPI is the API boundary and tenant gatekeeper:

- Auth verification and `AuthContext` construction.
- Multi-tenant authorization checks (`org_id` + `company_id` rules).
- Input validation and persistence to Postgres.
- Triggering runs and exposing run status via API.

FastAPI is intentionally not the compute layer; Trigger.dev handles pipeline execution.

## FastAPI <-> Trigger.dev Communication

Integration is HTTP-based:

1. FastAPI validates request and writes `submission` + initial run state.
2. FastAPI calls Trigger.dev HTTP API to start pipeline execution.
3. Trigger.dev executes blueprint steps in order and writes state/output back through API/DB-integrated flows.
4. FastAPI surfaces submission/run/result state to clients.

This keeps the boundary explicit: Python for API/tenancy, TypeScript for task execution.

## Multi-Tenancy Design

Primary hierarchy:

`Org -> Company -> User`

Execution hierarchy:

`Submission -> Pipeline Run -> Step Result`

Rules:

- Every tenant-owned query is scoped by `org_id`.
- Company-scoped reads/writes require `company_id` ownership under that org.
- Global step registry is shared; blueprints are org-scoped.

## Blueprint Snapshot Strategy

Blueprint definitions are mutable over time, but runs must be immutable in meaning.

Design:

- Persist `blueprint_snapshot` on `pipeline_runs` at execution start.
- Persist `blueprint_version` on `pipeline_runs`.
- Historical run interpretation never depends on current blueprint state.

## Auth Model

Two auth methods, one runtime context:

- API tokens (machine auth, hashed at rest).
- JWT sessions (user auth, signature validated).

Both produce the same `AuthContext` (`org_id`, `user_id`, `company_id`, `role`, `auth_method`) used uniformly across endpoints.

## Step Registry + Blueprint Model

- `steps` is a global registry of executable step definitions.
- `blueprints` and `blueprint_steps` are org-scoped compositions of those steps.
- Pipeline execution resolves ordered `blueprint_steps` at run start, then executes sequentially.

## Failure and Cancellation Strategy

Default behavior is fail-fast:

- Any step failure marks run as failed (unless explicit per-step override is introduced later).
- Cancellations mark pending/unstarted steps as `skipped`.

Deferred:

- `continue_on_error` as an optional per-step blueprint config extension.
