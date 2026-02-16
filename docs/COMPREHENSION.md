# data-engine-x-api — Comprehension

## 1) System Understanding

`data-engine-x-api` is a multi-tenant processing backend that takes raw company/CRM data, runs deterministic step pipelines, and returns transformed outputs for downstream consumption (dashboard, CRM, or both).

Operational split:

- **FastAPI (Python, Railway)**: Auth, request validation, persistence, pipeline kickoff.
- **Trigger.dev (TypeScript)**: Step execution orchestration, retries, observability.
- **Supabase/Postgres**: Source of truth for tenants, blueprints, submissions, run state, and step results.

Critical boundary:

- Python owns tenancy/auth/routing/storage.
- TypeScript tasks are stateless executors driven by DB + Trigger inputs.

## 2) End-to-End Flow

1. Client calls FastAPI (POST endpoint) with auth + submission payload.
2. FastAPI resolves `AuthContext`, validates org/company access, persists `submission`.
3. FastAPI creates `pipeline_run` and triggers Trigger.dev runner task via HTTP API.
4. Trigger runner loads blueprint steps, executes mapped step tasks in order.
5. Each step reads prior context, calls external providers (Apollo/Blitz/Gemini/etc), writes `step_results`.
6. Runner updates pipeline status; completion/failed state is persisted in Postgres.
7. API exposes run/submission status and outputs to authorized org/company users or systems.

## 3) Multi-Tenancy Rules

Tenancy hierarchy:

- `org` -> `company` -> `submission` -> `pipeline_run` -> `step_result`

Access invariants:

- Every tenant-owned query is filtered by `org_id` at minimum.
- Company-specific reads/writes require `company_id` **and** ownership validation (`company.org_id = auth.org_id`).
- Global resources (step registry) are not org-scoped.
- Role behavior:
  - `org_admin`: full org scope.
  - `company_admin`: restricted to assigned company scope.
  - `member`: read-oriented access unless explicitly elevated per endpoint.

## 4) Core Domain Mapping

- **Step**: globally registered task definition (`task_id`, type, schema/metadata).
- **Blueprint**: org-owned ordered list of steps + per-step config.
- **Submission**: a tenant batch input tied to a blueprint and company.
- **Pipeline Run**: one execution instance for a submission.
- **Step Result**: materialized output/status/timing per step execution.

## 5) Proposed Database Schema

Below is the schema I would implement first-pass in Postgres for this system.

### 5.1 Suggested enums

- `user_role`: `org_admin | company_admin | member`
- `auth_method`: `api_token | jwt`
- `step_type`: `clean | enrich | analyze | extract | transform`
- `run_status`: `queued | running | succeeded | failed | canceled`
- `step_status`: `queued | running | succeeded | failed | skipped | retrying`
- `submission_status`: `received | validated | queued | running | completed | failed | canceled`

### 5.2 Tables

#### `orgs`

- `id uuid pk`
- `name text not null`
- `slug text not null unique`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

#### `companies`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `name text not null`
- `external_ref text null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `unique (org_id, name)`
- `unique (org_id, external_ref)` (where `external_ref is not null`)

#### `users`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `company_id uuid null references companies(id) on delete set null`
- `email citext not null unique`
- `full_name text null`
- `role user_role not null`
- `is_active boolean not null default true`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Constraint:

- `company_id` (if present) must belong to same `org_id` (enforced via trigger or composite FK strategy).

#### `api_tokens`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `company_id uuid null references companies(id) on delete set null`
- `name text not null`
- `token_hash text not null unique`
- `role user_role not null`
- `created_by_user_id uuid null references users(id) on delete set null`
- `last_used_at timestamptz null`
- `expires_at timestamptz null`
- `revoked_at timestamptz null`
- `created_at timestamptz not null default now()`

#### `steps` (global registry)

- `id uuid pk`
- `key text not null unique` (stable internal identifier)
- `task_id text not null unique` (Trigger.dev task ID)
- `name text not null`
- `description text null`
- `step_type step_type not null`
- `default_config jsonb not null default '{}'::jsonb`
- `input_schema jsonb null`
- `output_schema jsonb null`
- `is_active boolean not null default true`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

#### `blueprints`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `name text not null`
- `description text null`
- `is_active boolean not null default true`
- `created_by_user_id uuid null references users(id) on delete set null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `unique (org_id, name)`

#### `blueprint_steps`

- `id uuid pk`
- `blueprint_id uuid not null references blueprints(id) on delete cascade`
- `step_id uuid not null references steps(id) on delete restrict`
- `position int not null check (position > 0)`
- `config jsonb not null default '{}'::jsonb`
- `is_enabled boolean not null default true`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `unique (blueprint_id, position)`

#### `submissions`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `company_id uuid not null references companies(id) on delete restrict`
- `blueprint_id uuid not null references blueprints(id) on delete restrict`
- `submitted_by_user_id uuid null references users(id) on delete set null`
- `source text null` (dashboard/api/crm/etc)
- `input_payload jsonb not null`
- `status submission_status not null default 'received'`
- `metadata jsonb not null default '{}'::jsonb`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Constraint:

- `blueprint` and `company` must belong to the same `org_id` as submission.

#### `pipeline_runs`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `company_id uuid not null references companies(id) on delete restrict`
- `submission_id uuid not null references submissions(id) on delete cascade`
- `blueprint_id uuid not null references blueprints(id) on delete restrict`
- `trigger_run_id text null unique` (Trigger.dev run ID)
- `status run_status not null default 'queued'`
- `attempt int not null default 1`
- `started_at timestamptz null`
- `finished_at timestamptz null`
- `error_message text null`
- `error_details jsonb null`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`

Indexes:

- `(org_id, created_at desc)`
- `(submission_id)`
- `(status, created_at desc)`

#### `step_results`

- `id uuid pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `company_id uuid not null references companies(id) on delete restrict`
- `pipeline_run_id uuid not null references pipeline_runs(id) on delete cascade`
- `submission_id uuid not null references submissions(id) on delete cascade`
- `step_id uuid not null references steps(id) on delete restrict`
- `blueprint_step_id uuid null references blueprint_steps(id) on delete set null`
- `step_position int not null check (step_position > 0)`
- `task_run_id text null` (subtask run identifier)
- `status step_status not null default 'queued'`
- `input_payload jsonb null`
- `output_payload jsonb null`
- `error_message text null`
- `error_details jsonb null`
- `started_at timestamptz null`
- `finished_at timestamptz null`
- `duration_ms int null check (duration_ms >= 0)`
- `attempt int not null default 1`
- `created_at timestamptz not null default now()`
- `updated_at timestamptz not null default now()`
- `unique (pipeline_run_id, step_position, attempt)`

Indexes:

- `(org_id, created_at desc)`
- `(pipeline_run_id, step_position)`
- `(status, created_at desc)`

#### `run_events` (optional but recommended)

- `id bigserial pk`
- `org_id uuid not null references orgs(id) on delete cascade`
- `pipeline_run_id uuid not null references pipeline_runs(id) on delete cascade`
- `step_result_id uuid null references step_results(id) on delete set null`
- `level text not null` (`info|warn|error|debug`)
- `event_type text not null` (`run_started`, `step_retry`, provider errors, etc.)
- `message text not null`
- `details jsonb null`
- `created_at timestamptz not null default now()`

Purpose:

- Auditable timeline and easier operational debugging without overloading step result rows.

## 6) Data Integrity + Security Recommendations

- Use Postgres constraints/triggers to enforce cross-table tenant integrity (`org_id` consistency).
- Enable RLS on tenant tables (`companies`, `users`, `api_tokens`, `blueprints`, `blueprint_steps`, `submissions`, `pipeline_runs`, `step_results`, `run_events`).
- Prefer opaque external IDs only at API edge; keep UUID PKs internal.
- Never store plaintext API tokens; store hash + prefix for lookup ergonomics.
- Add idempotency key support on submission creation to prevent duplicate runs from client retries.

## 7) Questions Before Implementation

1. **Run cardinality**: should one `submission` support multiple reruns (`pipeline_runs` > 1), or strictly one run per submission?
2. **Blueprint mutability**: should runs reference a snapshot of blueprint config at execution time (immutable), or always current blueprint definition?
3. **Company-scoped users**: can a `company_admin/member` belong to multiple companies, or exactly one company?
4. **Data retention**: what retention policy is required for `input_payload`/`output_payload`/error details (especially PII)?
5. **Step outputs**: do we need normalized typed outputs for common entities, or is JSONB-only acceptable initially?
6. **Cancellation semantics**: should canceled pipelines mark pending steps as `skipped` or remain `queued`?
7. **Failure policy**: does a failed step always stop the run, or can blueprints allow `continue_on_error` per step?
8. **Auth source of truth**: are JWT users mirrored in `users` table always, or can JWT-only identities exist transiently?
9. **Token scope**: should API tokens optionally be restricted to selected blueprints/endpoints beyond role/company scope?
10. **Observability depth**: is `run_events` required now, or defer until after initial launch?

## 8) Implementation Readiness

With answers to the questions above, this can be implemented as:

- Supabase migrations for enums/tables/indexes/constraints/RLS.
- FastAPI auth dependency + org/company authorization helpers.
- POST endpoints for steps/blueprints/submissions/runs/status retrieval.
- Trigger.dev runner + per-step task contracts (`task_id` mapping from `steps` registry).
