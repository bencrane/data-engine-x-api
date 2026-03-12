# Directive: FMCSA Production Timeouts and Max Duration Stabilization

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA ingestion tasks are registered, the FastAPI app is healthy, and the streaming batch-persist path is partially working in production, but several FMCSA feeds are failing for two operational reasons rather than contract/parser issues:

1. `MAX_DURATION_EXCEEDED` on larger feeds because the current Trigger.dev runtime budget is too small for those tasks.
2. mid-run `TimeoutError` from the abort controller during streaming persistence, which strongly suggests that one or more HTTP request timeouts in the FMCSA ingestion workflow or internal API client are too short for large batch writes, or that the download/persist loop is not tuned correctly for the real production runtime.

This directive is to investigate those production failure modes and fix them so all `31` FMCSA feeds can complete successfully in production.

## Known Current Configuration Surfaces

From the current code:

- the shared workflow in `trigger/src/workflows/fmcsa-daily-diff.ts` has feed-level knobs for:
  - `useStreamingParser`
  - `writeBatchSize`
  - `downloadTimeoutMs`
  - `persistenceTimeoutMs`
- the workflow currently defaults to:
  - `300_000ms` download timeout for streaming-parser feeds
  - `120_000ms` persistence timeout for streaming-parser feeds
- the internal API client in `trigger/src/workflows/internal-api.ts` defaults to `30_000ms` when no per-call override is passed
- several larger FMCSA tasks are currently configured with:
  - `machine: "small-2x"`
  - `maxDuration: 1800`
- the largest current tasks already using higher settings include:
  - `fmcsa-company-census-file-daily.ts`
  - `fmcsa-vehicle-inspection-file-daily.ts`
  - both currently use `machine: "medium-2x"` and `maxDuration: 3600`

The executor must verify the real production failures from logs before changing anything, but these are the first places to inspect.

## Existing code to read

- `CLAUDE.md` — project conventions, Trigger/FastAPI boundary, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — no-guessing rule, pragmatic fix scope
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — confirmed-write and failure-surfacing principles
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — production/Trigger context
- `trigger/src/workflows/fmcsa-daily-diff.ts` — shared FMCSA ingestion workflow, timeout knobs, streaming behavior, batch persistence loop
- `trigger/src/workflows/internal-api.ts` — internal API client timeout behavior and abort-controller path
- `trigger/src/workflows/persistence.ts` — confirmed-write wrapper behavior
- `trigger/src/tasks/fmcsa-out-of-service-orders-daily.ts`
- `trigger/src/tasks/fmcsa-special-studies-daily.ts`
- `trigger/src/tasks/fmcsa-company-census-file-daily.ts`
- `trigger/src/tasks/fmcsa-vehicle-inspection-file-daily.ts`
- `trigger/src/tasks/fmcsa-carrier-all-history-daily.ts`
- `trigger/src/tasks/fmcsa-revocation-all-history-daily.ts`
- `trigger/src/tasks/fmcsa-insur-all-history-daily.ts`
- all other `trigger/src/tasks/fmcsa-*.ts` task files to confirm whether the runtime-budget problem is isolated to a subset or more widespread
- `trigger/src/workflows/__tests__/fmcsa-daily-diff.test.ts`
- `trigger/src/tasks/__tests__/fmcsa-daily-diff-tasks.test.ts`
- `app/routers/internal.py` — FMCSA batch upsert endpoints and response envelopes
- the FMCSA persistence service modules called by those internal endpoints if log evidence points to a specific slow endpoint:
  - `app/services/fmcsa_daily_diff_common.py`
  - `app/services/carrier_registrations.py`
  - `app/services/process_agent_filings.py`
  - `app/services/insurance_filing_rejections.py`
  - `app/services/motor_carrier_census_records.py`
  - and any other FMCSA service backing a failing endpoint

---

### Deliverable 1: Production Failure Investigation

Investigate the production FMCSA failures before changing code.

Required actions:

- Inspect production Trigger.dev logs for the specific failing FMCSA runs.
- Identify which feeds are failing with:
  - `MAX_DURATION_EXCEEDED`
  - mid-run `TimeoutError`
- For each failing class, determine where the timeout is occurring:
  - task-level runtime budget exhaustion
  - download timeout
  - internal API persist timeout
  - another abort-controller path in the workflow loop
- Capture enough evidence to map the failure to a specific code/config surface.

Do not guess from symptoms alone. Use the actual production run logs.

This deliverable is investigation only. No commit unless a later deliverable requires code changes.

### Deliverable 2: Increase Task Runtime Budgets for Large FMCSA Feeds

Fix the `MAX_DURATION_EXCEEDED` class of failures.

Required scope:

- audit the current `machine` and `maxDuration` settings across all FMCSA task files
- identify which feeds need higher runtime budgets
- raise those budgets appropriately for the actual workload

The user has already identified the likely large-feed set:

- `Out of Service Orders`
- `Special Studies`
- `Company Census File`
- `Vehicle Inspection File`
- the `All With History` variants

You should verify whether that set is complete based on production evidence and current task configuration.

Constraints:

- keep the changes explicit in the task files
- do not blanket-increase every FMCSA task without evidence
- keep machine-size changes narrowly targeted if they are needed
- update the FMCSA task test expectations to match the new runtime settings

Commit standalone.

### Deliverable 3: Fix Streaming Workflow and Internal Persist Timeouts

Fix the mid-run timeout class of failures in the shared FMCSA workflow.

Investigate and adjust as needed:

- feed-level `downloadTimeoutMs`
- feed-level `persistenceTimeoutMs`
- `writeBatchSize`
- any internal API client timeout path that is still effectively too low for large streaming batches
- any endpoint-specific persist behavior that is making successful batches too slow for the current timeout budget

Requirements:

- keep confirmed-write semantics intact; do not bypass confirmation just to avoid timeouts
- do not convert surfaced failures into silent warnings
- if the correct fix is to increase timeouts for only certain large feeds, do that rather than globally inflating everything without reason
- if batch sizing is part of the fix, tune it based on the production symptom rather than guessing
- if an internal batch upsert endpoint is materially slower than the others because of an avoidable implementation issue, fix that narrowly

Commit standalone.

### Deliverable 4: Verification and Regression Coverage

Add or update tests to lock the timeout/runtime behavior you changed.

At minimum, cover:

- task-level runtime-budget expectations for the affected FMCSA tasks
- workflow behavior when a longer persistence timeout is required
- any batch-size behavior you changed
- any feed-specific timeout override behavior you introduced

Then verify, based on code plus production evidence, that:

- all identified `MAX_DURATION_EXCEEDED` feeds now have appropriate runtime settings
- all identified abort-controller timeout paths now have appropriate timeout configuration
- the FMCSA workflow still surfaces real failures rather than hiding them

Commit standalone.

---

**What is NOT in scope:** No deploy commands. No redesign of FMCSA storage semantics. No new FMCSA feeds. No parser-contract changes unless logs prove the timeout is masking a parser bug. No changes to `run-pipeline.ts`. No broad Trigger.dev refactor beyond the FMCSA timeout/runtime surfaces. No turning confirmed writes into fire-and-forget. No production backfill.

**Commit convention:** Deliverables 2, 3, and 4 are each one commit if changed. Deliverable 1 is investigation only and should not create a commit by itself. Do not push.

**When done:** Report back with: (a) which FMCSA feeds were failing in production and with which timeout class, (b) the relevant Trigger.dev log evidence, (c) the old and new `machine` / `maxDuration` settings for affected task files, (d) the old and new workflow/internal API timeout settings you changed, (e) whether `writeBatchSize` changed and why, (f) every file changed, (g) test coverage added or updated, and (h) anything to flag — especially if any feed is still likely to fail because of endpoint-side performance rather than task/runtime configuration.
