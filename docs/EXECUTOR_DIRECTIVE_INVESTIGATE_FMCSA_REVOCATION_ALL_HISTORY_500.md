# Directive: Investigate `fmcsa-revocation-all-history-daily` 500 on Internal Upsert

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Production evidence already shows `fmcsa-revocation-all-history-daily` failing with `InternalApiError: Internal API request failed (500): /api/internal/operating-authority-revocations/upsert-batch`. This directive is to identify the exact error behind that 500, using Railway logs first if available and local reproduction second if not. If the root cause is clear and local verification is possible, fix it. Do not deploy anything until you report back with the exact error and the proposed or completed fix.

**Failure surface in scope:**

- Trigger task: `fmcsa-revocation-all-history-daily`
- Shared feed config: `FMCSA_REVOCATION_ALL_HISTORY_CSV_FEED`
- Internal endpoint: `/api/internal/operating-authority-revocations/upsert-batch`
- Service path behind the endpoint: `app/services/operating_authority_revocations.py`

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_TIMEOUT_FAILURE_DIAGNOSIS_2026-03-11.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_DIRECTIVE_FMCSA_NEXT_BATCH_SNAPSHOTS_AND_HISTORY_FEEDS.md`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-revocation-all-history-daily.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/internal-api.ts`
- `/Users/benjamincrane/data-engine-x-api/app/routers/internal.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/operating_authority_revocations.py`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/023_fmcsa_snapshot_history_tables.sql`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/overview-data-dictionary.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/__tests__/fmcsa-daily-diff.test.ts`
- `/Users/benjamincrane/data-engine-x-api/tests/test_fmcsa_daily_diff_persistence.py`

---

### Deliverable 1: Identify the Exact 500 Error

Investigate the exact cause of the 500 returned by `/api/internal/operating-authority-revocations/upsert-batch` for `fmcsa-revocation-all-history-daily`.

Investigation order:

1. Check Railway logs for the failing request and capture the exact backend exception.
2. If Railway logs are not accessible or not sufficient, reproduce locally by calling the internal endpoint with a representative sample batch shaped like the revocation all-history feed payload.

Requirements:

- do not stop at “500 from internal API”; capture the actual exception text and where it originates
- if reproducing locally, use a realistic sample batch from the revocation all-history feed contract, not the daily revocation contract
- confirm whether the failure is:
  - schema mismatch
  - bad field/header mapping
  - date parsing issue
  - nullability issue
  - unique/constraint violation
  - another service/database error
- compare the revocation all-history feed headers and source fields against what `app/services/operating_authority_revocations.py` currently reads
- explicitly check whether the service is still expecting daily-feed field names while the all-history CSV feed provides different header names

Important hypothesis to verify, not assume:

- the all-history feed config in `trigger/src/workflows/fmcsa-daily-diff.ts` uses header names such as `DOT_NUMBER`, `TYPE_LICENSE`, and `ORDER1_SERVE_DATE`
- the current service in `app/services/operating_authority_revocations.py` reads daily-feed field names such as `USDOT Number`, `Operating Authority Registration Type`, and `Serve Date`

Your job is to prove whether that mismatch is the actual cause of the 500 or whether the error is elsewhere.

This deliverable is diagnosis first. No commit is required unless you proceed to Deliverable 2.

### Deliverable 2: Fix the Root Cause If Confirmed

If Deliverable 1 produces a clear, reproducible root cause and the fix is within this scope, implement it.

Allowed fix surfaces:

- `app/services/operating_authority_revocations.py`
- `app/routers/internal.py` only if request handling or payload shaping is part of the issue
- `trigger/src/workflows/fmcsa-daily-diff.ts` only if the revocation all-history feed payload itself is malformed before it reaches FastAPI
- tests that cover the affected path
- a migration only if the exact error proves the production schema is wrong for the intended canonical contract

Fix requirements:

- preserve the canonical table and existing ingestion semantics unless the exact failure proves they are wrong
- do not guess at a fix without reproducing or proving the error
- if the issue is a header/field-name mismatch between daily and all-history revocation variants, fix it in the narrowest place that preserves both variants correctly
- if the issue is a schema or constraint mismatch, align the code and schema carefully and explain why the mismatch existed
- do not broaden this into a general FMCSA refactor
- add or update tests that would have caught this exact failure mode

Commit standalone.

### Deliverable 3: Report Back Before Any Deploy

Do not deploy Railway. Do not deploy Trigger.dev. Do not push unless I explicitly ask after reviewing your report.

Report back with the exact findings first, including whether Deliverable 2 was completed and validated locally.

Commit standalone if Deliverable 2 changed code.

---

**What is NOT in scope:** No deployment. No manual triggering of FMCSA feeds after a fix. No unrelated FMCSA timeout work. No broad schema redesign of FMCSA tables. No changes to `trigger/src/tasks/run-pipeline.ts`. No speculative fixes without exact error evidence. No production backfill.

**Commit convention:** If you make a code fix, keep it to one commit. Do not push. Do not deploy.

**When done:** Report back with: (a) whether Railway logs were accessible, (b) the exact error text and stack location, (c) whether you reproduced it locally and how, (d) the confirmed root cause, (e) whether the likely issue was header/field mismatch, schema mismatch, or something else, (f) every file changed if you fixed it, (g) the tests added or updated, and (h) anything to flag before a later deploy decision.
