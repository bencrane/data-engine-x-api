# Directive: Client Automation Config, Recurring Schedules, and Entity Associations

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The current architecture already has the core execution lineage model: `orgs -> companies -> blueprints -> submissions -> pipeline_runs -> step_results`, plus canonical entity tables in `entities`. What is missing is the client automation layer that lets a company account store reusable workflow inputs, run those inputs on a schedule, and scope discovered entities back to that client account. This is not a blueprint rewrite. Blueprints stay generic. The new layer stores client-specific input parameters, schedule definitions, and entity-association records that tie resulting entities back to the client company that owns the workflow run.

**Critical architecture rules for this directive:**

- Use existing `ops.companies` as the client account model. Do **not** introduce a new top-level `clients` table.
- Keep blueprints generic. Do **not** duplicate blueprints per client just to store client parameters.
- Keep FastAPI as the owner of database writes and submission creation.
- Trigger.dev may orchestrate recurring evaluation, but it should call FastAPI internal endpoints rather than writing directly to the database.
- Do **not** copy entity data into client-specific tables. The association layer references entity rows; it does not duplicate them.
- Do **not** use this directive to force a broader entity-globalization rewrite. Work with the current repo reality while keeping the association design forward-compatible with the doctrine in `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`.
- Treat the current org-scoped entity tables as an implementation reality to interoperate with, not as the target design to extend further.
- Make the new client-to-entity association layer the forward-compatible client visibility mechanism.
- Do **not** attempt to re-key, de-scope, or globalize the existing entity tables in this workstream.

**Primary use case to optimize for:** a staffing agency onboards, stores target company domains and job-title filters, chooses a generic hiring/discovery blueprint, and the system automatically runs that blueprint on a recurring schedule. The resulting companies, people, and job postings must be visible only within that client company’s account context.

**Planning note about current work:** if you need a concrete example for docs, fixtures, or test payloads, use the client context `Outbound Solutions` with domain `outboundsolutions.com`. Do not assume that org/company already exists in production unless you explicitly verify it.

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/DATA_ENGINE_X_ARCHITECTURE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`
- `/Users/benjamincrane/data-engine-x-api/docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/001_initial_schema.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/006_blueprint_operation_steps.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/007_entity_state.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/010_fan_out.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/013_job_posting_entities.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/014_entity_relationships.sql`
- `/Users/benjamincrane/data-engine-x-api/supabase/migrations/021_schema_split_ops_entities.sql`
- `/Users/benjamincrane/data-engine-x-api/app/database.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/submission_flow.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/entity_state.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/trigger.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/internal.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/tenant_blueprints.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/tenant_flow.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/super_admin_flow.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/entities_v1.py`
- `/Users/benjamincrane/data-engine-x-api/app/main.py`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/internal-api.ts`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/tasks/fmcsa-revocation-daily.ts`
- `/Users/benjamincrane/data-engine-x-api/tests/test_batch_flow.py`
- `/Users/benjamincrane/data-engine-x-api/tests/test_database_schema_routing.py`
- `/Users/benjamincrane/data-engine-x-api/tests/test_entity_state.py`

---

### Deliverable 1: Contract Lock and Design Document

Create `docs/CLIENT_AUTOMATION_CONFIG_SCHEDULE_ASSOCIATION_DESIGN.md`.

This document must lock the architecture before implementation.

It must explicitly answer:

- how client-specific workflow inputs are stored without modifying blueprints
- how recurring schedules are represented
- how due schedules are claimed and executed without duplicate submission creation
- how resulting entities are associated back to the client company
- where each new table belongs (`ops` vs `entities`) and why
- how the design stays compatible with the current implemented schema while respecting the doctrine that entity data should not be duplicated per tenant

Required design decisions:

- use existing `ops.companies` as the client account table
- prefer a DB-backed schedule model plus one recurring Trigger evaluator task over per-client code-registered Trigger schedules
- keep blueprint-specific input parameters in a reusable client config record, not in the blueprint definition itself
- use an explicit association table between client companies and entity IDs instead of relying only on the current `company_id` field on entity tables
- place the client-to-entity association table in `ops`, because it is tenant/client access metadata rather than canonical entity state

The design doc must include:

- proposed new table names
- the purpose of each table
- key columns and uniqueness rules
- schedule idempotency strategy
- how submission `source` and `metadata` will record config/schedule provenance
- how entity list queries will enforce company scoping using the new association layer
- one worked example using `Outbound Solutions` / `outboundsolutions.com`

Hard requirements:

- do not create a new `clients` root table
- do not duplicate entity payloads into client-scoped copies
- do not turn client config into blueprint mutation
- if you conclude that the preferred DB-backed schedule evaluator model is not viable, stop and report before implementing a different scheduler architecture

Commit standalone.

### Deliverable 2: Schema and Management API Layer

Implement the schema and management API for client configs and schedules.

Create or update:

- one or more new migrations in `supabase/migrations/` after inspecting the real latest migration sequence in the repo
- `app/services/company_blueprint_configs.py`
- `app/services/company_blueprint_schedules.py`
- `app/routers/tenant_client_automation.py`
- `app/routers/super_admin_client_automation.py`
- `app/main.py`
- any shared request/response models needed in those router files

Schema requirements:

- create a company-scoped config table for reusable workflow inputs tied to:
  - `org_id`
  - `company_id`
  - `blueprint_id`
- create a schedule table tied to a specific config record
- create a schedule-run or equivalent execution-ledger mechanism if needed for safe due-run claiming and duplicate prevention

Data-model requirements:

- blueprint selection must be a foreign key, not a copied blueprint definition
- client-specific run inputs should be stored as config payload data that can be passed into submissions at runtime
- use typed columns for fields that will be queried operationally, such as active state, schedule state, timezone, run timestamps, and provenance fields
- use JSONB for blueprint-specific variable input payloads rather than trying to normalize every possible blueprint input into columns
- preserve org/company tenancy integrity with the same rigor as existing ops tables

Management API requirements:

- add tenant-scoped endpoints to create, list, get, and update client config records
- add tenant-scoped endpoints to create, list, get, and update schedule records
- add super-admin endpoints for the same surfaces
- keep endpoint style consistent with existing tenant and super-admin CRUD routers

Suggested endpoint families:

- `/api/client-automation/configs/*`
- `/api/client-automation/schedules/*`
- `/api/super-admin/client-automation/configs/*`
- `/api/super-admin/client-automation/schedules/*`

You may refine the exact path suffixes, but keep the surface explicit and consistent with the repo’s existing list/get/create/update patterns.

Commit standalone.

### Deliverable 3: Recurring Schedule Evaluation and Submission Creation

Build the recurring schedule mechanism.

Create or update:

- `trigger/src/tasks/client-automation-scheduler.ts`
- `app/routers/internal.py`
- `app/services/submission_flow.py`
- any new FastAPI service module(s) needed to:
  - claim due schedules
  - create submissions from client config payloads
  - record schedule-run outcomes

Required architecture:

- Trigger.dev runs one recurring scheduler task on a fixed cron
- that task calls FastAPI internal endpoints using the existing internal API auth pattern
- FastAPI evaluates due schedules, claims them safely, creates submissions, and records results

Hard requirements:

- Trigger.dev must not directly write schedule records or submissions to the database
- reuse the existing submission creation flow where possible instead of inventing a second submission system
- scheduled submissions must preserve the generic blueprint model
- scheduled submissions must stamp provenance in `source` and/or `metadata` so you can trace:
  - config ID
  - schedule ID
  - schedule-run ID or equivalent
  - scheduler invocation timestamp

Idempotency requirements:

- evaluator reruns must not create duplicate submissions for the same schedule fire window
- due-schedule claiming must be concurrency-safe enough that overlapping scheduler executions do not double-submit
- if a run fails after claim, the failure must be observable and the schedule must remain recoverable

Commit standalone.

### Deliverable 4: Client-Scoped Entity Association Layer

Implement the company-to-entity association layer and wire it into entity visibility.

Create or update:

- `app/services/company_entity_associations.py`
- one or more new migrations in `supabase/migrations/`
- `app/routers/internal.py`
- `app/services/entity_state.py`
- `app/routers/entities_v1.py`

Association requirements:

- create an explicit association table linking client companies to entities
- the table must not duplicate canonical entity payloads
- it must carry enough lineage to understand how the association was created, at minimum through references such as:
  - `source_submission_id`
  - `source_pipeline_run_id`
  - optional source step/operation metadata if naturally available
- it must support associations for:
  - company entities
  - person entities
  - job posting entities

Important schema-placement judgment:

- this association table is tenant/client scoping metadata, not canonical entity state
- it should live in `ops`, not `entities`
- design it accordingly and justify its schema placement in Deliverable 1

Write-path requirements:

- when a workflow run for a client produces or upserts company/person/job entities, record an association row for that client company
- do this without changing the canonical entity payload model
- keep the association write additive and idempotent

Query-path requirements:

- update the company/person/job entity list endpoints so company-scoped frontend users can be limited through the association layer
- do not rely only on the current entity-table `company_id` field for this new client-automation scoping model
- if timeline/snapshot access needs companion association checks for safe company-scoped visibility, include them if they naturally follow from the implementation

Commit standalone.

### Deliverable 5: Tests and End-to-End Coverage

Add or update tests to cover the new automation layer.

At minimum, cover:

- config create/list/get/update behavior for tenant and/or super-admin surfaces
- schedule create/list/get/update behavior
- schedule due-claim idempotency and duplicate prevention
- scheduled submission creation with correct blueprint/config provenance in metadata
- Trigger scheduler task calling the correct internal FastAPI surface
- entity association record creation for company, person, and job results
- entity list queries respecting association-based scoping for company-scoped users
- schema routing for any new `ops` and `entities` tables

Use or extend:

- `tests/test_batch_flow.py`
- `tests/test_database_schema_routing.py`
- `tests/test_entity_state.py`

Add new tests as needed. Keep the test surface focused on the new automation and association architecture rather than unrelated workflow behavior.

Commit standalone.

---

**What is NOT in scope:** No deployment. No push. No rewrite of the generic blueprint system into client-specific copies. No full global-entity migration. No replacement of existing submission/pipeline lineage. No direct Trigger.dev database writes. No new top-level `clients` table. No frontend implementation.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/CLIENT_AUTOMATION_CONFIG_SCHEDULE_ASSOCIATION_DESIGN.md`, (b) the exact new tables and which schema each landed in, (c) the schedule-evaluation architecture chosen and how duplicate submission prevention works, (d) the new tenant and super-admin endpoint paths, (e) the Trigger task ID and cron used for recurring evaluation, (f) how scheduled submissions record config/schedule provenance, (g) how entity associations are written and queried, (h) every file changed, and (i) anything to flag — especially any tension between current org-scoped entity tables and the longer-term doctrine that entities should be global.
