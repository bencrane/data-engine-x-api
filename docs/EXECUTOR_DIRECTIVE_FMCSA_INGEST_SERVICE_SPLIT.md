# Executor Directive: FMCSA Ingest Service Split

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA ingestion pipeline shares a FastAPI process with the entire data-engine-x-api. Every push to `main` triggers a Railway auto-deploy that restarts the process, killing in-flight FMCSA chunk POST requests mid-feed. A single feed runs 25–60+ minutes across hundreds of sequential chunk POSTs. A mid-run restart means the entire feed re-runs from scratch. The repo is under active development, so this happens constantly and makes FMCSA ingestion unreliable. This directive splits the FMCSA bulk write ingestion into a separate FastAPI service — same repo, same database, independent deploy cycle.

---

## Reference Documents (Read Before Starting)

**Must read — existing code:**
- `CLAUDE.md` — project conventions, deploy protocol, auth model
- `app/main.py` — the current FastAPI app entrypoint (what NOT to break)
- `app/routers/internal.py` — the internal router containing all FMCSA write endpoints (lines 806–1055: the 16 `upsert-batch` endpoints and the `ingest-artifact` endpoint), the request models (`InternalUpsertFmcsaDailyDiffBatchRequest` at line 313, `InternalFmcsaArtifactIngestRequest` at line 327), the `require_internal_key` auth dependency (line 66), and the `_build_fmcsa_source_context` helper (line 461)
- `app/services/fmcsa_daily_diff_common.py` — the shared COPY+merge persistence layer (connection pool, row builder, `upsert_fmcsa_daily_diff_rows`)
- `app/services/fmcsa_artifact_ingest.py` — the artifact ingest service (Supabase storage download → chunked upsert)
- `app/middleware/gzip_request.py` — GzipRequestMiddleware (required because Trigger.dev sends gzip-compressed request bodies)
- `app/config.py` — Settings model with `database_url` and `internal_api_key`
- `Dockerfile` — current container setup
- `trigger/src/workflows/internal-api.ts` — the `InternalApiClient` and `resolveInternalApiConfig()` that reads `DATA_ENGINE_API_URL`
- `trigger/src/workflows/fmcsa-daily-diff.ts` — the workflow that calls FastAPI FMCSA endpoints; specifically the `createClient` function (line 489) that builds the API client

**Must read — per-table upsert services (the imports the new router needs):**
- `app/services/carrier_registrations.py`
- `app/services/carrier_inspections.py`
- `app/services/carrier_inspection_violations.py`
- `app/services/carrier_safety_basic_measures.py`
- `app/services/carrier_safety_basic_percentiles.py`
- `app/services/commercial_vehicle_crashes.py`
- `app/services/insurance_policies.py`
- `app/services/insurance_policy_filings.py`
- `app/services/insurance_policy_history_events.py`
- `app/services/insurance_filing_rejections.py`
- `app/services/operating_authority_histories.py`
- `app/services/operating_authority_revocations.py`
- `app/services/out_of_service_orders.py`
- `app/services/process_agent_filings.py`
- `app/services/vehicle_inspection_units.py`
- `app/services/vehicle_inspection_citations.py`
- `app/services/vehicle_inspection_special_studies.py`
- `app/services/motor_carrier_census_records.py`

---

## Critical Technical Constraints

### 1. No Duplication of Persistence Logic

The new service imports the existing persistence layer — `app/services/fmcsa_daily_diff_common.py` and the 18 per-table upsert services. The COPY+merge logic, conflict semantics, phase instrumentation, and connection pool configuration are NOT duplicated. The new service is a thin HTTP layer over the same service functions.

### 2. Same Database

Both services connect to the same Supabase/Postgres instance via `DATABASE_URL`. The connection pool in `fmcsa_daily_diff_common.py` initializes lazily per-process — each service gets its own pool instance but hits the same database.

### 3. Internal Auth Only

The ingest service only accepts `INTERNAL_API_KEY` bearer token auth — the same `require_internal_key` pattern used in `app/routers/internal.py`. No tenant auth, no JWT, no CORS, no super-admin.

### 4. GzipRequestMiddleware Required

Trigger.dev sends all chunk POST payloads with `Content-Encoding: gzip`. The ingest service must include `GzipRequestMiddleware` or the payloads will be unparseable.

### 5. Leave Main API Unchanged

The existing FMCSA endpoints in `app/routers/internal.py` stay as-is. Do not remove them. They remain as dead code in the main API until a separate cleanup directive.

### 6. Endpoint Path Compatibility

The new service must serve the exact same endpoint paths that Trigger.dev currently calls. Every `internalUpsertPath` in the feed configs (e.g., `/api/internal/motor-carrier-census-records/upsert-batch`) and the artifact ingest path (`/api/internal/fmcsa/ingest-artifact`) must work unchanged. Trigger.dev just switches the base URL — the paths stay identical.

---

## File Structure

Create these new files:

| File | Purpose |
|---|---|
| `app/routers/fmcsa_ingest.py` | Dedicated router with all 17 FMCSA write endpoints |
| `app/fmcsa_ingest_main.py` | Minimal FastAPI app entrypoint for the ingest service |
| `Dockerfile.fmcsa-ingest` | Container definition for the ingest service |
| `docs/RAILWAY_FMCSA_INGEST_SERVICE_SETUP.md` | Railway configuration instructions |
| `tests/test_fmcsa_ingest_service.py` | Tests for the new service |

Modify this existing file:

| File | Change |
|---|---|
| `trigger/src/workflows/fmcsa-daily-diff.ts` | Read `FMCSA_INGEST_API_URL` in `createClient` |

---

## Deliverable 1: FMCSA Ingest Router

Create `app/routers/fmcsa_ingest.py`.

This file extracts the FMCSA write endpoints from `app/routers/internal.py` into a dedicated router. It is a self-contained module that the new ingest service mounts.

**What to include:**

1. **Auth dependency** — replicate `require_internal_key` locally in this file (copy the function, do not import from `internal.py`). Rationale: the ingest service should not import `app/routers/internal.py` at all — that module pulls in dozens of unrelated dependencies (entity state, timeline, orchestration). A 10-line auth function is cheaper than importing the entire internal router's dependency tree.

2. **Request models** — replicate `InternalFmcsaDailyDiffRow`, `InternalUpsertFmcsaDailyDiffBatchRequest`, and `InternalFmcsaArtifactIngestRequest` locally. Same rationale — avoid importing `internal.py`.

3. **`_build_fmcsa_source_context` helper** — replicate locally.

4. **16 upsert-batch endpoints** — one per table, same paths as in `internal.py`:
   - `POST /operating-authority-histories/upsert-batch`
   - `POST /operating-authority-revocations/upsert-batch`
   - `POST /insurance-policies/upsert-batch`
   - `POST /insurance-policy-filings/upsert-batch`
   - `POST /insurance-policy-history-events/upsert-batch`
   - `POST /carrier-registrations/upsert-batch`
   - `POST /carrier-safety-basic-measures/upsert-batch`
   - `POST /commercial-vehicle-crashes/upsert-batch`
   - `POST /carrier-safety-basic-percentiles/upsert-batch`
   - `POST /vehicle-inspection-units/upsert-batch`
   - `POST /vehicle-inspection-special-studies/upsert-batch`
   - `POST /vehicle-inspection-citations/upsert-batch`
   - `POST /motor-carrier-census-records/upsert-batch`
   - `POST /out-of-service-orders/upsert-batch`
   - `POST /process-agent-filings/upsert-batch`
   - `POST /insurance-filing-rejections/upsert-batch`
   - `POST /carrier-inspections/upsert-batch`

   Each endpoint follows the exact same pattern as `internal.py`:
   ```
   result = upsert_xxx(
       source_context=_build_fmcsa_source_context(payload),
       rows=[row.model_dump() for row in payload.records],
   )
   return DataEnvelope(data=result)
   ```

5. **1 ingest-artifact endpoint** — `POST /fmcsa/ingest-artifact`, same handler logic as in `internal.py` (lazy import of `ingest_artifact` + `ChecksumMismatchError`, error mapping to 422/500).

**Imports:** Import per-table upsert functions from `app/services/*` and `DataEnvelope` from `app/routers/_responses`. Import `get_settings` from `app/config`. Do NOT import anything from `app/routers/internal.py`.

**Router prefix:** The router should be created with no prefix — the prefix is set when mounted in the app entrypoint.

Commit standalone.

---

## Deliverable 2: FMCSA Ingest FastAPI Entrypoint

Create `app/fmcsa_ingest_main.py`.

This is a minimal FastAPI application — the entrypoint for the ingest service. It should be as lean as possible.

**What to include:**

```
from fastapi import FastAPI
from app.middleware.gzip_request import GzipRequestMiddleware
from app.routers import fmcsa_ingest

app = FastAPI(
    title="data-engine-x-fmcsa-ingest",
    description="FMCSA bulk write ingestion service",
    version="0.1.0",
)

app.add_middleware(GzipRequestMiddleware)
```

**Health check:** Add a `GET /health` endpoint that returns `{"status": "ok", "service": "fmcsa-ingest"}`. This is needed for Railway health checks.

**Router mount:** Mount the FMCSA ingest router with prefix `/api/internal`:
```
app.include_router(fmcsa_ingest.router, prefix="/api/internal", tags=["fmcsa-ingest"])
```

This produces the full paths Trigger.dev expects (e.g., `/api/internal/motor-carrier-census-records/upsert-batch`).

**What NOT to include:**
- No CORS middleware (internal service, not called by browsers)
- No tenant auth routers
- No entity query routers
- No execute router
- No super-admin routers
- No orchestration endpoints
- No `HTTPException` handler (the default FastAPI handler is fine for an internal service)

Commit standalone.

---

## Deliverable 3: Dockerfile for Ingest Service

Create `Dockerfile.fmcsa-ingest`.

This is nearly identical to the existing `Dockerfile` with only the CMD changed. The full file:

```dockerfile
FROM python:3.12-slim

# Install Doppler CLI
RUN apt-get update && apt-get install -y apt-transport-https ca-certificates curl gnupg && \
    curl -sLf --retry 3 --tlsv1.2 --proto "=https" 'https://packages.doppler.com/public/cli/gpg.DE2A7741A397C129.key' | gpg --dearmor -o /usr/share/keyrings/doppler-archive-keyring.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/doppler-archive-keyring.gpg] https://packages.doppler.com/public/cli/deb/debian any-version main" > /etc/apt/sources.list.d/doppler-cli.list && \
    apt-get update && apt-get install -y doppler && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["doppler", "run", "--", "uvicorn", "app.fmcsa_ingest_main:app", "--host", "0.0.0.0", "--port", "8080"]
```

The only difference from the main `Dockerfile` is the final CMD line — `app.fmcsa_ingest_main:app` instead of `app.main:app`.

**Note:** Yes, this duplicates the Dockerfile almost entirely. That is intentional. A shared Dockerfile with build args or multi-stage targets adds complexity for no meaningful benefit in this case. Railway selects which Dockerfile to use per service — two simple Dockerfiles is the cleanest approach.

Commit standalone.

---

## Deliverable 4: Trigger.dev URL Routing

Modify `trigger/src/workflows/fmcsa-daily-diff.ts`.

Update the `createClient` function (currently at line 489) to check for `FMCSA_INGEST_API_URL` before falling back to the default API URL. This is the only change needed — all 31 FMCSA task files call `runFmcsaDailyDiffWorkflow` which calls `createClient`, so one change routes all feeds.

**Current code (line 489):**
```typescript
function createClient(
  payload: FmcsaDailyDiffWorkflowPayload,
  dependencies: FmcsaDailyDiffWorkflowDependencies,
): InternalApiClient {
  return (
    dependencies.client ??
    createInternalApiClient({
      authContext: {
        orgId: "system",
      },
      apiUrl: payload.apiUrl,
      internalApiKey: payload.internalApiKey,
    })
  );
}
```

**Updated code:** Add `FMCSA_INGEST_API_URL` as the highest-priority URL source, before `payload.apiUrl`:

```typescript
function createClient(
  payload: FmcsaDailyDiffWorkflowPayload,
  dependencies: FmcsaDailyDiffWorkflowDependencies,
): InternalApiClient {
  return (
    dependencies.client ??
    createInternalApiClient({
      authContext: {
        orgId: "system",
      },
      apiUrl: process.env.FMCSA_INGEST_API_URL ?? payload.apiUrl,
      internalApiKey: payload.internalApiKey,
    })
  );
}
```

**Why this works:**
- When `FMCSA_INGEST_API_URL` is set in the Trigger.dev environment, all FMCSA chunk POSTs and artifact ingests route to the dedicated ingest service.
- When `FMCSA_INGEST_API_URL` is not set (local dev, tests), behavior is unchanged — falls back to `payload.apiUrl` which resolves to `DATA_ENGINE_API_URL` via `resolveInternalApiConfig`.
- No task files need to change. No `internal-api.ts` changes needed.

Commit standalone.

---

## Deliverable 5: Railway Configuration Documentation

Create `docs/RAILWAY_FMCSA_INGEST_SERVICE_SETUP.md`.

Document the Railway configuration steps. The executor does not perform these steps — just documents them clearly for the operator.

**Content to include:**

### Service Creation
1. In the Railway project that hosts `data-engine-x-api`, create a new service
2. Name: `fmcsa-ingest` (or similar)
3. Connect it to the same GitHub repo (`data-engine-x-api`)
4. Set the Dockerfile path to `Dockerfile.fmcsa-ingest`

### Environment Variables
The ingest service needs a `DOPPLER_TOKEN` — same pattern as the main API. Doppler injects all secrets at runtime. The service only uses:
- `DATABASE_URL` (Postgres connection string — same database as main API)
- `INTERNAL_API_KEY` (bearer token for auth — same value as main API)
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` (used by `fmcsa_artifact_ingest.py` to download artifacts from Supabase storage)

These all come from the same Doppler project/config — set `DOPPLER_TOKEN` and everything else is injected.

### Watch Paths (Critical)
Configure Railway watch paths so the ingest service only redeploys when FMCSA ingestion code changes — not on every push to `main`:

**Include paths:**
- `app/fmcsa_ingest_main.py`
- `app/routers/fmcsa_ingest.py`
- `app/services/fmcsa_daily_diff_common.py`
- `app/services/fmcsa_artifact_ingest.py`
- `app/services/carrier_registrations.py`
- `app/services/carrier_inspections.py`
- `app/services/carrier_inspection_violations.py`
- `app/services/carrier_safety_basic_measures.py`
- `app/services/carrier_safety_basic_percentiles.py`
- `app/services/commercial_vehicle_crashes.py`
- `app/services/insurance_policies.py`
- `app/services/insurance_policy_filings.py`
- `app/services/insurance_policy_history_events.py`
- `app/services/insurance_filing_rejections.py`
- `app/services/operating_authority_histories.py`
- `app/services/operating_authority_revocations.py`
- `app/services/out_of_service_orders.py`
- `app/services/process_agent_filings.py`
- `app/services/vehicle_inspection_units.py`
- `app/services/vehicle_inspection_citations.py`
- `app/services/vehicle_inspection_special_studies.py`
- `app/services/motor_carrier_census_records.py`
- `app/middleware/gzip_request.py`
- `app/config.py`
- `app/routers/_responses.py`
- `Dockerfile.fmcsa-ingest`
- `requirements.txt`

**Note:** Railway watch paths use glob patterns. Document the most concise glob patterns that cover the above files. Suggest: `app/fmcsa_ingest_main.py`, `app/routers/fmcsa_ingest.py`, `app/services/fmcsa_*.py`, `app/services/carrier_*.py`, `app/services/commercial_*.py`, `app/services/insurance_*.py`, `app/services/operating_*.py`, `app/services/out_of_service_*.py`, `app/services/process_agent_*.py`, `app/services/vehicle_*.py`, `app/services/motor_carrier_*.py`, `app/middleware/*`, `app/config.py`, `app/routers/_responses.py`, `Dockerfile.fmcsa-ingest`, `requirements.txt`.

### Trigger.dev Environment Variable
After the Railway service is live and has a public URL:
1. In the Trigger.dev dashboard, add `FMCSA_INGEST_API_URL` set to the Railway ingest service URL (e.g., `https://fmcsa-ingest-production-xxxx.up.railway.app`)
2. Redeploy Trigger.dev: `cd trigger && npx trigger.dev@4.4.3 deploy`

### Deploy Order
For the initial cutover:
1. Push the code changes to `main` (Railway auto-deploys both services)
2. Wait for both Railway services to be live
3. Set `FMCSA_INGEST_API_URL` in Trigger.dev env
4. Deploy Trigger.dev

After cutover, the deploy protocol changes:
- **Main API changes:** Push to `main` → Railway auto-deploys main API only (watch paths prevent ingest service redeploy)
- **FMCSA ingestion code changes:** Push to `main` → Railway auto-deploys ingest service only (watch paths trigger)
- **Shared code changes** (e.g., `requirements.txt`, `app/config.py`): Push to `main` → both services redeploy. This is expected and acceptable — shared code changes are rare.

### Rollback
If the ingest service has issues:
1. Remove `FMCSA_INGEST_API_URL` from Trigger.dev env
2. Redeploy Trigger.dev
3. FMCSA tasks immediately fall back to posting to the main API (the old endpoints are still there)

Commit standalone.

---

## Deliverable 6: Tests

Create `tests/test_fmcsa_ingest_service.py`.

All tests mock database calls. Use `pytest`. Do not hit real databases.

**1. Router tests:**
- Each of the 16 upsert-batch endpoints accepts `InternalUpsertFmcsaDailyDiffBatchRequest` and returns `DataEnvelope`
- The ingest-artifact endpoint accepts `InternalFmcsaArtifactIngestRequest` and returns `DataEnvelope`
- All endpoints require internal API key auth (401 without token, 401 with wrong token)
- The `_build_fmcsa_source_context` helper correctly maps all payload fields

**2. App entrypoint tests:**
- `GET /health` returns `{"status": "ok", "service": "fmcsa-ingest"}`
- The app has `GzipRequestMiddleware` registered
- The router is mounted at `/api/internal` prefix (verify a known endpoint path resolves)

**3. Endpoint path compatibility tests:**
- Verify that every `internalUpsertPath` value used in the Trigger.dev feed configs maps to a registered endpoint in the ingest router. The following paths must all be registered:
  - `/api/internal/operating-authority-histories/upsert-batch`
  - `/api/internal/operating-authority-revocations/upsert-batch`
  - `/api/internal/insurance-policies/upsert-batch`
  - `/api/internal/insurance-policy-filings/upsert-batch`
  - `/api/internal/insurance-policy-history-events/upsert-batch`
  - `/api/internal/carrier-registrations/upsert-batch`
  - `/api/internal/carrier-safety-basic-measures/upsert-batch`
  - `/api/internal/commercial-vehicle-crashes/upsert-batch`
  - `/api/internal/carrier-safety-basic-percentiles/upsert-batch`
  - `/api/internal/vehicle-inspection-units/upsert-batch`
  - `/api/internal/vehicle-inspection-special-studies/upsert-batch`
  - `/api/internal/vehicle-inspection-citations/upsert-batch`
  - `/api/internal/motor-carrier-census-records/upsert-batch`
  - `/api/internal/out-of-service-orders/upsert-batch`
  - `/api/internal/process-agent-filings/upsert-batch`
  - `/api/internal/insurance-filing-rejections/upsert-batch`
  - `/api/internal/carrier-inspections/upsert-batch`
  - `/api/internal/fmcsa/ingest-artifact`

Commit standalone.

---

## What is NOT in scope

- **No removal of FMCSA endpoints from `app/routers/internal.py`.** They stay as dead code until a separate cleanup directive.
- **No changes to `app/main.py`.** The main API is unchanged.
- **No changes to the persistence layer** (`fmcsa_daily_diff_common.py`, per-table upsert services, `fmcsa_artifact_ingest.py`).
- **No changes to the database schema.** No migrations.
- **No Railway configuration changes.** Just document them.
- **No Trigger.dev deploy.** Just update the code.
- **No changes to any FMCSA task files** (`trigger/src/tasks/fmcsa-*.ts`). The URL routing is handled in the shared workflow.
- **No changes to `trigger/src/workflows/internal-api.ts`.** The `InternalApiClient` and `resolveInternalApiConfig` are unchanged.
- **Do not push.**

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Ingest router: total endpoint count, import strategy (confirm no imports from `internal.py`), auth dependency approach
(b) App entrypoint: middleware list, router mount prefix, health check response shape
(c) Dockerfile: CMD line, confirm it mirrors the main Dockerfile except for entrypoint
(d) Trigger.dev change: exact line changed, env var name, fallback behavior when env var is unset
(e) Railway docs: watch path glob patterns, deploy order, rollback procedure
(f) Tests: total test count, all passing, confirm all 18 endpoint paths verified
(g) Anything to flag — especially: any import that pulls in unexpected dependencies, any concern about connection pool sizing for the separate process, any Trigger.dev test that needs updating
