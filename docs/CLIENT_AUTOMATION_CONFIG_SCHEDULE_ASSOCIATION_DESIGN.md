# Client Automation Config, Schedule, and Association Design

## Objective

Add a client automation layer on top of the existing generic blueprint model so each `ops.companies` account can:

- store reusable blueprint input configs
- run configs on recurring schedules
- associate resulting canonical entities back to the client account without duplicating entity payloads

This design keeps FastAPI as the write owner, keeps Trigger.dev as orchestrator-only, and keeps canonical entities in `entities.*` while adding client visibility metadata in `ops.*`.

## Locked Decisions

- Client account model remains `ops.companies`; no new root `clients` table.
- Blueprints remain generic in `ops.blueprints`; client-specific inputs are stored in separate config rows.
- Recurrence uses DB-backed schedule rows plus one recurring Trigger task (`client-automation-scheduler`) that calls FastAPI internal endpoints.
- Due-run claiming and dedupe are enforced by an execution ledger table with a unique fire-window key.
- Client-to-entity visibility is enforced via explicit associations in `ops.company_entity_associations`.
- Canonical entity rows are not copied or duplicated per client.

## New Tables and Schema Placement

### `ops.company_blueprint_configs`

Purpose: reusable client-specific input configs bound to one blueprint.

Key columns:

- `org_id`, `company_id`, `blueprint_id`
- `name`, `description`
- `input_payload` (`JSONB`) for blueprint-variable input parameters
- `is_active`
- provenance fields: `created_by_user_id`, `updated_by_user_id`, timestamps

Uniqueness:

- `(org_id, company_id, name)` unique

Why in `ops`:

- config is execution/access metadata, not canonical entity intelligence.

### `ops.company_blueprint_schedules`

Purpose: recurring schedule definitions tied to one config.

Key columns:

- `config_id`, `org_id`, `company_id`
- `timezone`
- `cadence_minutes`
- `next_run_at`
- `last_claimed_at`, `last_succeeded_at`, `last_failed_at`, `last_submission_id`, `last_error`
- `is_active`

Uniqueness:

- `(org_id, company_id, name)` unique

Why in `ops`:

- schedule state is orchestration metadata.

### `ops.company_blueprint_schedule_runs`

Purpose: idempotent claim + execution ledger for each schedule fire window.

Key columns:

- `schedule_id`, `config_id`, `org_id`, `company_id`
- `scheduled_for` (fire window)
- `status` (`claimed | running | succeeded | failed | skipped`)
- `scheduler_task_id`, `scheduler_invoked_at`
- `submission_id`, `pipeline_run_id`
- `error_message`, `error_details`, `metadata`

Uniqueness:

- `(schedule_id, scheduled_for)` unique

Why in `ops`:

- run ledger is scheduling/execution provenance, not canonical data.

### `ops.company_entity_associations`

Purpose: explicit client visibility bridge from client company to canonical entity IDs.

Key columns:

- `org_id`, `company_id`
- `entity_type` (`company | person | job`)
- `entity_id` (UUID from canonical entity table)
- lineage fields: `source_submission_id`, `source_pipeline_run_id`, optional `source_step_result_id`, `source_operation_id`
- `metadata`

Uniqueness:

- `(org_id, company_id, entity_type, entity_id)` unique

Why in `ops`:

- this is tenant/client access metadata. Canonical entity state stays in `entities.*`.

## Schedule Idempotency and Duplicate Prevention

Idempotency is enforced at two layers:

1. **Schedule fire window uniqueness**
   - `ops.company_blueprint_schedule_runs` has unique `(schedule_id, scheduled_for)`.
   - overlapping evaluator invocations race safely; only one run row can exist for the same window.

2. **Submission idempotency for schedule runs**
   - scheduled submissions include `metadata.schedule_run_id`.
   - `ops.submissions` has a partial unique index on `metadata->>'schedule_run_id'` for `source='client_automation_schedule'`.
   - if a retry races after partial failure, duplicate submission creation is blocked by DB uniqueness.

Recoverability:

- claim rows persist even on failure.
- failed rows keep error details and can be inspected/replayed.
- schedules remain active; future windows continue.

## Trigger and FastAPI Responsibilities

- Trigger task: fixed cron evaluator loop only; no direct DB writes.
- FastAPI internal endpoint:
  - finds due schedules (`next_run_at <= now`)
  - claims each due window via schedule-run insert
  - creates submissions using existing submission flow
  - records run outcome + advances schedule timestamps

## Submission Provenance Contract

Scheduled submissions use:

- `source = "client_automation_schedule"`
- `metadata` includes:
  - `company_blueprint_config_id`
  - `company_blueprint_schedule_id`
  - `schedule_run_id`
  - `scheduler_invoked_at`
  - `scheduler_task_id`
  - `scheduled_for`

This gives full provenance from submission to config/schedule/fire-window.

## Entity Visibility Query Contract

For company-scoped users (`company_admin`, `member`):

- company/person/job entity list endpoints first resolve allowed entity IDs from `ops.company_entity_associations` for that company + entity type.
- canonical rows are then returned only for those IDs.
- `company_id` on canonical tables is not the sole visibility gate for client automation.

For org admins/super admins:

- existing org-scoped query behavior remains available.

## Compatibility With Current Reality and Doctrine

- Current canonical tables remain org-scoped (`entities.*`) and are not re-keyed in this workstream.
- Association layer is the forward-compatible visibility abstraction that decouples client access from canonical storage layout.
- No per-client entity payload copies are introduced.

## Worked Example: Outbound Solutions

Context:

- client company: `Outbound Solutions`
- domain: `outboundsolutions.com`

Flow:

1. Create `company_blueprint_config` for Outbound Solutions, referencing a generic hiring/discovery blueprint and storing config `input_payload` (target domains, title filters, etc.).
2. Create `company_blueprint_schedule` on that config (`timezone`, `cadence_minutes`, `next_run_at`).
3. Scheduler fires; FastAPI claims due window and inserts `company_blueprint_schedule_run` for `(schedule_id, scheduled_for)`.
4. FastAPI creates submission with `source='client_automation_schedule'` and metadata carrying config/schedule/run IDs.
5. Pipeline runs and upserts canonical entities as usual.
6. Entity upsert path records `company_entity_associations` rows for Outbound Solutions with source lineage (`submission_id`, `pipeline_run_id`).
7. Outbound Solutions company-scoped users query entity lists and see only associated entities.

