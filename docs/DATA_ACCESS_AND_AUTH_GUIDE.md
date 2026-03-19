# Data Access & Auth Guide

**Last updated:** 2026-03-18T12:00:00Z

Central reference for: what data is available to whom, under what credentials, and how to access it from different contexts.

Supplements `docs/AUTH_MODEL.md`. Every claim is grounded in the actual code — code references are inline.

---

## 1. Auth Types at a Glance

| Auth Type | Header Format | Who Uses It | What It Unlocks | Org-Scoped? |
|---|---|---|---|---|
| Tenant JWT session | `Authorization: Bearer <jwt>` | Frontend users, dashboard | All tenant endpoints (`/api/auth/*`, `/api/companies/*`, `/api/blueprints/*`, `/api/v1/*` entity/execute/batch) | Yes — `org_id` baked into JWT claims |
| Tenant API token | `Authorization: Bearer <token>` | Scripts, automations, external integrations | Same tenant endpoints as JWT | Yes — `org_id` stored in `api_tokens` table row |
| Super-admin (API key or JWT) | `Authorization: Bearer <key_or_jwt>` | Admin tools, cross-org management, operational queries | All `/api/super-admin/*` CRUD, `/api/v1/execute` (with org_id/company_id in body), FMCSA endpoints, all entity query endpoints including `/companies` and `/persons` (with org_id in body), federal data endpoints | Configurable — no inherent org; must specify org context on execution/entity endpoints |
| Internal service auth | `Authorization: Bearer <internal_key>` + `x-internal-org-id` + `x-internal-company-id` headers | Trigger.dev tasks | `/api/internal/*` callbacks, `/api/v1/execute` (via `get_current_auth` matching internal key) | Yes — org/company passed via headers |

---

## 2. Data Visibility by Auth Context

### Tenant User (JWT or API Token)

**Code path:** `app/auth/dependencies.py:get_current_auth()` → produces `AuthContext` with `org_id`, optional `company_id`, `role`.

- **Entity tables** (`company_entities`, `person_entities`, `job_posting_entities`): scoped by `org_id` column. Query always includes `.eq("org_id", org_id)` (see `entities_v1.py`).
- **Execution lineage** (`submissions`, `pipeline_runs`, `step_results`): scoped by `org_id` column on each table. Tenant flow endpoints filter by `auth.org_id` (see `tenant_flow.py:80+`).
- **Operation runs** (`operation_runs`): scoped by `org_id` column via `persist_operation_execution()`.
- **Dedicated entity tables** (`icp_job_titles`, `company_customers`, `company_ads`, `gemini_icp_job_titles`, `salesnav_prospects`, `company_intel_briefings`, `person_intel_briefings`, `entity_relationships`, `entity_timeline`, `entity_snapshots`): all scoped by `org_id` — service functions accept `org_id` parameter extracted from auth.
- **Company-admin/member sub-scoping**: roles `company_admin` and `member` are additionally restricted to entities associated with their `company_id` via `company_entity_associations` lookups (see `entities_v1.py:354-375`).
- **Global data visible to tenants**: Blueprints are org-scoped (tenant sees only own org's blueprints, `tenant_blueprints.py:67`). Steps are global — `tenant_steps.py` lists all active steps without org filtering. FMCSA endpoints use flexible auth and return global data. Federal leads and SBA data are global (no org filter in query functions).
- **Cannot see other orgs' data**: confirmed. All tenant queries enforce `.eq("org_id", auth.org_id)`.

### Super Admin

**Code path:** `app/auth/super_admin.py:get_current_super_admin()` → produces `SuperAdminContext` with `super_admin_id` and `email` only (no org_id).

- **Super-admin CRUD endpoints** (`/api/super-admin/*`): full cross-org visibility. `orgs/list` returns all orgs, `companies/list` returns all companies (optionally filtered by org_id), `users/list` returns all users, etc. (see `super_admin_api.py`).
- **`/api/v1/execute`**: super-admin **must** pass `org_id` + `company_id` in the request body. The code synthesizes a temporary `AuthContext` from these fields to create execution lineage under the correct org (`execute_v1.py:278-289`).
- **`/api/v1/batch/submit`**: same requirement — `org_id` + `company_id` required in body (`execute_v1.py:1283-1289`).
- **`/api/v1/batch/status`**: super-admin can query any submission. If `org_id` is passed, it filters; otherwise it queries by `submission_id` only (`execute_v1.py:1399-1401`).
- **Entity query endpoints** (`/api/v1/entities/*`):
  - `companies` and `persons`: use `_resolve_flexible_auth`, so super-admin works. Must pass `org_id` in request body — required for super-admin (400 if missing).
  - `job-postings`, `timeline`, `snapshots`: use `_resolve_flexible_auth`, so super-admin works. Must pass `org_id` in request body — required for super-admin.
  - Dedicated table queries (`icp-job-titles`, `company-customers`, etc.): use `_resolve_flexible_auth`. Super-admin must pass `org_id` in body.
  - Federal leads, SBA, FMCSA analytics: use `_resolve_flexible_auth`. Data is global, not org-scoped.
- **FMCSA endpoints** (`/api/v1/fmcsa-*`): flexible auth accepts super-admin. Data is global.

### Internal Service Auth (Trigger.dev)

**Code path:** `app/auth/dependencies.py:get_current_auth()` lines 47-61 — if token matches `settings.internal_api_key`, creates `AuthContext` with `org_id` from `x-internal-org-id` header (required), `company_id` from `x-internal-company-id` (optional), role `org_admin`, auth_method `api_token`.

- **`/api/internal/*` endpoints**: validated by `require_internal_key()` or `require_internal_context()` in `internal.py:66-97`. These are separate dependency functions that check the same `INTERNAL_API_KEY`.
- **`/api/v1/execute`**: internal auth works because `get_current_auth` matches the internal key and produces an `AuthContext`. The `_resolve_flexible_auth` wrapper tries super-admin first (fails), then falls back to `get_current_auth` which succeeds.
- **Entity query endpoints**: internal auth can access any endpoint that uses `get_current_auth` (companies, persons) or `_resolve_flexible_auth`. The `x-internal-org-id` header provides the org context.
- **Missing `x-internal-org-id`**: raises 401 "Missing x-internal-org-id for internal authorization" (`dependencies.py:50-53`).
- **Missing `x-internal-company-id`**: allowed — `company_id` is set to `None` in the resulting `AuthContext`.

### FMCSA and Federal Data Endpoints

- **FMCSA endpoints** (`/api/v1/fmcsa-carriers/*`, `/api/v1/fmcsa-crashes/*`, `/api/v1/fmcsa-signals/*`): all use `_resolve_flexible_auth` (accepts super-admin or tenant auth). Data is **globally accessible** — queries do not filter by `org_id`. Any authenticated user sees the same FMCSA data.
- **Federal contract leads** (`/api/v1/federal-contract-leads/*`): use `_resolve_flexible_auth`. Data is **globally accessible** — `query_federal_contract_leads()` queries the `mv_federal_contract_leads` materialized view without org filtering.
- **SBA loans** (`/api/v1/sba-loans/*`): use `_resolve_flexible_auth`. Data is **globally accessible**.
- **FMCSA analytics** (`/api/v1/fmcsa/analytics/*`): use `_resolve_flexible_auth`. Data is **globally accessible**.

---

## 3. Auth Paths Explained

### Tenant JWT Session

**How obtained:** `POST /api/auth/login` with email + password.

```
Request:  { "email": "user@example.com", "password": "secret" }
Response: { "data": { "access_token": "<jwt>", "token_type": "bearer" } }
```

**Code:** `app/routers/auth.py:login()` → looks up user in `users` table by email, verifies bcrypt password hash, calls `create_tenant_session_jwt()`.

**JWT claims** (from `app/auth/tokens.py:24-45`):
- `type`: `"session"`
- `sub` / `user_id`: user UUID
- `org_id`: org UUID
- `company_id`: company UUID or null
- `role`: `"org_admin"`, `"company_admin"`, or `"member"`
- `iat`: issued-at timestamp
- `exp`: expiry timestamp

**Expiry:** 24 hours (default `expires_in_hours=24` in `create_tenant_session_jwt()`).

**Validation:** `decode_tenant_session_jwt()` in `tokens.py:48-76` decodes with `jwt_secret` (HS256), checks `type == "session"`, extracts claims into `SessionTokenPayload`.

**Header format:** `Authorization: Bearer <jwt_token>`

### Tenant API Token

**How created:** Super-admin calls `POST /api/super-admin/api-tokens/create` with `{ "user_id": "<uuid>", "name": "my-token" }`. The endpoint looks up the user's `org_id`, `company_id`, and `role`, generates a random 40-byte URL-safe token, stores its SHA-256 hash in `api_tokens`, and returns the raw token once (`super_admin_api.py:589-633`).

**What it binds to:** `org_id`, `company_id`, and `role` — all inherited from the user record at creation time.

**Validation:** `get_current_auth()` in `dependencies.py:82-123` hashes the bearer token with SHA-256, looks up the hash in `api_tokens` table, checks `revoked_at` is null and `expires_at` is not past, then returns `AuthContext`.

**Expiry:** optional — `expires_at` can be set at creation time. If null, the token never expires.

**Difference from JWT:** API tokens have no user_id in the resulting `AuthContext` (`user_id=None`). They carry org/company/role context from the `api_tokens` table row, not from JWT claims.

**Header format:** `Authorization: Bearer <raw_api_token>`

### Super-Admin Auth

Super-admin auth has two sub-paths, both resolved by `get_current_super_admin()` in `super_admin.py:89-130`:

**Path A — Static API key:**
- Configured via `SUPER_ADMIN_API_KEY` env var.
- Validated by direct string comparison (`super_admin.py:80`).
- Produces `SuperAdminContext(super_admin_id=UUID("00000000-..."), email="api-key@super-admin")`.

**Path B — Super-admin JWT:**
- Obtained via `POST /api/super-admin/login` with email + password (checked against `super_admins` table with bcrypt).
- JWT signed with `super_admin_jwt_secret` (separate from tenant JWT secret).
- Claims: `type: "super_admin"`, `sub`, `email`, `iat`, `exp`.
- Expiry: 24 hours.
- Validation: decodes JWT, then verifies admin exists and is active in `super_admins` table.
- Produces `SuperAdminContext(super_admin_id=<real_uuid>, email=<real_email>)`.

**When additional context is needed:** On `/api/v1/execute` and `/api/v1/batch/submit`, super-admin must pass `org_id` and `company_id` in the request body because executions create org-scoped records (submissions, pipeline runs, operation runs).

### Internal Service Auth

**Key configuration:**
- FastAPI side: `INTERNAL_API_KEY` env var (loaded via `app/config.py` settings).
- Trigger.dev side: `DATA_ENGINE_INTERNAL_API_KEY` or `INTERNAL_API_KEY` env var (resolved in `internal-api.ts:103-107`).

**How Trigger.dev passes org context:** Both `InternalApiClient` (dedicated workflows, `trigger/src/workflows/internal-api.ts`) and the generic `internalPost()` function (legacy `run-pipeline.ts`) set org headers on every request:
- `Authorization: Bearer <internalApiKey>`
- `x-internal-org-id: <orgId>` (from pipeline payload `org_id`)
- `x-internal-company-id: <companyId>` (from pipeline payload `company_id`)

**FastAPI validation (internal endpoints):** `require_internal_key()` and `require_internal_context()` in `internal.py:66-97` check the bearer token against `settings.internal_api_key`. `require_internal_context()` additionally extracts `x-internal-org-id` (required) and `x-internal-company-id` (optional) and returns them as a dict.

**FastAPI validation (tenant endpoints):** `get_current_auth()` in `dependencies.py:47-61` checks if the token matches `settings.internal_api_key` before trying JWT decode. If it matches, it creates an `AuthContext` with org/company from the headers.

**Endpoints accepting internal auth:**
- All `/api/internal/*` endpoints (pipeline run CRUD, step result updates, entity state upserts, entity timeline recording, relationship recording, dedicated table upserts, fan-out, FMCSA feed upserts)
- `/api/v1/execute` (via `get_current_auth` fallback)
- Any endpoint using `_resolve_flexible_auth` (which calls `get_current_auth` as fallback)

---

## 4. Connecting from Different Contexts

### From a Frontend App (Dashboard / assistant-ui)

1. **Login:** `POST /api/auth/login` with `{ "email": "...", "password": "..." }`
2. **Store token:** Save `data.access_token` from the response (e.g., in-memory or secure storage).
3. **Use token:** Include `Authorization: Bearer <access_token>` on all subsequent requests.
4. **Token refresh:** Tokens expire after 24 hours. There is no refresh endpoint — re-login is required.
5. **Verify session:** `POST /api/auth/me` returns the current user's `org_id`, `company_id`, `role`.

### From Hex or a Data Notebook (Direct Postgres)

Direct Postgres access bypasses the API entirely. **There is no auth scoping at the database level** — you see all orgs, all schemas, all data.

**Connection pattern:**
```bash
doppler run -p data-engine-x-api -c prd -- psql
```

This injects `DATABASE_URL` from Doppler and opens a psql session.

**Schema navigation:**
- `ops.*` — orchestration tables (submissions, pipeline_runs, step_results, etc.)
- `entities.*` — domain data (company_entities, person_entities, FMCSA tables, etc.)
- `public.*` — platform tables (orgs, companies, users, super_admins, api_tokens, steps, blueprints, etc.)

**Caution:** You are responsible for adding `WHERE org_id = '...'` filters yourself when querying org-scoped tables. Without this, you see all tenants' data.

### From a Script or Automation

1. **Obtain an API token:** Ask a super-admin to create one via `POST /api/super-admin/api-tokens/create`.
2. **Use token:** `Authorization: Bearer <api_token>` on all requests.
3. **Token is org-scoped:** All queries and executions are automatically scoped to the token's org.

### From Trigger.dev (Internal Service)

Trigger tasks use the `InternalApiClient` class from `trigger/src/workflows/internal-api.ts`.

**Setup:**
```typescript
import { createInternalApiClient } from "../workflows/internal-api";

const api = createInternalApiClient({
  authContext: { orgId: payload.orgId, companyId: payload.companyId },
});
```

**Environment variables** (set in Trigger.dev runtime, not Doppler):
- `DATA_ENGINE_API_URL` — FastAPI base URL
- `DATA_ENGINE_INTERNAL_API_KEY` — internal service key

**How context flows:** `orgId` and `companyId` come from the Trigger task payload (which originates from the submission/pipeline run that spawned the task). The client sets `x-internal-org-id` and `x-internal-company-id` headers on every POST request.

---

## 5. Writing Data — Ingest & Write Paths

### Batch Submit (Enrichment Pipeline)

**Endpoint:** `POST /api/v1/batch/submit`

**Auth:** Tenant JWT/API token (org auto-scoped) or super-admin (org_id + company_id in body).

**Request shape** (from `execute_v1.py:BatchSubmitRequest`):
```json
{
  "blueprint_id": "<uuid>",
  "entities": [
    { "entity_type": "company", "input": { "domain": "example.com" } },
    { "entity_type": "company", "input": { "domain": "other.com" } }
  ],
  "org_id": "<uuid>",          // required for super-admin only
  "company_id": "<uuid>",      // required for super-admin and org_admin
  "source": "api_v1_batch",    // optional
  "metadata": {}               // optional
}
```

**What it creates:** submission → one pipeline_run per entity → step_results pre-created for each blueprint step → Trigger.dev tasks dispatched.

### Single Operation Execute

**Endpoint:** `POST /api/v1/execute`

**Auth:** Tenant JWT/API token, super-admin (with org_id + company_id in body), or internal service auth.

**Request shape** (from `execute_v1.py:ExecuteV1Request`):
```json
{
  "operation_id": "company.enrich.profile",
  "entity_type": "company",
  "input": { "domain": "example.com" },
  "options": {},                // optional
  "org_id": "<uuid>",          // required for super-admin only
  "company_id": "<uuid>"       // required for super-admin only
}
```

### Internal Callbacks (Trigger → FastAPI)

Trigger.dev tasks call back to `/api/internal/*` endpoints during pipeline execution:

| Endpoint | Purpose |
|---|---|
| `POST /api/internal/pipeline-runs/update-status` | Update pipeline run status (running/succeeded/failed) |
| `POST /api/internal/step-results/update` | Update individual step result with output/error |
| `POST /api/internal/step-results/mark-remaining-skipped` | Skip remaining steps on failure |
| `POST /api/internal/entity-state/upsert` | Upsert company/person/job entity from cumulative context |
| `POST /api/internal/entity-timeline/record-step-event` | Record entity timeline event |
| `POST /api/internal/entity-relationships/record` | Record entity relationship |
| `POST /api/internal/entity-relationships/record-batch` | Batch record relationships |
| `POST /api/internal/submissions/update-status` | Update submission status |
| `POST /api/internal/submissions/sync-status` | Recompute submission status from pipeline runs |
| `POST /api/internal/pipeline-runs/fan-out` | Create child pipeline runs for fan-out |
| `POST /api/internal/icp-job-titles/upsert` | Upsert ICP job titles |
| `POST /api/internal/company-customers/upsert` | Upsert company customers |
| `POST /api/internal/company-intel-briefings/upsert` | Upsert company intel briefing |
| `POST /api/internal/person-intel-briefings/upsert` | Upsert person intel briefing |
| `POST /api/internal/gemini-icp-job-titles/upsert` | Upsert Gemini ICP titles |
| `POST /api/internal/company-ads/upsert` | Upsert company ads |
| `POST /api/internal/salesnav-prospects/upsert` | Upsert Sales Nav prospects |

All use internal service auth with `x-internal-org-id` and `x-internal-company-id` headers.

FMCSA feed upsert endpoints (motor_carrier_census_records, carrier_inspections, insurance_policies, etc.) use `require_internal_key()` only — they do not require org context because FMCSA data is global.

### Entity Ingest Path (Clay / External)

**Endpoint:** `POST /api/v1/entities/ingest`

**Auth:** Tenant JWT/API token or super-admin (with org_id in body).

**Request shape** (from `entities_v1.py:EntityIngestRequest`):
```json
{
  "entity_type": "company",
  "source_provider": "clay.find_companies",
  "payload": { "domain": "example.com", "name": "Example Inc", ... },
  "org_id": "<uuid>",          // super-admin only
  "company_id": "<uuid>"       // super-admin only
}
```

This is the path used by Clay ingestion (`external.ingest.clay.find_companies` / `external.ingest.clay.find_people`). It calls `ingest_entity()` which resolves or creates entity records in the entities schema.

### FMCSA Feed Ingestion

FMCSA feed data is ingested by **Trigger.dev tasks** that write directly to the database via internal API callbacks:

- Tasks in `trigger/src/tasks/` fetch FMCSA CSV feeds and call internal endpoints like `POST /api/internal/motor-carrier-census-records/upsert`, `POST /api/internal/carrier-inspections/upsert`, etc.
- Auth: internal service key (no org context needed — FMCSA data is global).
- The internal endpoints call service functions that do direct Supabase upserts into `entities.*` FMCSA tables.

---

## 6. API Token vs API Key Clarity

| Credential | What It Is | Where Configured/Created | Which Endpoints Accept It | Org-Bound? |
|---|---|---|---|---|
| Super-admin API key | Single static string | `SUPER_ADMIN_API_KEY` env var | All `/api/super-admin/*`, `/api/v1/execute` (with org_id/company_id), FMCSA (flexible auth), entity queries (flexible auth), federal data (flexible auth) | No (cross-org) |
| Super-admin JWT | Session token for admin users | `POST /api/super-admin/login`, signed with `SUPER_ADMIN_JWT_SECRET` | Same as API key | No (cross-org) |
| Tenant API token | Per-org long-lived token | Created via `POST /api/super-admin/api-tokens/create`, stored as SHA-256 hash in `api_tokens` table | All tenant endpoints (`/api/auth/me`, `/api/companies/*`, `/api/blueprints/*`, `/api/v1/*`) | Yes (org_id from token record) |
| Tenant JWT | Short-lived session token (24h) | Issued by `POST /api/auth/login`, signed with `JWT_SECRET` | Same as tenant API token | Yes (org_id from JWT claims) |
| Internal API key | Service-to-service static string | `INTERNAL_API_KEY` env var (FastAPI), `DATA_ENGINE_INTERNAL_API_KEY` env var (Trigger.dev) | `/api/internal/*`, `/api/v1/execute`, any endpoint using `get_current_auth` or `_resolve_flexible_auth` | No (org via headers) |

**Note:** The super-admin API key and the internal API key are different values serving different purposes. The super-admin key grants admin-level access; the internal key grants service-level access with org context from headers.

---

## 7. Schema & Table Scoping Reference

### `public` schema — Platform tables

| Table | Scoping | Scoped By | Notes |
|---|---|---|---|
| `public.orgs` | N/A | — | Top-level tenant records |
| `public.companies` | Org-scoped | `org_id` column | Companies belong to orgs |
| `public.users` | Org-scoped | `org_id` column | Users belong to orgs, optionally to companies |
| `public.super_admins` | Global | — | Platform admin accounts |
| `public.api_tokens` | Org-scoped | `org_id` column | API tokens inherit org from creating user |
| `public.steps` | Global | — | Step registry, shared across all orgs |
| `public.blueprints` | Org-scoped | `org_id` column | Pipeline templates owned by orgs |
| `public.blueprint_steps` | Blueprint-scoped | `blueprint_id` FK | Steps within a blueprint |

### `ops` schema — Orchestration tables

| Table | Scoping | Scoped By | Notes |
|---|---|---|---|
| `ops.submissions` | Org-scoped | `org_id` column, `company_id` column | Pipeline submission records |
| `ops.pipeline_runs` | Org-scoped | `org_id` column, `submission_id` FK | Individual pipeline executions |
| `ops.step_results` | Org-scoped | `org_id` column, `pipeline_run_id` FK | Per-step execution results |
| `ops.operation_runs` | Org-scoped | `org_id` column | Individual operation execution audit log |

### `entities` schema — Domain data (org-scoped)

| Table | Scoping | Scoped By | Notes |
|---|---|---|---|
| `entities.company_entities` | Org-scoped | `org_id` column | Canonical company records |
| `entities.person_entities` | Org-scoped | `org_id` column | Canonical person records |
| `entities.job_posting_entities` | Org-scoped | `org_id` column | Job posting records |
| `entities.entity_timeline` | Org-scoped | `org_id` column | Entity change/event timeline |
| `entities.entity_snapshots` | Org-scoped | `org_id` column | Point-in-time entity snapshots |
| `entities.entity_relationships` | Org-scoped | `org_id` column | Cross-entity relationships |
| `entities.company_entity_associations` | Org-scoped | `org_id`, `company_id` | Maps entities to companies for sub-org scoping |
| `entities.icp_job_titles` | Org-scoped | `org_id` column | ICP job title discoveries |
| `entities.extracted_icp_job_title_details` | Org-scoped | `org_id` column | Detailed ICP title extractions |
| `entities.company_customers` | Org-scoped | `org_id` column | Discovered customer relationships |
| `entities.gemini_icp_job_titles` | Org-scoped | `org_id` column | Gemini-derived ICP titles |
| `entities.company_ads` | Org-scoped | `org_id` column | Company advertising data |
| `entities.salesnav_prospects` | Org-scoped | `org_id` column | Sales Navigator prospect data |
| `entities.company_intel_briefings` | Org-scoped | `org_id` column | Company intelligence briefings |
| `entities.person_intel_briefings` | Org-scoped | `org_id` column | Person intelligence briefings |

### `entities` schema — Global data (no org scoping)

| Table | Scoping | Notes |
|---|---|---|
| `entities.motor_carrier_census_records` | Global | FMCSA carrier census data |
| `entities.carrier_inspections` | Global | FMCSA inspection records |
| `entities.carrier_inspection_violations` | Global | FMCSA inspection violations |
| `entities.carrier_registrations` | Global | FMCSA carrier registrations |
| `entities.carrier_safety_basic_measures` | Global | FMCSA BASIC safety measures |
| `entities.carrier_safety_basic_percentiles` | Global | FMCSA BASIC percentiles |
| `entities.commercial_vehicle_crashes` | Global | FMCSA crash records |
| `entities.insurance_policies` | Global | FMCSA insurance policies |
| `entities.insurance_policy_filings` | Global | FMCSA insurance filings |
| `entities.insurance_policy_history_events` | Global | FMCSA insurance history |
| `entities.insurance_filing_rejections` | Global | FMCSA filing rejections |
| `entities.operating_authority_histories` | Global | FMCSA authority history |
| `entities.operating_authority_revocations` | Global | FMCSA authority revocations |
| `entities.out_of_service_orders` | Global | FMCSA OOS orders |
| `entities.process_agent_filings` | Global | FMCSA process agent filings |
| `entities.vehicle_inspection_citations` | Global | FMCSA vehicle citations |
| `entities.vehicle_inspection_special_studies` | Global | FMCSA special studies |
| `entities.vehicle_inspection_units` | Global | FMCSA vehicle inspection units |
| `entities.fmcsa_carrier_signals` | Global | FMCSA signal detection results (0 rows) |
| `entities.sam_gov_entities` | Global | SAM.gov entity registrations |
| `entities.sba_7a_loans` | Global | SBA 7(a) loan records |
| `entities.usaspending_contracts` | Global | USASpending federal contract data |
| `entities.mv_federal_contract_leads` | Global | Materialized view joining federal data |

**Summary:** 4 `public` platform tables are global, 4 are org-scoped. 4 `ops` tables are org-scoped. 16 `entities` tables are org-scoped. 22+ `entities` tables are global (FMCSA, federal data).

---

## 8. Practical Examples

### Example 1: Querying entities as a tenant (API token)

```bash
curl -X POST https://your-instance.railway.app/api/v1/entities/companies \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "page": 1,
    "per_page": 10
  }'
```

Returns company entities automatically scoped to the token's `org_id`. Response:
```json
{
  "data": {
    "items": [ { "entity_id": "...", "org_id": "...", "canonical_domain": "...", ... } ],
    "pagination": { "page": 1, "per_page": 10, "returned": 10 }
  }
}
```

### Example 2: Submitting a batch as a tenant

```bash
curl -X POST https://your-instance.railway.app/api/v1/batch/submit \
  -H "Authorization: Bearer YOUR_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "blueprint_id": "YOUR_BLUEPRINT_ID",
    "company_id": "YOUR_COMPANY_ID",
    "entities": [
      { "entity_type": "company", "input": { "domain": "example.com" } },
      { "entity_type": "company", "input": { "domain": "acme.co" } }
    ],
    "source": "api_v1_batch"
  }'
```

Creates a submission with one pipeline run per entity. Returns submission ID and pipeline run IDs.

### Example 3: Querying entities as super admin

Super-admin can query all entity endpoints including `/api/v1/entities/companies` and `/api/v1/entities/persons`. Must pass `org_id` in the request body — required for all entity queries as super-admin (returns 400 without it).

```bash
curl -X POST https://your-instance.railway.app/api/v1/entities/companies \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "org_id": "YOUR_ORG_ID",
    "page": 1,
    "per_page": 10
  }'
```

Works the same for `/api/v1/entities/persons`, `/api/v1/entities/job-postings`, and all dedicated table query endpoints. Super-admin must always provide `org_id` in the body.

### Example 4: Hitting an internal endpoint with service auth

```bash
curl -X POST https://your-instance.railway.app/api/internal/step-results/update \
  -H "Authorization: Bearer YOUR_INTERNAL_API_KEY" \
  -H "x-internal-org-id: YOUR_ORG_ID" \
  -H "x-internal-company-id: YOUR_COMPANY_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "step_result_id": "STEP_RESULT_UUID",
    "status": "succeeded",
    "output_payload": { "result": "enriched_data" }
  }'
```

All three headers are required (company_id is technically optional for some endpoints but recommended).

### Example 5: Querying FMCSA data (flexible auth)

```bash
curl -X POST https://your-instance.railway.app/api/v1/fmcsa-carriers/query \
  -H "Authorization: Bearer YOUR_API_TOKEN_OR_SUPER_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "state": "TX",
    "min_power_units": 50,
    "limit": 10
  }'
```

Works with any auth type (tenant or super-admin). Returns the same FMCSA data regardless of org — it is globally accessible.

### Example 6: Creating an API token via super admin

```bash
curl -X POST https://your-instance.railway.app/api/super-admin/api-tokens/create \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "TARGET_USER_UUID",
    "name": "automation-token"
  }'
```

Response includes the raw token (shown only once):
```json
{
  "data": {
    "id": "TOKEN_UUID",
    "token": "RAW_TOKEN_VALUE_SAVE_THIS",
    "name": "automation-token",
    "org_id": "ORG_UUID_FROM_USER",
    "company_id": "COMPANY_UUID_OR_NULL",
    "role": "org_admin",
    "user_id": "TARGET_USER_UUID",
    "created_at": "2026-03-18T..."
  }
}
```

The token inherits `org_id`, `company_id`, and `role` from the target user. Optional `expires_at` field can be passed to set an expiry.

---

## Findings

### Auth Gaps Discovered

1. **`/api/v1/entities/companies` and `/api/v1/entities/persons` did not accept super-admin auth (fixed).** These endpoints previously used `Depends(get_current_auth)` instead of `Depends(_resolve_flexible_auth)`. Both now use `_resolve_flexible_auth` — super-admin can query them with `org_id` in the request body, consistent with all other entity endpoints.

2. **Internal auth `auth_method` is `"api_token"`.** When the internal API key matches in `get_current_auth()`, the resulting `AuthContext` has `auth_method="api_token"` (line 61), making it indistinguishable from a tenant API token in downstream code. This is not a security issue but could cause confusion in audit logging.

3. **Internal auth role is hardcoded to `"org_admin"`.** The `AuthContext` produced by internal auth always has `role="org_admin"` (line 59), regardless of the actual org/user context. This means Trigger.dev tasks bypass company-scoped restrictions.

4. **`/api/v1/batch/status` — super-admin without `org_id` sees any submission.** If super-admin doesn't pass `org_id`, the query has no org filter (`execute_v1.py:1399-1401`), allowing access to any submission by ID. This is likely intentional but worth noting.

5. **Federal leads and SBA endpoints have no org scoping.** `query_federal_contract_leads()`, `query_sba_loans()`, and related endpoints return data without any org filter. Any authenticated user (including tenants) sees the full federal dataset. This is by design for public federal data.

6. **`api_tokens` table is queried without schema prefix.** In `dependencies.py:84`, the API token lookup uses `client.table("api_tokens")` without `.schema("public")`. This works because `api_tokens` is in the `public` schema (the default), but it is inconsistent with the convention of explicit schema qualification documented in memory.

### Discrepancies with AUTH_MODEL.md

- AUTH_MODEL.md states internal auth's `x-internal-company-id` is "optional" — confirmed correct in code.
- AUTH_MODEL.md lists four auth paths — confirmed, all four exist in code. However, AUTH_MODEL.md does not mention the super-admin JWT path (only the API key). In practice, `get_current_super_admin()` supports both API key and JWT.
- AUTH_MODEL.md states "Step registry is global; blueprints are org-scoped" — confirmed. Tenant `steps/list` returns all active steps without org filter; blueprints filter by `org_id`.
