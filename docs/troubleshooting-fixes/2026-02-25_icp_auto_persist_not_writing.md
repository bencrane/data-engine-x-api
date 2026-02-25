# ICP Auto-Persist Not Writing to Dedicated Table

**Date:** 2026-02-25
**Severity:** Data did not land in expected table. Pipeline runs succeeded but `icp_job_titles` table was empty for the new companies.

## What Happened

Ran the "ICP Job Titles Discovery v1" blueprint on 5 new companies (WithCoverage, SecurityPal AI, Radar, Forethought, Lunos AI). All 5 child runs completed successfully in Trigger.dev (version `20260225.3`). Step results had full Parallel.ai output. But the `icp_job_titles` table had no rows for these 5 companies.

## Root Cause

The auto-persist code in `run-pipeline.ts` calls `POST /api/internal/icp-job-titles/upsert` on FastAPI (Railway) after a successful ICP step. This call is wrapped in try/catch — if it fails, it logs a warning but does not fail the pipeline step. This is by design (don't break the pipeline for a persistence side-effect).

The most likely cause: the Railway deploy was still rolling when the Trigger.dev runs fired. The internal endpoint wasn't available yet, so the upsert call failed silently. The step succeeded, the data landed in `step_results`, but the dedicated table write was skipped.

## How It Was Fixed

Manually backfilled the 5 companies by reading from `step_results` and calling `upsert_icp_job_titles` directly:

```bash
doppler run -p data-engine-x-api -c prd -- uv run python -c "<inline script>"
```

All 5 records confirmed in `icp_job_titles` after backfill.

## Prevention

1. **Deploy Trigger.dev AFTER Railway is confirmed live.** Railway auto-deploys on push but takes 1-2 minutes. Trigger.dev deploys separately. If you push + deploy Trigger.dev immediately, the new Trigger.dev code may call FastAPI endpoints that don't exist yet on the old Railway container.

2. **Sequence:** Push → wait for Railway deploy to complete → then deploy Trigger.dev.

3. **The try/catch design is correct** — don't change it. A failed persistence side-effect should never fail the pipeline. But be aware that if you see data in step_results but not in the dedicated table, this timing gap is the first thing to check.

## Related Files

- `trigger/src/tasks/run-pipeline.ts` — auto-persist blocks (around line 1755+)
- `app/routers/internal.py` — `/api/internal/icp-job-titles/upsert` endpoint
- `app/services/icp_job_titles.py` — upsert function
- `scripts/backfill_icp_job_titles.py` — backfill script for bulk recovery
