# Directive: Investigate Production 502 on Railway

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The production FastAPI app at `https://api.dataengine.run` is returning `502` from Railway. Trigger.dev tasks are registered and triggerable, but they are failing because the FastAPI app is down. This directive is investigation first: determine whether the latest Railway deploy is healthy, inspect runtime logs, reproduce the boot path locally against production secrets, and identify the root cause. If the cause is a narrow, clearly fixable issue such as an import error, missing dependency, bad migration syntax, or an obvious missing production env var, fix it. If the cause is structural or high-risk, stop after diagnosis and report rather than making broad changes.

## Production / Runtime Commands To Use

Use these exact operational checks unless you discover a better repo-local equivalent during the investigation:

- Railway deploy status:
  - `railway status`
  - or Railway dashboard if CLI output is insufficient
- If Railway CLI auth is expired:
  - `railway login`
- Railway runtime logs:
  - `railway logs --tail 100`
- Local boot against production secrets:
  - `doppler run -p data-engine-x-api -c prd -- uvicorn app.main:app --host 0.0.0.0 --port 8080`

You may use additional non-destructive diagnostic commands if they stay within this scope.

## Existing code to read

- `CLAUDE.md` — project conventions, auth/runtime boundary, deploy protocol
- `docs/DOPPLER_RAILWAY_SETUP.md` — Railway + Doppler runtime model, Docker/Doppler injection pattern, troubleshooting notes
- `docs/troubleshooting-fixes/2026-02-25_icp_auto_persist_not_writing.md` — deploy-order incident context
- `app/main.py` — FastAPI entrypoint and import surface
- `app/config.py` — required env vars and validation behavior
- `app/database.py` — startup-time DB client construction and schema routing
- `requirements.txt` — production Python dependency manifest
- `Dockerfile` — Railway container startup command and dependency installation path
- `railway.toml` — Railway build/deploy configuration
- `supabase/migrations/021_schema_split_ops_entities.sql`
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- `supabase/migrations/023_fmcsa_snapshot_history_tables.sql`
- `supabase/migrations/024_fmcsa_sms_tables.sql`
- `supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql`

If the stack trace points into a more specific module, read that module too before changing it.

---

### Deliverable 1: Railway Deployment and Runtime Investigation

Investigate the live production failure on Railway.

Required actions:

- Check whether the latest Railway deploy is successful, failed, or crash-looping.
- Capture the most relevant runtime evidence from the last `100` log lines.
- Determine whether the failure is happening:
  - before the app boots
  - during import/startup
  - during config validation
  - during migration/runtime DB initialization
  - or after the app starts but before it can serve requests

Focus especially on these likely classes of failure:

- bad migration or migration-side startup issue, especially around `025`
- missing dependency or package import failure
- missing or invalid production env var
- Docker/Railway command or runtime config issue

This deliverable is investigation only. No commit unless a later deliverable requires code changes.

### Deliverable 2: Local Reproduction Against Production Secrets

Run the FastAPI app locally against the production Doppler config using:

- `doppler run -p data-engine-x-api -c prd -- uvicorn app.main:app --host 0.0.0.0 --port 8080`

Required outcomes:

- Confirm whether the app boots locally.
- If it fails locally, capture the exact exception and map it to the responsible file/module.
- If it boots locally but Railway is failing, isolate what is likely Railway-specific:
  - env var injection/runtime config difference
  - Docker/build artifact difference
  - deploy artifact mismatch
  - platform/runtime issue rather than Python app logic

This deliverable is investigation only. No commit unless a later deliverable requires code changes.

### Deliverable 3: Simple Fix Only If Clearly Warranted

Only if Deliverables 1 and 2 identify a narrow, clearly fixable cause, fix it.

Allowed fix classes:

- missing import or obvious import cycle breakage
- missing Python dependency in `requirements.txt`
- obvious config/bootstrap error in startup code
- obvious migration syntax or migration-file issue that is directly causing the app to fail to boot
- a single missing production env var or similarly narrow runtime config issue, if you can correct it safely without widening scope

Constraints:

- Keep the fix minimal.
- Do not refactor unrelated startup code.
- Do not broaden scope into app improvements or cleanup.
- If the issue is structural, ambiguous, or risky, do not change code just to “try something.”
- If the root cause is production configuration rather than repo code, report the exact config issue. Only change it if it is a straightforward, clearly scoped correction and you can state exactly what was changed.

If code changes are required, commit standalone.

### Deliverable 4: Verification After Diagnosis or Fix

After investigation, and after any simple fix if one was made:

- Re-run the local boot command.
- Re-check the relevant error condition you identified.
- Confirm whether the root cause is resolved locally.
- If the issue was production-only and you did not change code, explain exactly why no code change was appropriate.

Do not deploy. Verification in this directive stops at diagnosis plus local confirmation of any fix.

Commit standalone only if this deliverable requires follow-up code/test changes beyond Deliverable 3.

---

**What is NOT in scope:** No deploy commands. No Trigger.dev code changes. No broad refactors. No secret rotation unless you discover an exposed secret during the investigation. No schema redesign. No unrelated migration work. No speculative fixes without a concrete root cause. No rewriting the Railway/Doppler setup model.

**Commit convention:** If no code changes are needed, do not create a commit. If code changes are needed, each code-changing deliverable is one commit. Do not push.

**When done:** Report back with: (a) the Railway deploy status, (b) the relevant runtime log output, (c) whether the app boots locally against `doppler run -p data-engine-x-api -c prd`, (d) the root cause, (e) whether you fixed it or why you did not, (f) every file changed if code changes were made, (g) any production config/env var issue identified, and (h) what needs to happen next if the issue was not safely fixable within this directive.
