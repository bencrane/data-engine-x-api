# Railway: FMCSA Ingest Service Setup

Operator instructions for deploying the standalone FMCSA bulk write ingestion service alongside the main data-engine-x API.

---

## Service Creation

1. In the Railway project that hosts `data-engine-x-api`, create a new service.
2. Name: `fmcsa-ingest`
3. Connect it to the same GitHub repo (`data-engine-x-api`).
4. Set the Dockerfile path to `Dockerfile.fmcsa-ingest`.

---

## Environment Variables

The ingest service needs a single Railway env var: `DOPPLER_TOKEN`. Doppler injects all secrets at runtime — same pattern as the main API.

The service uses these secrets (all provided by Doppler):
- `DATABASE_URL` — Postgres connection string (same database as main API)
- `INTERNAL_API_KEY` — bearer token for auth (same value as main API)
- `SUPABASE_URL` and `SUPABASE_SERVICE_KEY` — used by `fmcsa_artifact_ingest.py` to download artifacts from Supabase storage

---

## Watch Paths (Critical)

Configure Railway watch paths so the ingest service only redeploys when FMCSA ingestion code changes — not on every push to `main`.

**Recommended glob patterns:**

```
app/fmcsa_ingest_main.py
app/routers/fmcsa_ingest.py
app/services/fmcsa_*.py
app/services/carrier_*.py
app/services/commercial_*.py
app/services/insurance_*.py
app/services/operating_*.py
app/services/out_of_service_*.py
app/services/process_agent_*.py
app/services/vehicle_*.py
app/services/motor_carrier_*.py
app/middleware/*
app/config.py
app/routers/_responses.py
Dockerfile.fmcsa-ingest
requirements.txt
```

These cover all files the ingest service imports. Changes to main API routers, entity services, or Trigger.dev code will not trigger a redeploy.

---

## Trigger.dev Environment Variable

After the Railway ingest service is live and has a public URL:

1. In the Trigger.dev dashboard, add env var:
   - **Name:** `FMCSA_INGEST_API_URL`
   - **Value:** the Railway ingest service URL (e.g., `https://fmcsa-ingest-production-xxxx.up.railway.app`)
2. Redeploy Trigger.dev: `cd trigger && npx trigger.dev@4.4.3 deploy`

---

## Deploy Order — Initial Cutover

1. Push the code changes to `main` (Railway auto-deploys both services).
2. Wait for both Railway services to be live and healthy (`GET /health` returns 200).
3. Set `FMCSA_INGEST_API_URL` in Trigger.dev env.
4. Deploy Trigger.dev: `cd trigger && npx trigger.dev@4.4.3 deploy`

---

## Deploy Order — Steady State

After cutover, the deploy protocol changes:

| Change type | What happens |
|---|---|
| **Main API changes** (routers, entity services, etc.) | Push to `main` → Railway auto-deploys main API only. Watch paths prevent ingest service redeploy. |
| **FMCSA ingestion code changes** (upsert services, ingest router, etc.) | Push to `main` → Railway auto-deploys ingest service only. Watch paths trigger. |
| **Shared code changes** (`requirements.txt`, `app/config.py`) | Push to `main` → both services redeploy. Expected and acceptable — shared code changes are rare. |

---

## Rollback

If the ingest service has issues:

1. Remove `FMCSA_INGEST_API_URL` from Trigger.dev env.
2. Redeploy Trigger.dev: `cd trigger && npx trigger.dev@4.4.3 deploy`
3. FMCSA tasks immediately fall back to posting to the main API (the old endpoints are still there).

No Railway changes needed — the ingest service can stay deployed but idle.
