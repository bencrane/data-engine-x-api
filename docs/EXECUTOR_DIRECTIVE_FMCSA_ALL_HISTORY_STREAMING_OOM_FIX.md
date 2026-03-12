# Directive: FMCSA All-History Streaming OOM Fix

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Operator override to standard executor convention:** The project-wide default is that executors do not push and do not deploy. For this specific directive only, the operator explicitly wants the finished fix pushed and Trigger.dev deployed after implementation and verification are complete. Treat that rollout as in scope only for this FMCSA Trigger-side fix. Do not trigger any FMCSA feeds after deploy.

**Background:** Four plain-text FMCSA all-history feeds are crashing with OOM because the shared workflow currently uses `response.text()` for the non-streaming path, which materializes the full response body in memory before CSV parsing. The CSV-export feeds already use a streaming parser path in `trigger/src/workflows/fmcsa-daily-diff.ts`; this fix should bring the affected plain-text all-history feeds onto a streaming download/parse/persist path as well so large files are never buffered as one giant string.

**Affected feeds and task IDs:**

- `AuthHist - All With History` — `fmcsa-authhist-all-history`
- `BOC3 - All With History` — `fmcsa-boc3-all-history`
- `InsHist - All With History` — `fmcsa-inshist-all-history`
- `ActPendInsur - All With History` — `fmcsa-actpendinsur-all-history`

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_DIRECTIVE_FMCSA_NEXT_BATCH_SNAPSHOTS_AND_HISTORY_FEEDS.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_DIRECTIVE_FMCSA_REMAINING_CSV_EXPORT_FEEDS.md`
- `/Users/benjamincrane/data-engine-x-api/docs/EXECUTOR_DIRECTIVE_FMCSA_PRODUCTION_TIMEOUTS_AND_MAX_DURATION.md`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/internal-api.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/persistence.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-authhist-all-history.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-boc3-all-history.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-inshist-all-history.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-actpendinsur-all-history.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/__tests__/fmcsa-daily-diff.test.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/__tests__/fmcsa-daily-diff-tasks.test.ts`

---

### Deliverable 1: Move the Four Plain-Text All-History Feeds onto a Streaming Path

Fix `trigger/src/workflows/fmcsa-daily-diff.ts` so the four affected plain-text all-history feeds no longer use the `response.text()` code path and never materialize the full response body as a single in-memory string before parsing.

Required scope:

- keep using the shared FMCSA workflow; do not fork a second FMCSA ingestion framework
- preserve the existing confirmed-write semantics through the internal API client and persistence helpers
- preserve the current row-shape validation semantics for these feeds
- preserve the current feed metadata behavior such as `feed_date`, `observed_at`, `task_id`, and source file variant
- make the streaming approach work for plain-text no-header CSV-formatted feeds, not just the existing header-row CSV export feeds
- keep the change narrowly targeted to the workflow and any feed config needed to route these four feeds to the correct streaming behavior

The fix must ensure:

- the affected feeds stream download content from `response.body`
- parsing happens incrementally rather than after building one giant string
- large files are flushed to persistence in batches during parsing
- no silent degradation back to the `response.text()` path remains for these four feeds

Implementation constraints:

- do not change the FastAPI persistence contract unless it is strictly required for the streaming fix; this should be a Trigger-side workflow fix
- do not redesign FMCSA ingestion semantics
- do not introduce a solution that merely raises memory limits while retaining whole-body buffering
- do not hide parser or persistence failures behind warnings
- if the correct generalization is to make plain-text feeds eligible for the same streaming machinery already used by CSV feeds, do that rather than cloning a second parser/persist loop
- if content-type handling for `text/plain` currently blocks the streaming path, fix that narrowly and explicitly

Commit standalone.

### Deliverable 2: Regression Coverage for the OOM Fix

Update the Trigger workflow and task tests so this regression is locked down.

At minimum, cover:

- the four affected all-history feeds taking the streaming path rather than the whole-body text path
- correct handling of no-header CSV-formatted plain-text rows in the streaming parser
- row-width validation still firing for malformed rows
- batched persistence still occurring during streaming for the affected feeds
- no regression to the existing streaming behavior for header-row CSV feeds

Mock all network and persistence behavior. Do not hit live FMCSA endpoints in tests.

Commit standalone.

### Deliverable 3: Commit, Push, and Deploy Trigger.dev Only

After Deliverables 1 and 2 are complete and verified:

- create the required commits
- push the branch/commits as requested by the operator
- deploy Trigger.dev for this change set

Deployment constraints:

- this rollout is for Trigger-side code only
- if you discover that the fix actually requires FastAPI/Railway changes, stop and report rather than partially deploying
- do not trigger any of the FMCSA feeds after deploy
- do not run ad hoc ingestion jobs to “test live” by executing the four feeds
- if there is any uncertainty about whether the pushed changes are limited to Trigger code and Trigger tests, stop and report before deploy

Commit standalone.

---

**What is NOT in scope:** No FastAPI schema or persistence redesign. No new FMCSA feeds. No changes to `trigger/src/tasks/run-pipeline.ts`. No manual triggering of FMCSA runs. No production backfill. No broad FMCSA timeout tuning unrelated to the OOM root cause. No “fix” that depends on larger machines while still buffering the whole file in memory.

**Commit convention:** Deliverables 1 and 2 should be their own commits. Unlike the normal executor convention, the operator explicitly requires push plus Trigger.dev deployment after the implementation commits are complete. Do not push or deploy anything except this scoped fix.

**When done:** Report back with: (a) the exact root cause in `trigger/src/workflows/fmcsa-daily-diff.ts`, (b) how the four affected feeds were routed onto the streaming path, (c) every file changed, (d) the tests added or updated and what they prove, (e) the commit SHAs created, (f) the branch and push target used, (g) the Trigger.dev deploy command executed and whether it succeeded, and (h) anything to flag — especially any remaining non-streaming large-feed paths in the shared workflow that still risk OOM.
