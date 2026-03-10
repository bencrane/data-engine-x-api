# Directive: Investigation — DB-Backed Child Fan-Out for Dedicated Workflows

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The person search/enrichment workflow (Priority 3) uses in-task fan-out — it loops through discovered people inside a single Trigger.dev task with bounded concurrency. This works, but it means no per-entity pipeline runs in the `ops` tables, no granular retry, and no resumability if the task crashes mid-batch. The existing `run-pipeline.ts` has a DB-backed fan-out path that creates child pipeline runs and triggers child Trigger.dev tasks. We need to understand whether that fan-out path can be made to trigger dedicated workflow files instead of always invoking `run-pipeline`, and what the cost/risk of that change would be.

**This is a read-only investigation. No code changes. No commits.**

---

## Existing Code to Read

- `trigger/src/tasks/run-pipeline.ts` — the fan-out code path. Trace from the fan-out step detection through child run creation and child task triggering. Pay particular attention to where the target Trigger.dev task ID is specified.
- `app/routers/internal.py` — the `/api/internal/pipeline-runs/fan-out` endpoint. Trace what it creates in the database and what it returns.
- `app/services/` — any service functions called by the fan-out endpoint
- `supabase/migrations/010_fan_out.sql` — the schema that supports fan-out (parent_pipeline_run_id on pipeline_runs)
- `docs/NESTED_FAN_OUT_TRACE.md` — existing documentation on how recursive fan-out works
- `trigger/src/tasks/` — the dedicated workflow files from Priority 2 and 3, to understand what a "target workflow" would look like as a fan-out child

---

## Questions to Answer

### 1. How does the existing DB-backed fan-out work?

Trace the exact code path end-to-end:
- How does `run-pipeline.ts` detect a fan-out step?
- What data does it send to `/api/internal/pipeline-runs/fan-out`?
- What does the FastAPI endpoint create in the database (child pipeline_runs, child step_results)?
- How does the child Trigger.dev task get triggered — does `run-pipeline.ts` trigger it directly, or does FastAPI trigger it?
- What does the child task receive as input?

### 2. What is hardwired to `run-pipeline`?

Where exactly in the code is the Trigger.dev task ID `run-pipeline` specified when triggering child runs? Is it:
- A string literal in `run-pipeline.ts`?
- A reference to the task object?
- Passed through from the FastAPI fan-out response?
- Stored in the database (blueprint, pipeline_run)?

Identify every location where the system decides "the child run should execute as a `run-pipeline` task."

### 3. What would need to change?

If we wanted the fan-out path to trigger a dedicated workflow file instead of `run-pipeline`, what would need to change? Assess:
- Which files would need modification
- How many code locations are involved
- Whether the change is isolated (one routing decision) or spread across multiple layers
- Whether it's a simple task-ID swap or requires structural changes to how child runs are configured

### 4. Are there other dependencies or assumptions?

Does the fan-out path assume anything about the child task's behavior that a dedicated workflow might not satisfy? For example:
- Does it assume the child task reads a blueprint snapshot?
- Does it assume the child task starts from a specific step position?
- Does it assume a specific input shape?
- Does the parent task wait for child tasks and aggregate results, or are they fire-and-forget?
- Are there assumptions about how child tasks report completion back to the parent?

---

## What is NOT in scope

- No code changes
- No commits
- No deploy commands
- No design proposals (report findings; we will decide next steps)

## When done

Report back with:
(a) End-to-end fan-out trace: the exact sequence from fan-out detection to child task execution, with file names and relevant line numbers
(b) Every location where the target task is hardwired to `run-pipeline`, with file paths and line numbers
(c) Assessment of what would need to change: file count, location count, risk level (isolated vs. spread)
(d) Assumptions the fan-out path makes about child task behavior
(e) Your assessment of feasibility and risk — is this a clean routing change or a structural refactor?
(f) Anything unexpected you found in the fan-out path
