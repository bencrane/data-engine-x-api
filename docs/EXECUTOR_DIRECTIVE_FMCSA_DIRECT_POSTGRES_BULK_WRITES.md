# Directive: FMCSA Bulk Ingestion Direct Postgres Write Path

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The existing data-engine-x architecture correctly routes normal writes through FastAPI to the Supabase PostgREST client. That remains the right pattern for normal workflow operations, entity upserts, confirmed writes, and lineage-sensitive application paths. FMCSA bulk ingestion is a different workload: large batches, many thousands of rows, and multiple scheduled feeds running under concurrency. In that path, PostgREST is the bottleneck producing timeouts, `500`s, and `502`s under load. This directive creates a scoped exception for FMCSA bulk ingestion only: keep the Trigger task contracts and internal FastAPI endpoint contracts unchanged, but replace the underlying FastAPI persistence implementation from PostgREST to direct Postgres writes using `psycopg` and `DATABASE_URL`.

**Current contract to preserve:**

- Trigger tasks still call the same FastAPI internal endpoints.
- FastAPI internal endpoints still receive the same JSON payload shape via `InternalUpsertFmcsaDailyDiffBatchRequest`.
- FMCSA service modules still build typed rows plus metadata through the existing service layer.
- The only architectural change is inside the FMCSA persistence layer reached through `app/services/fmcsa_daily_diff_common.py`.

**Internal API request/response shape to preserve:**

- Request fields:
  - `feed_name`
  - `feed_date`
  - `download_url`
  - `source_file_variant`
  - `source_observed_at`
  - `source_task_id`
  - `source_schedule_id`
  - `source_run_metadata`
  - `records` with `row_number`, `raw_values`, and `raw_fields`
- Response behavior:
  - same endpoint paths
  - same FastAPI response envelope shape
  - same returned summary semantics: `feed_name`, `table_name`, `feed_date`, `rows_received`, `rows_written`

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `/Users/benjamincrane/data-engine-x-api/docs/FMCSA_TIMEOUT_FAILURE_DIAGNOSIS_2026-03-11.md`
- `/Users/benjamincrane/data-engine-x-api/app/config.py`
- `/Users/benjamincrane/data-engine-x-api/app/database.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/internal.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/fmcsa_daily_diff_common.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/operating_authority_histories.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/operating_authority_revocations.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/insurance_policies.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/insurance_policy_filings.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/insurance_policy_history_events.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/carrier_registrations.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/process_agent_filings.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/insurance_filing_rejections.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/carrier_safety_basic_measures.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/carrier_safety_basic_percentiles.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/carrier_inspection_violations.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/carrier_inspections.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/motor_carrier_census_records.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/commercial_vehicle_crashes.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/vehicle_inspection_units.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/vehicle_inspection_special_studies.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/vehicle_inspection_citations.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/out_of_service_orders.py`
- `/Users/benjamincrane/data-engine-x-api/requirements.txt`
- `/Users/benjamincrane/data-engine-x-api/tests/test_fmcsa_daily_diff_persistence.py`

---

### Deliverable 1: Replace FMCSA PostgREST Bulk Upserts with Direct Postgres Writes

Replace the FMCSA bulk write implementation currently centered in `app/services/fmcsa_daily_diff_common.py`.

Requirements:

- remove the FMCSA bulk ingestion dependency on `get_supabase_client().table(...).upsert(...).execute()`
- use `psycopg` with the existing `DATABASE_URL` setting from `app.config.get_settings()`
- keep the change scoped to the FMCSA bulk ingestion path only
- preserve the current service API used by all FMCSA service modules that call `upsert_fmcsa_daily_diff_rows(...)`
- preserve the current internal FastAPI endpoint contracts in `app/routers/internal.py`
- preserve the conflict key semantics currently used by the bulk path: `feed_date, source_feed_name, row_position`
- preserve the same metadata columns and raw row preservation behavior
- preserve `rows_received` and `rows_written` response semantics

Implementation decision:

- choose the best direct Postgres bulk strategy for this workload using either:
  - `executemany` with parameterized upsert SQL, or
  - `COPY` into a staging/temp table plus merge/upsert, or
  - another robust direct-Postgres bulk pattern if you can justify it

Hard requirements:

- all SQL must be parameterized; do not interpolate row values into SQL strings
- target the correct schema-qualified FMCSA tables in `entities`
- use a single transaction per batch write
- preserve idempotent same-`feed_date` reruns through the existing unique key semantics
- preserve `created_at`/`updated_at` behavior appropriately on insert vs conflict-update
- preserve JSONB writes for `source_run_metadata` and `raw_source_row`
- surface real database failures; do not swallow them or convert them into fake success
- do not change non-FMCSA services to use direct Postgres
- do not turn this into a new global rule for the rest of the system

You may create a dedicated helper module for FMCSA direct Postgres writes if that makes the implementation cleaner, but keep the design obviously scoped to FMCSA bulk ingestion and not a generic rewrite of the app’s database layer.

Commit standalone.

### Deliverable 2: Regression Coverage for the New Bulk Write Path

Update tests to validate the direct Postgres FMCSA write path without changing the endpoint contracts.

At minimum, cover:

- a representative FMCSA service still returns the same summary shape after persistence
- same-day rerun behavior remains idempotent on `feed_date, source_feed_name, row_position`
- different-`feed_date` snapshots still coexist correctly
- typed business columns, metadata columns, and raw row JSON payloads are all written correctly
- conflict-update behavior updates the expected columns while preserving insert-only semantics where appropriate
- failures from the direct Postgres layer surface as real failures rather than silent success
- internal FMCSA endpoint request/response contracts remain unchanged

Test strategy requirements:

- replace the current fake Supabase-client assumptions in FMCSA persistence tests with an appropriate direct-Postgres testing strategy
- you may use mocking around the connection/cursor layer, or a tighter integration-style test harness if it is already supported locally, but do not make the test suite depend on an unscoped production database
- keep the tests focused on FMCSA persistence behavior rather than broad database abstractions

Commit standalone.

---

**What is NOT in scope:** No Trigger.dev task contract changes. No FastAPI internal endpoint payload changes. No non-FMCSA write paths moving off PostgREST. No redesign of normal entity/workflow persistence. No schema renames. No table-concept changes that violate `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`. No deployment. No push. No changes to `trigger/src/tasks/run-pipeline.ts`. No broad database abstraction overhaul for the whole repo.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the direct Postgres bulk-write strategy chosen and why, (b) every file changed, (c) how `DATABASE_URL` is now used in the FMCSA persistence path, (d) how the upsert conflict/update logic is implemented, (e) how JSONB and timestamps are handled, (f) what tests were changed or added and what they prove, and (g) anything to flag — especially any remaining FMCSA bottlenecks that still sit above the database write layer.
