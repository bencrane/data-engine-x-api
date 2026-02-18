# Step Timeline Event Schema

## Purpose

This document is the contract for per-step timeline observability events written to `entity_timeline`.

The contract applies to runner-driven terminal step transitions only.

## Event Type

- `event_type`: `"step_execution"`

## Emit Rules (Idempotency + Lifecycle)

- Timeline is append-only.
- Emit exactly once per terminal transition attempt from the runner for:
  - `succeeded`
  - `failed`
  - `skipped`
- Do **not** emit for non-terminal states:
  - `queued`
  - `running`
- Timeline write failures are non-fatal to orchestration.

## Metadata Shape

Every `step_execution` event must include these metadata keys:

- `event_type` (`"step_execution"`)
- `step_result_id` (`string`)
- `step_position` (`integer`)
- `operation_id` (`string`)
- `step_status` (`"succeeded" | "failed" | "skipped"`)
- `skip_reason` (`string | null`) - required when `step_status = "skipped"`
- `duration_ms` (`integer | null`)
- `provider_attempts` (`array`) - may be empty
- `condition` (`object | null`) - populated for condition-based skips
- `error_message` (`string | null`)
- `error_details` (`object | null`)

## Timeline Status Mapping

- `succeeded -> found`
- `failed -> failed`
- `skipped -> skipped`

## Provider Selection Rule

Given `provider_attempts`:

1. Pick the first attempt where:
   - `attempt.status` is `found` or `succeeded`, and
   - `attempt.provider` is present.
2. Else pick `provider` from the first attempt (if present).
3. Else `provider = null`.

## Fields Updated Rule

- For succeeded steps: infer from `operation_result.output` when available.
  - Use non-null output keys, sorted, unique.
- For failed/skipped steps: `fields_updated = null`.

## Required Query Patterns

The timeline table/query path must support:

1. `(org_id, entity_type, entity_id, created_at desc)`
2. `(org_id, pipeline_run_id)`
3. `(org_id, submission_id)` for run-level investigations
