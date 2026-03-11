# Directive: Dedicated Company Intel Briefing Workflow

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The ICP job titles discovery workflow established the Parallel.ai pattern in the new architecture: a reusable polling utility with staged intervals, prompt extraction into standalone files, and dual confirmed writes through FastAPI internal endpoints. This directive builds the second Parallel.ai workflow: company intel briefings, using the same foundation rather than another one-off block inside the `run-pipeline.ts` monolith.

Production truth to protect: `company.derive.intel_briefing` is one of the Trigger-direct Parallel operations, and the `company_intel_briefings` materialization path is healthy today in production with `3` successful executions and `3` rows. Do not regress the healthy path while extracting it out of `run-pipeline.ts`.

---

## The Problem

A target company domain and client company context go in. A Parallel.ai deep research intel briefing about that target company comes out, framed explicitly through the client company's sales lens. The workflow must call Parallel.ai directly from Trigger.dev, reuse the shared staged polling utility from the ICP workflow, and persist the successful result to both entity state and the `company_intel_briefings` dedicated table with confirmed writes.

The current inline implementation has two important weaknesses that this dedicated workflow should correct:

1. It is trapped inside `trigger/src/tasks/run-pipeline.ts`.
2. It hard-requires `target_company_name`, even though the real minimum business input is a company domain plus client context.

The dedicated workflow should support a domain-first target-company invocation while still using richer company metadata when it exists.

---

## Architectural Constraints

1. **Create a new Trigger.dev task entrypoint in `trigger/src/tasks/company-intel-briefing.ts`.** It wraps a dedicated workflow module. Do NOT modify `trigger/src/tasks/run-pipeline.ts`.

2. **Create a dedicated workflow module in `trigger/src/workflows/company-intel-briefing.ts`.** Follow the same separation already used by:
   - `trigger/src/tasks/icp-job-titles-discovery.ts`
   - `trigger/src/workflows/icp-job-titles-discovery.ts`

3. **Reuse the existing Parallel polling utility in `trigger/src/workflows/parallel-deep-research.ts`.** Do not create a second polling loop. Do not duplicate create-status-result handling. If you discover a real bug in the shared utility, stop and report it rather than quietly introducing a briefing-specific workaround.

4. **Extract the prompt into `trigger/src/workflows/prompts/company-intel-briefing.ts`.** Follow the same pattern as `trigger/src/workflows/prompts/icp-job-titles.ts`: keep prompt text and prompt rendering logic separate from orchestration.

5. **Parallel.ai remains Trigger-direct.** Do not route this through FastAPI. Use `PARALLEL_API_KEY` from the Trigger.dev runtime only.

6. **Trigger code must remain schema-agnostic.** Do not hardcode `public`, `ops`, or `entities` schema names in Trigger. Production truth today is still `public`, even though schema-split work exists in the repo. Trigger calls FastAPI internal endpoints only; FastAPI owns schema qualification and table routing.

7. **Persist to both entity state and `company_intel_briefings` with confirmed writes.** No silent warning-and-continue behavior. The workflow must know whether each write succeeded and must surface failures explicitly.

8. **The workflow is client-scoped.** Require client context in the workflow input. At minimum, require:
   - `client_company_name`
   - `client_company_domain`
   - `client_company_description`

9. **Lineage stays simple.** This is a long-running single-step workflow:
   - one pipeline run
   - one explicit step result
   - no child runs
   - no synthetic per-poll `step_results`

10. **Deploy protocol applies, but deployment is not part of this directive.** Railway first, Trigger.dev second.

---

## External API Shape To Preserve

Unless live Parallel docs prove the contract changed, preserve the same external API shape the current `run-pipeline.ts` implementation uses:

- `POST https://api.parallel.ai/v1/tasks/runs`
  - Headers: `x-api-key`, `Content-Type: application/json`
  - Body: `{"input": "<rendered prompt>", "processor": "<processor>"}`
  - Expected response fields: at minimum `run_id`, `status`

- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}`
  - Headers: `x-api-key`
  - Expected response fields: at minimum `status`

- `GET https://api.parallel.ai/v1/tasks/runs/{run_id}/result`
  - Headers: `x-api-key`
  - Preserve the full raw JSON result for auditability as `parallel_raw_response`
  - The dedicated-table write should continue extracting the structured briefing payload from `parallel_raw_response.output.content`

If Parallel's live docs have changed, align to the live docs but keep the workflow-facing result normalization and dedicated-table extraction stable.

---

## Internal Endpoint Shapes To Use

These endpoints already exist. Use them as-is.

- `POST /api/internal/pipeline-runs/update-status`
  - Request: `pipeline_run_id`, `status`, optional `error_message`, optional `error_details`, optional `trigger_run_id`, optional timestamps

- `POST /api/internal/step-results/update`
  - Request: `step_result_id`, `status`, optional `input_payload`, optional `output_payload`, optional `error_message`, optional `error_details`, optional `duration_ms`, optional `task_run_id`

- `POST /api/internal/entity-state/upsert`
  - Request: `pipeline_run_id`, `entity_type`, `cumulative_context`, optional `last_operation_id`
  - Important: FastAPI currently rejects this call unless the pipeline run is already `succeeded`

- `POST /api/internal/company-intel-briefings/upsert`
  - Request:
    - `company_domain`
    - optional `company_name`
    - optional `client_company_name`
    - optional `client_company_domain`
    - optional `client_company_description`
    - `raw_parallel_output`
    - optional `parallel_run_id`
    - optional `processor`
    - optional `source_submission_id`
    - optional `source_pipeline_run_id`

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
  - Study `COMPANY_INTEL_BRIEFING_PROMPT_TEMPLATE`
  - Study `executeCompanyIntelBriefing(...)`
  - Study the current `company.derive.intel_briefing` auto-persist block for `company_intel_briefings`
- `trigger/src/workflows/parallel-deep-research.ts`
- `trigger/src/workflows/prompts/icp-job-titles.ts`
- `trigger/src/workflows/icp-job-titles-discovery.ts`
- `trigger/src/tasks/icp-job-titles-discovery.ts`
- `trigger/src/workflows/internal-api.ts`
- `trigger/src/workflows/persistence.ts`
- `trigger/src/workflows/lineage.ts`
- `trigger/src/workflows/context.ts`
- `app/routers/internal.py`
  - `InternalPipelineRunStatusUpdateRequest`
  - `InternalStepResultUpdateRequest`
  - `InternalEntityStateUpsertRequest`
  - `InternalUpsertCompanyIntelBriefingsRequest`
  - `/api/internal/company-intel-briefings/upsert`
  - `/api/internal/entity-state/upsert`
- `supabase/migrations/016_intel_briefing_tables.sql`

---

## Deliverable 1: Company Intel Briefing Prompt Extraction

Create `trigger/src/workflows/prompts/company-intel-briefing.ts`.

Requirements:

- extract the current company intel briefing prompt text out of `trigger/src/tasks/run-pipeline.ts`
- follow the same renderer pattern as `trigger/src/workflows/prompts/icp-job-titles.ts`
- accept structured input for both:
  - the client company
  - the target company
- support a **domain-first target company invocation**
  - `company_domain` is required
  - `company_name` is optional
  - when target metadata such as description, industry, size, funding, or competitors exists, use it
- require all three client fields for prompt rendering:
  - `client_company_name`
  - `client_company_domain`
  - `client_company_description`
- improve the prompt slightly where it is clearly low-risk and beneficial:
  - include `client_company_domain` in the rendered research context
  - preserve the same output intent and general schema
  - do not casually redesign the research deliverable

Do NOT modify `trigger/src/tasks/run-pipeline.ts`.

Commit standalone.

---

## Deliverable 2: Company Intel Briefing Workflow Task

Create:

- `trigger/src/workflows/company-intel-briefing.ts`
- `trigger/src/tasks/company-intel-briefing.ts`

Use task id: `company-intel-briefing`.

### Workflow Input

At minimum, the workflow payload must accept:

- `pipeline_run_id`
- `org_id`
- `company_id`
- `company_domain`
- `client_company_name`
- `client_company_domain`
- `client_company_description`
- `step_results`

Also support:

- optional `submission_id`
- optional `initial_context`
- optional `company_name`
- optional `company_description`
- optional `company_industry`
- optional `company_size`
- optional `company_funding`
- optional `company_competitors`
- optional `processor`
- optional `api_url`
- optional `internal_api_key`

This should follow the same payload style as `trigger/src/workflows/icp-job-titles-discovery.ts`.

### Workflow Behavior

The workflow must:

1. Build seed context using the existing shared context helpers.
2. Validate that the workflow received the expected single-step mapping for this dedicated workflow.
3. Mark the pipeline run `running`.
4. Mark the single step result `running`.
5. Render the company intel briefing prompt from Deliverable 1.
6. Execute Parallel deep research via `runParallelDeepResearch(...)` from `trigger/src/workflows/parallel-deep-research.ts`.
7. Normalize the successful result into workflow output and cumulative context.
8. Mark the step result `succeeded` or `failed` with auditable output/error payloads.
9. Perform the dual-write path with confirmed writes:
   - entity state upsert
   - `company_intel_briefings` upsert
10. Surface any persistence failure explicitly on the pipeline run.

### Result Normalization Requirements

Preserve the full Parallel result blob for auditability, but do not force downstream code to dig through raw provider JSON when a normalized field is easy to surface. At minimum, the workflow output and cumulative context should carry:

- `parallel_run_id`
- `processor`
- normalized `company_domain`
- optional `company_name`
- `client_company_name`
- `client_company_domain`
- `client_company_description`
- full `parallel_raw_response`
- extracted `raw_parallel_output`

For the dedicated-table write:

- extract `raw_parallel_output` from the completed Parallel result in the same conceptual shape used by the current inline company intel briefing persistence path
- if `parallel_raw_response.output.content` is missing, empty, or malformed, treat that as an incomplete-response failure, not success

### Dual-Write Contract

This workflow is replacing the silent auto-persist pattern. Use the same explicit persistence contract established by the ICP workflow:

- when the Parallel step itself fails, the step result is `failed` and the pipeline run is `failed`
- when the Parallel step succeeds, the step result should record that success before persistence begins
- because `/api/internal/entity-state/upsert` requires a succeeded pipeline run, you will need to mark the pipeline run `succeeded` before calling that endpoint
- if either confirmed write then fails, immediately rewrite the pipeline run to `failed` with error details identifying which write failed

That means lineage can truthfully show:

- the research step succeeded
- the workflow still failed overall because post-step persistence failed

This is acceptable and preferable to a false-green run.

### Lineage Expectations

This is a long-running single-step workflow. Keep lineage simple and explicit:

- one pipeline run
- one step result at position `1`
- no child runs
- no per-poll step result updates

Do include poll metadata in final output or provider-attempt metadata so a 10-30 minute wait is diagnosable afterward.

Commit standalone.

---

## Deliverable 3: Tests

Add tests under the existing Trigger test structure. Expected files:

- `trigger/src/workflows/__tests__/company-intel-briefing-prompt.test.ts`
- `trigger/src/workflows/__tests__/company-intel-briefing.test.ts`

You do not need a new polling utility test file. The shared polling utility is already covered by `trigger/src/workflows/__tests__/parallel-deep-research.test.ts`. For this directive, the key requirement is proving the briefing workflow reuses that shared utility rather than a custom loop.

Coverage required:

- prompt rendering with full target-company and client-company context
- prompt rendering for a domain-first target-company invocation
- missing client context fails explicitly
- workflow calls `runParallelDeepResearch(...)` from the shared utility rather than implementing its own polling loop
- successful dual-write flow
- entity-state write failure is surfaced
- `company_intel_briefings` write failure is surfaced
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
- No modifications to `trigger/src/workflows/parallel-deep-research.ts` unless you find a real shared-utility bug, in which case stop and report it
- No database migrations
- No deploy commands
- No person intel briefing workflow
- No changes to other dedicated workflows
- No blueprint submission flow changes
- No provider abstraction layer inside FastAPI for Parallel.ai

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first, wait for Railway to be live, then Trigger.dev. The workflow depends on existing FastAPI internal endpoints being live before the Trigger task runs. `PARALLEL_API_KEY` must exist in Trigger.dev env vars.

## When done

Report back with:

(a) Prompt file location and exactly how client context is templated into the prompt
(b) How the workflow reuses `trigger/src/workflows/parallel-deep-research.ts` and confirmation that no custom polling logic was introduced
(c) How confirmed writes work for the dual-write path, including what happens if entity state succeeds and `company_intel_briefings` fails, and vice versa
(d) The input shape and which client-context fields are required
(e) How this workflow differs from the ICP job titles workflow beyond prompt text and persistence target
(f) Test count and what they cover
(g) Anything to flag: prompt quality concerns, Parallel API shape differences between ICP and company briefing calls, and implications for the future person intel briefing workflow
