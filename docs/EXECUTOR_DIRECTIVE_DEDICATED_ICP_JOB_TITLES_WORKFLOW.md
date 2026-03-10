# Directive: Priority 3 (continued) — ICP Job Titles Discovery Workflow

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Parallel.ai deep research is the highest-value ICP job titles source in the system. It is long-running and currently trapped inside the `run-pipeline.ts` monolith with a fixed 20-second polling interval, hardcoded prompt text, and inline persistence side effects. This directive extracts that behavior into a dedicated workflow that uses the shared workflow utilities, establishes a reusable Parallel polling pattern for future intel briefings, and keeps confirmed persistence explicit instead of silent.

Production truth to protect: `company.derive.icp_job_titles` is one of the 4 Trigger-direct operations, and the `icp_job_titles` materialization path is healthy today. Do not regress the healthy path while extracting it out of `run-pipeline.ts`.

---

## The Problem

A company domain goes in. ICP job titles for that company come out. Parallel.ai deep research is asynchronous: create a task run, poll until terminal state, then fetch the result. The current implementation polls every 20 seconds forever-ish. The dedicated workflow must replace that with a staged polling schedule that polls more aggressively early and backs off as the run ages.

The input contract also needs to improve. The current inline implementation fails if `company_name` is missing. The dedicated workflow must support a domain-only invocation, while still using `company_name` and `company_description` when they are available.

---

## Architectural Constraints

1. **Create a new Trigger.dev task entrypoint in `trigger/src/tasks/icp-job-titles-discovery.ts`.** It wraps a dedicated workflow module. Do NOT modify `trigger/src/tasks/run-pipeline.ts`.

2. **Create a dedicated workflow module in `trigger/src/workflows/icp-job-titles-discovery.ts`.** Follow the same separation used by `trigger/src/tasks/company-enrichment.ts` + `trigger/src/workflows/company-enrichment.ts` and `trigger/src/tasks/person-search-enrichment.ts` + `trigger/src/workflows/person-search-enrichment.ts`.

3. **Put the reusable Parallel helper in `trigger/src/workflows/parallel-deep-research.ts`.** This utility is not ICP-specific. Future `company.derive.intel_briefing` and `person.derive.intel_briefing` workflows must be able to import it without inheriting ICP-specific prompt or extraction logic.

4. **Put the ICP prompt renderer in `trigger/src/workflows/prompts/icp-job-titles.ts`.** Keep prompt text and prompt rendering logic separate from orchestration. Future Parallel workflows should follow the same `trigger/src/workflows/prompts/` pattern.

5. **Reuse the existing shared workflow modules where they already solve the problem.** The expected reuse points are:
   - `trigger/src/workflows/internal-api.ts`
   - `trigger/src/workflows/persistence.ts`
   - `trigger/src/workflows/lineage.ts`
   - `trigger/src/workflows/context.ts`
   - `trigger/src/workflows/operations.ts` only if you genuinely need shared result types; do not force the Parallel workflow through `POST /api/v1/execute`

6. **Parallel.ai is called directly from Trigger.dev, not through FastAPI.** This remains a Trigger-direct operation. Use `PARALLEL_API_KEY` from the Trigger runtime only. Do not add a FastAPI provider wrapper for this directive.

7. **Do not hardcode database schema names in Trigger code.** Ground truth today is that production still runs in `public`, even though the repo contains schema-split work. Trigger code must stay schema-agnostic and call FastAPI internal endpoints only. FastAPI owns schema qualification and table routing.

8. **Persist to both entity state and `icp_job_titles` with confirmed writes.** The workflow must know whether each write succeeded. Silent warning logs are not acceptable.

9. **Lineage stays in the existing model.** This is a long-running single-entity workflow, not a fan-out workflow. One pipeline run, one explicit workflow step, one long-running step result. Do not create synthetic per-poll `step_results`.

10. **Deploy protocol applies, but deployment is not part of this directive.** Railway first, Trigger.dev second.

---

## External API Shape To Preserve

The current `run-pipeline.ts` implementation calls Parallel with this shape. Your new utility should preserve the same external contract unless the current Parallel docs prove it has changed:

- `POST https://api.parallel.ai/v1/tasks/runs`
  - Headers: `x-api-key`, `Content-Type: application/json`
  - Body: `{"input": "<rendered prompt>", "processor": "<processor>"}`
  - Current code expects at minimum: `run_id`, `status`

- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}`
  - Headers: `x-api-key`
  - Current code expects at minimum: `status`

- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result`
  - Headers: `x-api-key`
  - Current code stores the full raw JSON response as `parallel_raw_response`
  - The current `icp_job_titles` backfill path assumes the structured ICP payload needed by the dedicated-table writer lives at `parallel_raw_response.output.content`

If the live Parallel docs differ, align to the live docs, but keep the result normalization stable for the workflow and the dedicated-table upsert path.

---

## Internal Endpoint Shapes To Use

These endpoints already exist. Use them as-is.

- `POST /api/internal/pipeline-runs/update-status`
  - Request: `pipeline_run_id`, `status`, optional `error_message`, optional `error_details`

- `POST /api/internal/step-results/update`
  - Request: `step_result_id`, `status`, optional `input_payload`, optional `output_payload`, optional `error_message`, optional `error_details`, optional `duration_ms`, optional `task_run_id`

- `POST /api/internal/entity-state/upsert`
  - Request: `pipeline_run_id`, `entity_type`, `cumulative_context`, optional `last_operation_id`
  - Important: FastAPI currently rejects this call unless the pipeline run is already in `succeeded`

- `POST /api/internal/icp-job-titles/upsert`
  - Request: `company_domain`, optional `company_name`, optional `company_description`, `raw_parallel_output`, optional `parallel_run_id`, optional `processor`, optional `source_submission_id`, optional `source_pipeline_run_id`

Internal auth remains:
- `Authorization: Bearer <INTERNAL_API_KEY>`
- `x-internal-org-id: <org_uuid>`
- `x-internal-company-id: <company_uuid>`

---

## Existing Code To Read Before Starting

- `CLAUDE.md`
- `docs/STRATEGIC_DIRECTIVE.md`
- `docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `trigger/src/tasks/run-pipeline.ts`
  - Study `executeParallelDeepResearch(...)`
  - Study the `ICP_JOB_TITLES_PROMPT_TEMPLATE`
  - Study the current `company.derive.icp_job_titles` auto-persist block
- `trigger/src/workflows/internal-api.ts`
- `trigger/src/workflows/persistence.ts`
- `trigger/src/workflows/lineage.ts`
- `trigger/src/workflows/context.ts`
- `trigger/src/workflows/company-enrichment.ts`
- `trigger/src/workflows/person-search-enrichment.ts`
- `trigger/src/tasks/company-enrichment.ts`
- `trigger/src/tasks/person-search-enrichment.ts`
- `app/routers/internal.py`
  - `InternalPipelineRunStatusUpdateRequest`
  - `InternalStepResultUpdateRequest`
  - `InternalEntityStateUpsertRequest`
  - `InternalUpsertIcpJobTitlesRequest`
  - `/api/internal/icp-job-titles/upsert`
  - `/api/internal/entity-state/upsert`
- `scripts/backfill_icp_job_titles.py`
- `docs/api-reference-docs/parallel/` for any Parallel material that helps confirm request/response assumptions

---

## Deliverable 1: Shared Parallel Polling Utility

Create `trigger/src/workflows/parallel-deep-research.ts`.

This module must provide a reusable async runner for Parallel task creation, staged polling, terminal-state handling, and result retrieval. Design it so the caller provides:

- the rendered prompt
- processor
- operation/provider labels for lineage metadata
- any caller-specific validation or output extraction logic
- polling configuration

The utility must:

- support staged polling intervals rather than one fixed interval
- support a max total wait / timeout policy
- treat malformed or incomplete terminal responses as explicit failures, not quiet `not_found`
- surface create-status-result HTTP failures with enough detail for the workflow to write useful `error_details`
- return enough metadata for workflow-level lineage and persistence:
  - `parallel_run_id`
  - terminal status
  - poll count
  - elapsed wait information
  - processor
  - raw result payload when available

Testing requirement for this utility:

- make the wait/sleep behavior injectable or otherwise directly testable
- do not require real timers or real network calls to verify the staged schedule

If `trigger/src/workflows/persistence.ts` needs a small extension for typed confirmed writes used by this workflow, make that change here. Do not duplicate existing confirmation logic.

Commit standalone.

---

## Deliverable 2: ICP Job Titles Prompt Extraction

Create `trigger/src/workflows/prompts/icp-job-titles.ts`.

Requirements:

- extract the current ICP prompt text out of `run-pipeline.ts`
- render from structured company input instead of raw string replacement scattered inside the workflow
- support a **domain-only** invocation
- enrich the prompt when `company_name` and `company_description` are present
- keep the output intent compatible with the current dedicated-table extraction path; do not casually change the semantic shape of the research result

The prompt module may export a template constant plus a renderer, or a renderer-only API. Keep orchestration logic out of this file.

Commit standalone.

---

## Deliverable 3: ICP Job Titles Discovery Workflow Task

Create:

- `trigger/src/workflows/icp-job-titles-discovery.ts`
- `trigger/src/tasks/icp-job-titles-discovery.ts`

Use task id: `icp-job-titles-discovery`.

### Workflow Input

At minimum, the workflow payload must accept:

- `pipeline_run_id`
- `org_id`
- `company_id`
- `company_domain`
- `step_results`

Also support:

- optional `submission_id`
- optional `initial_context`
- optional `company_name`
- optional `company_description`
- optional `processor`
- optional `api_url`
- optional `internal_api_key`

This should follow the same payload style as the existing dedicated workflow files.

### Workflow Behavior

The workflow must:

1. Build seed context using the existing shared context helpers.
2. Validate that the workflow received the expected single step mapping for this dedicated workflow.
3. Mark the pipeline run `running`.
4. Mark the single step result `running`.
5. Render the ICP prompt from Deliverable 2.
6. Execute Parallel deep research via the new shared utility from Deliverable 1.
7. Normalize the successful result into workflow output and cumulative context.
8. Mark the step result `succeeded` or `failed` with auditable output/error payloads.
9. Perform the dual-write path with confirmed writes:
   - entity state upsert
   - `icp_job_titles` upsert
10. Surface any persistence failure explicitly on the pipeline run.

### Dual-Write Contract

This workflow is replacing the silent auto-persist pattern. Use this explicit behavior:

- When the Parallel step itself fails, the step result is `failed` and the pipeline run is `failed`.
- When the Parallel step succeeds, the step result should record that success before persistence begins.
- Because `/api/internal/entity-state/upsert` requires a succeeded pipeline run, you will need to mark the pipeline run `succeeded` before calling that endpoint.
- If either confirmed write then fails, immediately rewrite the pipeline run to `failed` with error details identifying which write failed.

That means execution lineage can truthfully show:

- the research step succeeded
- the workflow still failed overall because post-step persistence failed

This is acceptable and preferable to a false-green run.

### Result Normalization Requirements

Preserve the full Parallel result blob for auditability, but do not force downstream code to dig through raw provider JSON when a normalized field is easy to surface. At minimum, the workflow output/cumulative context should carry:

- `parallel_run_id`
- `processor`
- normalized `company_domain`
- optional `company_name`
- optional `company_description`
- full `parallel_raw_response`

And for the dedicated-table write:

- extract `raw_parallel_output` from the completed Parallel result in the same conceptual shape assumed by `scripts/backfill_icp_job_titles.py`

If that extraction path is not present in a completed result, treat it as an incomplete-response failure, not as success.

### Lineage Expectations

This is a long-running single-step workflow. Keep lineage simple and explicit:

- one pipeline run
- one step result at position `1`
- no child runs
- no per-poll step result updates

Do include poll metadata in the final step output and/or provider-attempt metadata so a 10-30 minute wait is still diagnosable after the fact.

Commit standalone.

---

## Deliverable 4: Tests

Add tests under the existing Trigger test structure. Expected files:

- `trigger/src/workflows/__tests__/parallel-deep-research.test.ts`
- `trigger/src/workflows/__tests__/icp-job-titles-discovery.test.ts`
- `trigger/src/workflows/__tests__/icp-job-titles-prompt.test.ts`

You may collapse the prompt assertions into the workflow test if that produces a cleaner suite, but the prompt renderer must still be directly tested.

Coverage required:

- polling utility success path
- polling utility timeout path
- polling utility error path for task creation, status polling, and result fetch
- staged polling schedule is actually staged, not constant
- domain-only prompt rendering
- prompt rendering with company name and description
- successful dual-write flow
- entity-state write failure is surfaced
- `icp_job_titles` write failure is surfaced
- incomplete Parallel result shape is surfaced
- lineage status updates for the long-running single-step path

Mock all HTTP calls to:

- Parallel.ai endpoints
- FastAPI internal endpoints

Do not call production. Do not call real Parallel.

Commit standalone.

---

## What is NOT in scope

- No modifications to `trigger/src/tasks/run-pipeline.ts`
- No modifications to FastAPI endpoints or request models
- No database migrations
- No deploy commands
- No intel briefing workflows
- No changes to `trigger/src/workflows/company-enrichment.ts`
- No changes to `trigger/src/workflows/person-search-enrichment.ts`
- No blueprint submission flow changes
- No `extracted_icp_job_title_details` extraction or downstream processing
- No provider abstraction layer inside FastAPI for Parallel.ai

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first, wait for Railway to be live, then Trigger.dev. The workflow depends on existing FastAPI internal endpoints being live before the Trigger task runs. `PARALLEL_API_KEY` must exist in Trigger.dev env vars.

## When done

Report back with:

(a) Polling utility file path and public API — function signature, parameters, how callers configure prompt/input/extraction
(b) The staged polling interval schedule you chose and the rationale
(c) Prompt file location and format
(d) Which shared utilities you reused vs. extended
(e) How confirmed writes work for the dual-write path — including what happens if entity state succeeds and `icp_job_titles` fails, and vice versa
(f) How lineage tracking works for this long-running single-step workflow
(g) Test count and what they cover
(h) Anything to flag — Parallel API shape assumptions, incomplete-result edge cases, and implications for future intel briefing workflows
