# Export Contract V1 (Data-Engine-X -> HQ)

## Purpose

Define a stable, versioned export contract from `data-engine-x` (operational system of record) to HQ warehouse (analytics/history system), so both systems stay aligned as the API and operations evolve.

This is a **Phase 1 required artifact**, even if sync jobs are implemented later.

---

## Scope

- Source system: `data-engine-x` Postgres
- Target system: HQ warehouse
- Entity model: `company` and `person`
- Export model version: `v1`

Contract principles:

- Event streams are append-only.
- Canonical state tables are upserted snapshots.
- All exported rows are tenant-scoped.
- Changes are additive-first; removals require deprecation window.

---

## Dataset Contract

## 1) `dx_operation_runs_v1` (append-only)

One row per operation invocation.

Required fields:

- `export_schema_version` (`text`) -> always `v1`
- `run_id` (`uuid/text`) -> unique operation run id
- `pipeline_run_id` (`uuid/text`) -> parent execution id (nullable for standalone)
- `workflow_id` (`text`, nullable)
- `operation_id` (`text`) -> canonical id (e.g. `company.enrich.profile`)
- `action_id` (`text`) -> concrete implementation id
- `entity_type` (`text`) -> `company` | `person`
- `entity_id` (`uuid/text`)
- `org_id` (`uuid/text`)
- `company_id` (`uuid/text`, nullable)
- `source_provider` (`text`, nullable) -> e.g. `prospeo`
- `status` (`text`) -> `succeeded` | `failed` | `skipped` | `canceled`
- `attempt_count` (`int`)
- `started_at` (`timestamptz`)
- `ended_at` (`timestamptz`, nullable)
- `duration_ms` (`int`, nullable)
- `cost_usd` (`numeric`, nullable)
- `error_code` (`text`, nullable)
- `error_message` (`text`, nullable)
- `created_at` (`timestamptz`)

Primary key:

- (`run_id`)

Partition recommendation:

- partition/cluster by `date(created_at)` and `org_id`

---

## 2) `dx_operation_events_v1` (append-only)

Detailed event log for retries, provider interactions, and state transitions.

Required fields:

- `export_schema_version` (`text`) -> `v1`
- `event_id` (`uuid/text`) -> unique event id
- `run_id` (`uuid/text`) -> FK-like link to operation run
- `event_type` (`text`) -> `request_sent`, `response_received`, `retry_scheduled`, `state_change`, `error`, etc.
- `event_sequence` (`int`) -> monotonic within `run_id`
- `occurred_at` (`timestamptz`)
- `org_id` (`uuid/text`)
- `company_id` (`uuid/text`, nullable)
- `entity_type` (`text`)
- `entity_id` (`uuid/text`)
- `provider` (`text`, nullable)
- `http_status` (`int`, nullable)
- `raw_request_ref` (`text`, nullable) -> pointer/key to raw request object
- `raw_response_ref` (`text`, nullable) -> pointer/key to raw response object
- `payload_hash` (`text`, nullable)
- `error_code` (`text`, nullable)
- `error_message` (`text`, nullable)
- `metadata_json` (`jsonb`, nullable)

Primary key:

- (`event_id`)

Uniqueness guard:

- (`run_id`, `event_sequence`) unique

---

## 3) `dx_company_entities_v1` (upsert snapshot)

Current canonical company state for analytics consumption.

Required fields:

- `export_schema_version` (`text`) -> `v1`
- `org_id` (`uuid/text`)
- `company_id` (`uuid/text`)
- `entity_id` (`uuid/text`) -> canonical company entity id
- `canonical_name` (`text`, nullable)
- `canonical_domain` (`text`, nullable)
- `linkedin_url` (`text`, nullable)
- `linkedin_page_id` (`text`, nullable)
- `industry` (`text`, nullable)
- `employee_count` (`int`, nullable)
- `revenue_band` (`text`, nullable)
- `hq_country` (`text`, nullable)
- `enrichment_confidence` (`numeric`, nullable)
- `last_enriched_at` (`timestamptz`, nullable)
- `last_operation_id` (`text`, nullable)
- `last_run_id` (`uuid/text`, nullable)
- `source_priority` (`text`, nullable)
- `record_version` (`bigint/int`) -> monotonic per entity
- `updated_at` (`timestamptz`)

Primary key:

- (`org_id`, `entity_id`)

Upsert rule:

- apply only if incoming `record_version` > existing `record_version`

---

## 4) `dx_person_entities_v1` (upsert snapshot)

Current canonical person state for analytics consumption.

Required fields:

- `export_schema_version` (`text`) -> `v1`
- `org_id` (`uuid/text`)
- `company_id` (`uuid/text`, nullable)
- `entity_id` (`uuid/text`) -> canonical person entity id
- `full_name` (`text`, nullable)
- `first_name` (`text`, nullable)
- `last_name` (`text`, nullable)
- `linkedin_url` (`text`, nullable)
- `title` (`text`, nullable)
- `seniority` (`text`, nullable)
- `department` (`text`, nullable)
- `work_email` (`text`, nullable)
- `email_status` (`text`, nullable)
- `phone_e164` (`text`, nullable)
- `contact_confidence` (`numeric`, nullable)
- `last_enriched_at` (`timestamptz`, nullable)
- `last_operation_id` (`text`, nullable)
- `last_run_id` (`uuid/text`, nullable)
- `record_version` (`bigint/int`) -> monotonic per entity
- `updated_at` (`timestamptz`)

Primary key:

- (`org_id`, `entity_id`)

Upsert rule:

- apply only if incoming `record_version` > existing `record_version`

---

## 5) `dx_entity_snapshots_v1` (optional, append-only SCD)

Historical canonical snapshots for model drift and time-travel analytics.

Required fields:

- `export_schema_version` (`text`) -> `v1`
- `snapshot_id` (`uuid/text`)
- `org_id` (`uuid/text`)
- `entity_type` (`text`) -> `company` | `person`
- `entity_id` (`uuid/text`)
- `record_version` (`bigint/int`)
- `canonical_payload_json` (`jsonb`)
- `captured_at` (`timestamptz`)
- `source_run_id` (`uuid/text`, nullable)

Primary key:

- (`snapshot_id`)

Uniqueness guard:

- (`org_id`, `entity_type`, `entity_id`, `record_version`) unique

---

## Sync Cadence

Default v1 cadence:

- **Micro-batch export**: every 5-15 minutes
- **Daily reconciliation**: once per day (off-peak) for late-arriving rows and drift checks

Backfill strategy:

- replay by `created_at`/`updated_at` windows
- idempotent writes in target (PK + upsert semantics)

---

## Data Quality & Reconciliation

Per-batch checks:

- row count parity by dataset and date window
- checksum/hash parity on stable key columns
- max-lag SLA check (`now - latest_exported_timestamp`)
- null-rate checks on critical fields:
  - company: `canonical_domain`, `canonical_name`
  - person: `full_name` or (`first_name`, `last_name`)
- status distribution anomaly checks for `dx_operation_runs_v1`

Failure handling:

- failed exports route to dead-letter queue/table
- retry with exponential backoff
- unresolved failures are surfaced in operational alerting

---

## Schema Governance

Versioning rules:

- include `export_schema_version` in every dataset
- v1 allows additive columns only
- field removal/rename requires:
  1) publish `v2`,
  2) dual-publish window,
  3) explicit HQ consumer migration completion

Breaking-change policy:

- no in-place breaking changes to active version
- deprecation window minimum: 2 release cycles

---

## Security & Tenancy

- Every row must include `org_id` (and `company_id` where applicable).
- Do not export secrets or provider API keys.
- Raw payload references should point to controlled storage locations; avoid embedding sensitive payload blobs directly unless required and encrypted.

---

## Phase 1 Acceptance Criteria

- `docs/EXPORT_CONTRACT_V1.md` approved and frozen for Phase 1 scope.
- All five datasets have:
  - required fields,
  - key strategy,
  - write semantics (append-only vs upsert),
  - cadence definition.
- Governance policy is documented (`export_schema_version`, additive-only, v2 policy).
- Data quality checks and reconciliation plan are explicitly defined.
- Contract is referenced by architecture docs as the source of truth for HQ export.

---

## Out of Scope for Phase 1

- Building the actual sync pipeline/jobs
- Warehouse physical table DDL implementation
- BI modeling and downstream semantic layer

Those are Phase 2+ implementation tasks, but must adhere to this contract.

