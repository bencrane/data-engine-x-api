# Phase Directive: Per-Step Timeline Observability

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Existing code to read:**
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — production timeline and entity state context
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — runtime boundary and entity accumulation flow
- `docs/STRATEGIC_DIRECTIVE.md` — doctrine and build rules
- `docs/SYSTEM_OVERVIEW.md` — secondary reference: execution flow, entity timeline, fan-out model
- `app/services/entity_timeline.py` — existing timeline recording
- `app/routers/internal.py` — internal endpoint patterns
- `trigger/src/tasks/run-pipeline.ts` — step execution and terminal state transitions

---

## Mission

Implement full per-step entity timeline observability so we can answer, at entity level:
- what operation ran,
- when it ran,
- whether it succeeded/failed/skipped,
- which provider produced the outcome,
- and what fields were updated.

Current timeline writes are limited to:
- fan-out discovery events, and
- final entity state upsert events.

This phase adds step-level audit coverage across the pipeline runner lifecycle.

---

## Why This Phase Now

- At scale (thousands of entities, many steps each), we need deterministic auditability.
- Dedup/freshness work is harder to validate without step-level event history.
- Debugging quality issues currently requires correlating `step_results` manually by run.
- Existing timeline table/service already exists; this is a focused expansion, not greenfield.

---

## Scope (In)

### Deliverable 0: Contract Lock (required first)

Create and lock a single source of truth for per-step timeline events.

Build:
- Add `docs/STEP_TIMELINE_EVENT_SCHEMA.md`.
- Define required event metadata keys for step-level events:
  - `event_type` = `"step_execution"`
  - `step_result_id`
  - `step_position`
  - `operation_id`
  - `step_status` (`succeeded` | `failed` | `skipped`)
  - `skip_reason` (nullable; required when skipped)
  - `duration_ms` (nullable)
  - `provider_attempts` (array, may be empty)
  - `condition` (nullable; for condition-based skips)
  - `error_message` (nullable)
  - `error_details` (nullable object)
- Define timeline `status` mapping policy:
  - `succeeded -> found`
  - `failed -> failed`
  - `skipped -> skipped`
- Define `provider` selection rule:
  - first successful provider from attempts if present, else first provider in attempts, else `null`.
- Define idempotency rule:
  - append-only; emit only on terminal step states (`succeeded|failed|skipped`) from runner-driven transitions.
  - no timeline write for `running` or `queued`.
- Define required query patterns:
  - by `(org_id, entity_type, entity_id, created_at desc)`
  - by `(org_id, pipeline_run_id)`
  - by `(org_id, submission_id)` for run-level investigation

Acceptance:
- Schema doc exists and is explicit enough to write tests against.
- Mapping and provider rules are unambiguous.
- No code behavior changes yet.

---

### Deliverable 1: Internal Timeline Write Path for Step Events

Centralize step event recording in FastAPI internal path (not in Trigger runner).

Build:
- Add a new internal endpoint in `app/routers/internal.py`:
  - `POST /api/internal/entity-timeline/record-step-event`
- Add request model with required fields:
  - tenancy + run linkage: `org_id`, `company_id`, `submission_id`, `pipeline_run_id`
  - entity resolution context: `entity_type`, `cumulative_context`
  - step context: `step_result_id`, `step_position`, `operation_id`, `step_status`
  - optional metadata: `skip_reason`, `duration_ms`, `provider_attempts`, `condition`, `error_message`, `error_details`
- Resolve entity id using existing deterministic resolvers:
  - `resolve_company_entity_id(...)` for company
  - `resolve_person_entity_id(...)` for person
- Call `record_entity_event(...)` with:
  - `status` mapped by contract
  - `provider` selected by contract rule
  - `fields_updated` inferred from successful `operation_result.output` when available; otherwise `None`
  - `summary` concise, deterministic, step-oriented
  - `metadata` containing schema-defined keys
- Make this endpoint best-effort:
  - timeline write failures must not throw fatal errors to orchestration path
  - return envelope indicating write attempted and event id if available

Acceptance:
- Endpoint is callable with internal auth.
- Entity id is deterministically derived for both person and company.
- Stored metadata matches schema doc.
- No regressions to existing fan-out/upsert timeline behavior.

---

### Deliverable 2: Runner Integration (Terminal Step States)

Emit step timeline events from Trigger runner by calling the new internal endpoint.

Build in `trigger/src/tasks/run-pipeline.ts`:
- After step update to terminal `succeeded`, call internal timeline endpoint.
- After step update to terminal `failed`, call internal timeline endpoint.
- After step update to terminal `skipped` (condition skip and parent condition skip), call internal timeline endpoint.
- Pass step and context payload exactly per schema contract.
- Keep orchestration resilient:
  - timeline call failures are logged but do not fail run execution path.
- Ensure fan-out short-circuit skip loop also emits step events for each downstream skipped step.

Acceptance:
- Every terminal step transition in runner path has a matching timeline emit attempt.
- No duplicate emits for a single terminal transition in normal flow.
- Pipeline run success/failure semantics unchanged.

---

### Deliverable 3: Query Support + Index Check

Ensure timeline reads support new usage patterns efficiently.

Build:
- Extend `POST /api/v1/entities/timeline` request support with optional filters:
  - `pipeline_run_id` (optional)
  - `submission_id` (optional)
  - `event_type` (optional; value like `step_execution`)
- Keep existing behavior fully backward compatible when filters are omitted.
- Add migration only if needed:
  - If no index exists for `(org_id, submission_id, created_at desc)`, add one migration.
  - Keep migration minimal and idempotent.

Acceptance:
- Existing timeline requests still work unchanged.
- Filtered queries return expected subset.
- New index exists only if required by schema/query plan.

---

### Deliverable 4: Tests

Add explicit tests for contract and behavior.

Required tests:
- `tests/test_internal_step_timeline.py` (new):
  - internal endpoint records success event with `status=found`
  - internal endpoint records failed event with `status=failed`
  - internal endpoint records skipped event with `status=skipped` and `skip_reason`
  - provider selection logic matches contract
  - metadata contains required keys
  - invalid/insufficient entity context handled safely (best-effort semantics)
- Trigger/runner integration tests (new or existing file):
  - condition_not_met skip emits step event
  - parent_step_condition_not_met skip emits events for downstream steps
  - failed step emits event
  - succeeded step emits event
  - timeline endpoint failure does not fail pipeline run logic
- Entities timeline query tests:
  - filtering by `pipeline_run_id`, `submission_id`, and `event_type`
  - tenant scoping unchanged

Acceptance:
- New tests pass.
- Existing relevant suites remain green.
- No test regressions in nested fan-out behavior.

---

## Scope (Out)

- No dedup/freshness logic in this directive.
- No operation registry metadata.
- No new providers or operation semantics.
- No UI for timeline exploration.
- No broad schema redesign.
- No deploy commands.

---

## Files to Read Before Starting

- `app/routers/internal.py` — existing internal callbacks, fan-out/upsert timeline writes
- `app/services/entity_timeline.py` — timeline write helper and status constraints
- `app/services/entity_state.py` — entity ID resolution and deterministic identity behavior
- `trigger/src/tasks/run-pipeline.ts` — step lifecycle and terminal transitions
- `app/routers/entities_v1.py` — timeline query endpoint behavior and auth scoping
- `supabase/migrations/009_entity_timeline.sql` — current timeline schema/indexes
- `tests/test_nested_fan_out.py` — existing internal router and orchestration testing pattern

---

## Technical Constraints

- Keep timeline writes append-only.
- Never allow observability write failures to crash orchestration flow.
- Preserve tenant/org/company scoping.
- Preserve existing API behavior unless explicitly expanded in scope.
- Keep types and naming consistent across Python and TypeScript.

---

## Commit Strategy

One commit per deliverable, in this order:
1. Deliverable 0 (contract doc)
2. Deliverable 1 (internal endpoint + service wiring)
3. Deliverable 2 (runner integration)
4. Deliverable 3 (timeline query/index updates)
5. Deliverable 4 (tests)

Do not push.

---

## Completion Report Format (Mandatory)

When done, report:
1. Implementation summary by deliverable
2. Files changed
3. Step-event schema (final shape)
4. Mapping details (`step_status -> timeline status`, provider selection)
5. How condition skips and fan-out downstream skips are recorded
6. Test suites run and pass counts
7. Any risks, edge cases, or follow-up recommendations
8. Any deviations from directive and rationale

