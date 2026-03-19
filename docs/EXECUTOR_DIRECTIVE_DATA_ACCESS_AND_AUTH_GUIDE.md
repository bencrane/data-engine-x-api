# Executor Directive: Data Access & Auth Guide

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** There is no single document that practically answers: "I want to query or write data — what credentials do I use, what's scoped to what, what can I see, and what do my payloads look like?" The existing `docs/AUTH_MODEL.md` is a compact reference but does not cover data visibility by auth context, practical connection patterns from different clients (frontend, notebook, script, Trigger.dev), write paths, or worked curl examples. Engineers, agents, and integrators waste time tracing auth code to answer basic access questions. This guide closes that gap.

---

## Existing code to read

Before writing anything, read these files carefully. **Every claim in the guide must be grounded in what the code actually does**, not what docs say it should do. Trace the auth resolution logic end-to-end for each auth type.

### Auth resolution (the core logic)

- `app/auth/dependencies.py` — primary auth dependency `get_current_auth()` that validates bearer tokens. This is where tenant JWT vs API token vs super-admin vs internal service auth are distinguished. Trace every branch.
- `app/auth/tokens.py` — token encoding/decoding: `decode_tenant_session_jwt()`, `hash_api_token()`, `create_tenant_session_jwt()`. Understand what claims are in the JWT.
- `app/auth/models.py` — `AuthContext` and `SuperAdminContext` models. Understand what fields each carries (org_id, company_id, user_id, role, etc.).
- `app/auth/super_admin.py` — super-admin auth dependency `get_current_super_admin()`. Understand how it differs from tenant auth and what context it produces.

### Routers (where auth is consumed)

- `app/routers/auth.py` — tenant login endpoint (`POST /login`). Understand the login flow: what credentials are sent, what's returned, how the JWT is structured.
- `app/routers/super_admin_auth.py` — super-admin login endpoint. Understand how admin sessions are created.
- `app/routers/super_admin_api.py` — super-admin CRUD endpoints including API token creation. Understand how tokens are created, what org they bind to, and the response shape.
- `app/routers/execute_v1.py` — operation execution (`/api/v1/execute`) and batch endpoints (`/api/v1/batch/submit`, `/api/v1/batch/status`). Trace how auth context is resolved for each. Pay special attention to the super-admin path on `/execute` — it requires `org_id` + `company_id` in the request body. Understand why.
- `app/routers/entities_v1.py` — entity query endpoints (companies, persons, job-postings, timeline). Trace how org scoping is applied to queries.
- `app/routers/internal.py` — internal Trigger.dev callback endpoints. Trace how `INTERNAL_API_KEY` is validated and how `x-internal-org-id` / `x-internal-company-id` headers are consumed.
- `app/routers/fmcsa_v1.py` — FMCSA query endpoints. Trace the `_resolve_flexible_auth()` pattern — this is the only place where auth is flexible (accepts either super-admin or tenant). Understand what data is returned regardless of org context (FMCSA data is global, not org-scoped).

### Trigger.dev internal client

- `trigger/src/workflows/internal-api.ts` — the TypeScript HTTP client that Trigger tasks use to call FastAPI. Trace how it sets the `Authorization` header, `x-internal-org-id`, and `x-internal-company-id`. Understand where it gets these values from (task payload).

### Existing docs (for reference, not as source of truth)

- `docs/AUTH_MODEL.md` — compact auth reference. Use as a starting point but verify every claim against the code.
- `docs/API_SURFACE.md` — endpoint inventory. Use to ensure you cover all relevant endpoints.
- `CLAUDE.md` — for the multi-tenancy model, live orgs, and schema layout.

---

## Deliverable 1: Data Access & Auth Guide

Create `docs/DATA_ACCESS_AND_AUTH_GUIDE.md`.

Add a last-updated timestamp at the top:

```markdown
# Data Access & Auth Guide

**Last updated:** 2026-03-18T[HH:MM:SS]Z
```

Use the actual UTC time when you finish writing.

### Required sections

The guide should be organized around the central question: **what data is available to whom, under what credentials, and how do I access it from different contexts?**

---

#### Section 1: Auth Types at a Glance

A quick-reference table summarizing all auth mechanisms. For each one, state:

| Auth Type | Header Format | Who Uses It | What It Unlocks | Org-Scoped? |
|---|---|---|---|---|
| Tenant JWT session | `Authorization: Bearer <jwt>` | Frontend users | ... | Yes |
| Tenant API token | `Authorization: Bearer <token>` | Scripts, automations | ... | Yes |
| Super-admin API key | `Authorization: Bearer <key>` | Admin tools, cross-org queries | ... | Configurable |
| Internal service auth | `Authorization: Bearer <internal_key>` + org/company headers | Trigger.dev | ... | Yes (via headers) |

Fill in from the code. If there are additional auth types beyond these four, include them.

---

#### Section 2: Data Visibility by Auth Context

**This is the most important section.** For each auth type, map out exactly what data is visible.

##### Tenant User (JWT or API Token)

- What tables are queryable and how is org scoping applied?
- Can a tenant see other orgs' data? (Answer: no — trace the code to confirm)
- Is scoping by `org_id` only, or also by `company_id`?
- Which tables are org-scoped via execution lineage (submissions, pipeline_runs, step_results, operation_runs)?
- Which tables are org-scoped via direct `org_id` column (entity tables)?
- Are there any tables that are globally visible to all tenants? (e.g., blueprints? step registry? FMCSA data via flexible auth?)

##### Super Admin

- Does super-admin bypass all org scoping? Trace the code — on which endpoints does super-admin get god-mode access vs. still needing to specify an org?
- On `/api/v1/execute`: super-admin must pass `org_id` + `company_id` in the body. Explain why (the execution needs an org context to create submissions/runs under).
- On entity query endpoints: does super-admin see all orgs' entities or must it filter?
- On super-admin CRUD endpoints: full cross-org visibility.
- On FMCSA endpoints: flexible auth means super-admin sees global FMCSA data.

##### Internal Service Auth (Trigger.dev)

- How does Trigger specify which org/company it's acting on behalf of? (headers)
- What endpoints does internal auth have access to? (internal callbacks, execute)
- Can internal auth access entity query endpoints or only internal endpoints?
- What happens if org/company headers are missing?

##### FMCSA and Federal Data Endpoints

- Are these org-scoped or globally accessible?
- What is the flexible auth pattern? Which auth types can access these endpoints?
- Is FMCSA data visible to all tenants, or only to specific orgs?

---

#### Section 3: Auth Paths Explained

Detailed practical explanation of each auth mechanism. For each one:

##### Tenant JWT Session

- How is a JWT obtained? (login endpoint, credentials, response shape)
- What claims are in the JWT? (user_id, org_id, company_id, role — trace `create_tenant_session_jwt`)
- How long does the session last? (expiry)
- What header format to send on subsequent requests?
- How does the backend decode and validate it? (trace `decode_tenant_session_jwt`)

##### Tenant API Token

- How is an API token created? (super-admin endpoint — trace the creation flow)
- What org does it bind to? (trace the `api_tokens` table schema — does it store org_id?)
- How is it validated? (SHA-256 hash lookup against `api_tokens` table)
- Difference from JWT: no expiry? No user context? Just org context?
- What header format to send?

##### Super-Admin API Key

- Where is it configured? (`SUPER_ADMIN_API_KEY` env var)
- How is it validated? (direct string comparison)
- What context does it produce? (`SuperAdminContext` — trace what fields it has)
- When does it need additional context in the request body? (on `/execute`, needs `org_id` + `company_id`)

##### Internal Service Auth

- Where is the key configured? (`INTERNAL_API_KEY` env var, also `DATA_ENGINE_INTERNAL_API_KEY` on Trigger side)
- How does Trigger.dev pass org context? (`x-internal-org-id`, `x-internal-company-id` headers)
- How is it validated on the FastAPI side? (trace `internal.py` auth check)
- What endpoints accept internal auth?

---

#### Section 4: Connecting from Different Contexts

Practical guide for each access context.

##### From a Frontend App (Dashboard / Web Application / assistant-ui)

- Auth flow: login → JWT → bearer token on all requests
- Login endpoint, request/response shape
- How to store and refresh the token
- Example: authenticating and then querying entities

##### From Hex or a Data Notebook (Direct Postgres)

- Direct Postgres connection bypasses the API entirely
- What does that mean for scoping? (You see everything — all orgs, all schemas)
- Connection string pattern: `doppler run -p data-engine-x-api -c prd -- psql` for production
- What credentials to use (DATABASE_URL from Doppler)
- Caution: no auth scoping at the database level — you're responsible for filtering by org_id yourself

##### From a Script or Automation

- API token pattern
- How to obtain a token (created via super-admin endpoint)
- Header format
- Example: curl to query entities, curl to submit a batch

##### From Trigger.dev (Internal Service)

- Internal API client setup (trace `internal-api.ts`)
- How Trigger gets the API URL and key (env vars)
- How org/company context flows from task payload → headers → FastAPI
- Example: how a workflow task calls `/api/internal/...` with service auth

---

#### Section 5: Writing Data — Ingest & Write Paths

For each write path, explain the auth required and include a sample request.

##### Batch Submit (Enrichment Pipeline)

- Endpoint: `POST /api/v1/batch/submit`
- Auth: tenant JWT or API token (org-scoped) or super-admin (with org_id/company_id in body)
- Request payload shape (trace the actual Pydantic model in `execute_v1.py`)
- What it creates: submission → pipeline runs → step results
- Include a curl example with placeholder values

##### Single Operation Execute

- Endpoint: `POST /api/v1/execute`
- Auth: same as batch, plus internal service auth
- Request payload shape
- Curl example

##### Internal Callbacks (Trigger → FastAPI)

- What endpoints does Trigger call back to? (step result updates, entity upserts, etc.)
- Auth: internal service auth with org/company headers
- These are not user-facing — explain they're part of the orchestration loop

##### Clay Ingestion Path

- How does external Clay data get ingested?
- What endpoint, what auth?
- Brief description — this is an internal ingestion pattern

##### FMCSA Ingestion Path

- How does FMCSA feed data get ingested?
- Is this API-driven or Trigger-task-driven (direct Postgres writes)?
- What auth context does the ingestion run under?

---

#### Section 6: API Token vs API Key Clarity

A dedicated section disambiguating the credential types, since this is a common confusion point.

| Credential | What It Is | Where Configured/Created | Which Endpoints Accept It | Org-Bound? |
|---|---|---|---|---|
| Super-admin API key | Single static key | `SUPER_ADMIN_API_KEY` env var | Super-admin endpoints, `/execute`, FMCSA (flexible) | No (cross-org) |
| Tenant API token | Per-org token | Created via super-admin endpoint, stored in `api_tokens` table | All tenant endpoints | Yes |
| Internal API key | Service-to-service key | `INTERNAL_API_KEY` env var | `/api/internal/*` endpoints | No (org via headers) |
| Tenant JWT | Short-lived session token | Issued by `/login` endpoint | All tenant endpoints | Yes |

Verify each cell against the code. If there are additional credential types, add them.

---

#### Section 7: Schema & Table Scoping Reference

Quick-reference table showing which schemas/tables are org-scoped vs global.

```markdown
| Schema.Table | Scoping | Scoped By | Notes |
|---|---|---|---|
| ops.submissions | Org-scoped | company_id → org lineage | Via company ownership |
| ops.pipeline_runs | Org-scoped | submission_id → company lineage | Via submission ownership |
| ops.step_results | Org-scoped | pipeline_run_id lineage | Via pipeline run ownership |
| ops.operation_runs | Org-scoped | org_id column | Direct org_id |
| entities.company_entities | Org-scoped | org_id column | Direct org_id |
| entities.person_entities | Org-scoped | org_id column | Direct org_id |
| entities.motor_carrier_census_records | Global | — | FMCSA data, no org scoping |
| ... | ... | ... | ... |
```

Cover all application tables across `ops` and `entities` schemas. For each, state whether it's org-scoped (and by what column/lineage) or globally accessible.

---

#### Section 8: Practical Examples

At minimum, include these 6 curl examples with realistic placeholder values. Each example should show the full curl command with headers, body, and a brief explanation of what it does and what you'd expect back.

1. **Querying entities as a tenant (API token)**
   - `GET /api/v1/entities/companies` with bearer token
   - Show that results are automatically scoped to the token's org

2. **Submitting a batch as a tenant**
   - `POST /api/v1/batch/submit` with bearer token
   - Show the full request body with blueprint_id, inputs, etc.

3. **Querying entities as super admin**
   - Show that super-admin on entity endpoints either sees all orgs or needs to specify — trace the code to determine which

4. **Hitting an internal endpoint with service auth**
   - Show the `Authorization` + `x-internal-org-id` + `x-internal-company-id` headers
   - Use a representative internal endpoint

5. **Querying FMCSA data (flexible auth)**
   - Show a FMCSA query endpoint call with either super-admin or tenant auth
   - Demonstrate that FMCSA data is not org-scoped

6. **Creating an API token via super admin**
   - Show the super-admin endpoint that creates a tenant API token
   - Show what org_id is passed and how the token is returned

For each example, use placeholder values like `YOUR_API_TOKEN`, `YOUR_ORG_ID`, `https://your-instance.railway.app`, etc. Do not include real credentials or URLs.

Trace the actual endpoint paths, request/response models, and required fields from the router code. Do not guess at payload shapes.

---

### Evidence standard

- Every claim about what an auth type can access must be traceable to a specific code path (file + function).
- Every payload shape must come from the actual Pydantic model or request handler in the code.
- Every scoping claim must be verified by tracing the query logic (how does the code filter by org_id?).
- If something is ambiguous in the code (e.g., an endpoint doesn't explicitly scope by org), document that as a finding.
- If you discover auth gaps (endpoints that don't check auth, or scoping that's missing), note them in a "Findings" section at the bottom but do not fix them.

Commit standalone.

---

## Deliverable 2: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: created `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` covering auth types, data visibility by auth context, connection patterns for 4 client types, write paths, credential disambiguation, schema scoping reference, and 6 practical curl examples. Note any auth gaps or ambiguities discovered.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive.
- **No schema changes.** No migrations.
- **No deploy commands.** Do not push.
- **No fixes to auth gaps discovered.** Document them, do not fix them.
- **No changes to `docs/AUTH_MODEL.md`.** The new guide supplements it, does not replace it.
- **No changes to any other existing documentation files.** Only create the new guide and append to the work log.
- **No changes to `CLAUDE.md`.** The chief agent will decide if/when to reference the new guide from CLAUDE.md.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Guide: full path, section count, total curl examples included
(b) Auth types documented: list each auth type covered and whether the code matched what `docs/AUTH_MODEL.md` claims
(c) Data visibility: for each auth type, one-sentence summary of what's visible
(d) Scoping table: how many tables covered, how many are org-scoped vs global
(e) Findings: any auth gaps, missing scoping, ambiguous behavior, or discrepancies between code and existing docs
(f) Anything to flag — especially: endpoints that don't check auth, org scoping that's missing where it should exist, credential types not documented in AUTH_MODEL.md
