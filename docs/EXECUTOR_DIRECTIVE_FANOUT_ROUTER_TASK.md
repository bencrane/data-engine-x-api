# Directive: DB-Backed Fan-Out Router for Dedicated Workflows

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The system now has five dedicated workflow files (company enrichment, person search/enrichment, ICP job titles, company intel briefing, person intel briefing) alongside the legacy `run-pipeline.ts`. The existing DB-backed fan-out path — which creates child `pipeline_runs` and triggers child Trigger.dev tasks — is hardwired to invoke `run-pipeline`. Dedicated workflows currently use in-task fan-out (bounded parallel loops within a single task), which has no per-entity lineage, no granular retry, and no resumability on task crash.

An investigation has already been completed. Key findings:

- **`trigger.py` (FastAPI) hardcodes `task_id = "run-pipeline"`** when triggering child runs via the Trigger.dev SDK. This is the single routing decision point on the FastAPI side.
- **The fan-out child contract is built around generic DB-hydrated payloads.** The fan-out endpoint creates child `pipeline_runs` in the database, then triggers a Trigger.dev task with a payload that includes `pipeline_run_id`, `submission_id`, and related IDs. The child task (`run-pipeline`) hydrates the full run context from the database.
- **Dedicated workflows expect explicit workflow-specific payloads.** They take domain, org context, client context, etc. as direct input — not a `pipeline_run_id` to hydrate from the database.
- **The agreed approach is Path B: a thin router task** in Trigger.dev that receives the generic fan-out payload, determines which dedicated workflow to invoke based on the pipeline run's context, builds the correct workflow-specific payload, and triggers the target workflow. This preserves the existing DB fan-out infrastructure while enabling dedicated workflows as fan-out targets.

---

## The Problem

When a parent workflow or `run-pipeline` fans out, FastAPI creates child `pipeline_runs` and triggers a Trigger.dev task. Today that task is always `run-pipeline`. The router task sits between the fan-out trigger and the target workflow — it receives the generic payload, resolves which workflow should handle this child run, translates the payload, and triggers the correct dedicated workflow (or falls back to `run-pipeline` for workflows that haven't been migrated yet).

---

## Architectural Constraints

1. **The router task is a new Trigger.dev task in `trigger/src/tasks/`.** It is thin — its job is routing and payload translation, not orchestration.

2. **FastAPI's fan-out endpoint (`trigger.py`) must be updated to trigger the router task instead of `run-pipeline` directly.** This is the only FastAPI change in this directive. The `task_id` that `trigger.py` sends to the Trigger.dev SDK must change from `"run-pipeline"` to the router task's ID.

3. **The router must fall back to `run-pipeline` for unrecognized workflows.** Not every pipeline has a dedicated workflow yet. If the router cannot determine a dedicated workflow target, it must invoke `run-pipeline` with the original generic payload. The system must not break for pipelines that haven't been migrated.

4. **The existing lineage contract must be preserved.** Child `pipeline_runs` and `step_results` are already created by the FastAPI fan-out endpoint before the router task runs. The router does not create lineage records — it routes to a workflow that operates within the already-created pipeline run. The target workflow must update the existing `pipeline_run` and `step_result` records, not create new ones.

5. **Payload translation is the router's core responsibility.** The generic fan-out payload contains database IDs (`pipeline_run_id`, `submission_id`, `org_id`, `company_id`). The dedicated workflows expect domain-level inputs (`company_domain`, `client_context`, `person_linkedin_url`, etc.). The router must hydrate the necessary context from the database (via FastAPI internal endpoints) and build the workflow-specific payload.

6. **The routing decision must be deterministic.** The router needs to know which dedicated workflow to invoke for a given child run. You decide the routing mechanism — it could be based on the blueprint name, an explicit `workflow_id` field on the pipeline run, the operation sequence in the blueprint snapshot, or another approach. The mechanism must be unambiguous and extensible as more workflows are added.

7. **Deploy protocol applies.** When deployed: Railway first (the `trigger.py` change and any new internal endpoints), Trigger.dev second (the router task and any workflow changes). This is especially critical here because the router task depends on the FastAPI change to route correctly.

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, auth model, deploy protocol
- `trigger/src/tasks/run-pipeline.ts` — how child runs are currently handled: the task receives a generic payload, hydrates from the database, and executes. Understand the input contract.
- `trigger/src/tasks/` — all five dedicated workflow files. Understand each workflow's input shape so you can build the payload translation for each.
- `app/routers/internal.py` — the `/api/internal/pipeline-runs/fan-out` endpoint and `/api/internal/pipeline-runs/get` endpoint. Understand what data is available for the router to hydrate context.
- The FastAPI file that triggers Trigger.dev tasks (likely `app/services/trigger.py` or similar — search for `task_id = "run-pipeline"` to find the exact location). This is the file you will modify.
- `supabase/migrations/010_fan_out.sql` — the fan-out schema
- `docs/NESTED_FAN_OUT_TRACE.md` — how recursive fan-out works

---

## Deliverable 1: Router Task

Create a new Trigger.dev task in `trigger/src/tasks/` that acts as the fan-out router.

**Input:** The same generic payload that `run-pipeline` currently receives from fan-out triggers (pipeline_run_id, submission_id, org context, etc.).

**Behavior:**
- Determine which dedicated workflow should handle this child run
- Hydrate whatever context the target workflow needs (via FastAPI internal endpoints)
- Build the workflow-specific payload
- Trigger the target dedicated workflow
- Fall back to triggering `run-pipeline` if no dedicated workflow matches

The routing logic, hydration strategy, and payload translation mappings are your engineering decisions. The router must handle all five existing dedicated workflows plus the `run-pipeline` fallback.

Commit standalone.

---

## Deliverable 2: Update FastAPI Task Triggering

Update the FastAPI code that triggers Trigger.dev tasks for fan-out child runs. Change the hardcoded `task_id` from `"run-pipeline"` to the router task's ID.

This should be a minimal, isolated change. The fan-out endpoint's behavior (creating child pipeline_runs, step_results) does not change — only the task ID it triggers changes.

Commit standalone.

---

## Deliverable 3: Verify Lineage Preservation

Verify that the router + dedicated workflow path preserves the existing lineage contract:
- Child `pipeline_runs` created by the fan-out endpoint are updated by the target workflow (status transitions, completion)
- Child `step_results` are updated by the target workflow
- Parent submission status sync still works
- Nested fan-out (a child that itself fans out) still works through the router

You decide how to verify this — tests, trace analysis, or both.

Commit standalone.

---

## Deliverable 4: Tests

Write tests that verify:
- The router correctly identifies which workflow to invoke for each of the five dedicated workflow types
- The router falls back to `run-pipeline` for unrecognized pipelines
- Payload translation produces the correct workflow-specific input for each workflow type
- The routing decision is deterministic
- The FastAPI trigger change sends the correct task ID

Mock all HTTP calls and Trigger.dev SDK calls. Do not call production.

Commit standalone.

---

## What is NOT in scope

- No modifications to the five dedicated workflow files (unless a minor interface change is needed to accept the router's payload — if so, keep it minimal and report it)
- No modifications to `run-pipeline.ts`
- No modifications to the fan-out endpoint's DB behavior (it still creates child pipeline_runs the same way)
- No database migrations
- No deploy commands
- No removal of `run-pipeline` or deprecation of the generic path

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

This is a high-risk deploy ordering scenario. When deployed: Railway first (the `trigger.py` change must be live so fan-out triggers the router task), wait for it to be live, then Trigger.dev second (the router task must exist before fan-out can invoke it). If Trigger.dev deploys first, the router task exists but FastAPI still triggers `run-pipeline` — that's safe (no behavior change). If Railway deploys first but Trigger.dev hasn't deployed the router task yet, fan-out will try to trigger a task that doesn't exist — **that would break fan-out**. Coordinate carefully. The safest sequence is: deploy Trigger.dev first (adds the router task, but it won't be invoked yet), then deploy Railway (switches fan-out to invoke the router).

**This is the one case where the standard "Railway first, Trigger second" order should be reversed.** Flag this clearly in your report.

## When done

Report back with:
(a) Router task file path and the routing mechanism (how it determines which workflow to invoke)
(b) Payload translation approach — how generic DB-hydrated context becomes workflow-specific input for each of the five workflows
(c) The fallback behavior for unrecognized pipelines
(d) Which FastAPI file was changed and the exact nature of the change
(e) How lineage preservation was verified
(f) Test count and what they cover
(g) Deploy ordering recommendation — confirm the reversed deploy order and any other sequencing concerns
(h) Anything to flag — edge cases in routing, payload mismatches discovered, nested fan-out implications, or changes needed in the dedicated workflow input contracts
