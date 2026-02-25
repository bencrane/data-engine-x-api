# Directive: Auto-Persist ICP Job Titles to Dedicated Table

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a dedicated `icp_job_titles` table that stores raw Parallel.ai ICP research output per company. Currently, ICP results only land there via a backfill script. This directive wires the pipeline runner so that every future `company.derive.icp_job_titles` step that succeeds automatically writes to this table via an internal FastAPI endpoint.

---

## Existing code to read before starting

- `trigger/src/tasks/run-pipeline.ts` — the only file you will modify. Study:
  - The `executeParallelDeepResearch` function — this is the ICP job titles function
  - The step execution branch (around line 1308) — where the result is produced
  - The `internalPost` helper function (around line 222) — how Trigger.dev calls FastAPI internal endpoints
  - The variables `run.submission_id` and `pipeline_run_id` — available in the run scope for provenance
- `app/routers/internal.py` — the `/api/internal/icp-job-titles/upsert` endpoint already exists. You do NOT need to create it.

---

## Deliverable 1: Auto-Persist After ICP Step Succeeds

**File:** `trigger/src/tasks/run-pipeline.ts`

After the step execution branch produces a result, and BEFORE the existing `cumulativeContext = mergeContext(...)` line, add a block that persists ICP results to the dedicated table.

Find the code that looks like this (around lines 1307-1324):

```typescript
      try {
        let result: NonNullable<ExecuteResponseEnvelope["data"]>;
        if (operationId === "company.derive.icp_job_titles") {
          result = await executeParallelDeepResearch(cumulativeContext, stepSnapshot.step_config || {});
        } else if (operationId === "company.derive.intel_briefing") {
          ...
        }

        cumulativeContext = mergeContext(cumulativeContext, result.output);
```

Add this block between the result assignment and the `mergeContext` call:

```typescript
        if (operationId === "company.derive.icp_job_titles" && result.status === "found" && result.output) {
          try {
            await internalPost(internalConfig, "/api/internal/icp-job-titles/upsert", {
              company_domain: result.output.domain || result.output.company_domain,
              company_name: result.output.company_name,
              company_description: result.output.company_description,
              raw_parallel_output: (result.output.parallel_raw_response as Record<string, unknown>)?.output?.content || result.output.parallel_raw_response,
              parallel_run_id: result.output.parallel_run_id,
              processor: result.output.processor,
              source_submission_id: run.submission_id,
              source_pipeline_run_id: pipeline_run_id,
            });
            logger.info("ICP job titles persisted to dedicated table", {
              domain: result.output.domain || result.output.company_domain,
              company_name: result.output.company_name,
              pipeline_run_id,
            });
          } catch (error) {
            logger.warn("Failed to persist ICP job titles to dedicated table", {
              pipeline_run_id,
              error: error instanceof Error ? error.message : String(error),
            });
          }
        }

        cumulativeContext = mergeContext(cumulativeContext, result.output);
```

**Key details:**
- Only fires when `operationId === "company.derive.icp_job_titles"` AND `result.status === "found"` — no writes on failure/skip.
- Wrapped in try/catch — if the upsert fails, it logs a warning but does NOT fail the pipeline step. The step result is already saved; this is a bonus persistence.
- Uses `result.output.domain || result.output.company_domain` for the domain field to handle both possible key names.
- Extracts `parallel_raw_response.output.content` for the `raw_parallel_output` field (same path the backfill script uses).
- Uses `run.submission_id` and `pipeline_run_id` for provenance tracking.

Commit with message: `add auto-persist of ICP job titles to dedicated table after successful pipeline step`

---

## Deliverable 2: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

No changes needed — the table and endpoints are already documented.

### File: `CLAUDE.md`

No changes needed.

This deliverable is skipped if no documentation changes are required.

---

## What is NOT in scope

- No changes to FastAPI (the internal endpoint already exists)
- No changes to the `icp_job_titles` table schema
- No changes to other Parallel operations (company briefing, person briefing)
- No backfill logic
- No deploy commands

## Commit convention

One commit. Do not push. Do not squash.

## When done

Report back with:
(a) Exact line numbers where the new block was inserted
(b) The condition that gates the upsert (operation ID + status check)
(c) The extraction path for `raw_parallel_output` (what keys it reads)
(d) Confirmation that failure does NOT fail the pipeline step (try/catch with warn log)
(e) Anything to flag
