# Directive: Priority 4 — Schema Split (ops and entities)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** All application tables currently live in the `public` schema. The system has two conceptually distinct domains: orchestration/pipeline state (`ops`) and canonical entity intelligence (`entities`). Separating them into named schemas clarifies ownership, makes access control possible in the future, and establishes the boundary needed for the global entity data layer. This split must happen before more dedicated workflows are built, because every new workflow would need to be redirected after the fact.

This is a migration of existing tables with existing data. Nothing is rebuilt. Data is preserved. The application continues to work against the same database — tables just move into schema-qualified locations.

---

## Schema Assignment

### `ops` schema

These are orchestration, tenancy, and pipeline state tables:

- `orgs`
- `companies`
- `users`
- `api_tokens`
- `super_admins`
- `steps`
- `blueprints`
- `blueprint_steps`
- `submissions`
- `pipeline_runs`
- `step_results`
- `operation_runs`
- `operation_attempts`

### `entities` schema

These are canonical entity records, enrichment output, and dedicated intelligence tables:

- `company_entities`
- `person_entities`
- `job_posting_entities`
- `entity_timeline`
- `entity_snapshots`
- `entity_relationships`
- `icp_job_titles`
- `extracted_icp_job_title_details`
- `company_intel_briefings`
- `person_intel_briefings`
- `gemini_icp_job_titles`
- `company_customers`
- `company_ads`
- `salesnav_prospects`

---

## Architectural Constraints

1. **Data must be preserved.** This is `ALTER TABLE ... SET SCHEMA`, not drop-and-recreate. The executor decides the safest migration approach, but zero data loss is a hard requirement.

2. **Foreign keys that cross schemas must remain intact.** Several `entities` tables reference `ops` tables (e.g., `source_submission_id`, `source_pipeline_run_id`). Cross-schema foreign keys work within the same Postgres database. Verify they survive the move.

3. **All application code must use schema-qualified references after the split.** Every FastAPI query, internal endpoint, service function, and Trigger.dev workflow utility that touches these tables must be updated. The application must not rely on `search_path` falling back to `public` — references must be explicit.

4. **The `public` schema should be empty of application tables after the migration.** Postgres system tables and extensions can remain in `public`, but none of the 27 application tables listed above should remain there.

5. **Existing indexes, triggers, constraints, and RLS policies must be preserved.** Moving a table to a new schema should carry these along, but the executor must verify.

6. **Entity tables keep `org_id` for now.** `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` Principle 3 states entities are global, not tenant-scoped. Removing `org_id` from entity tables is a separate future directive. This directive only moves tables into schemas.

7. **The company enrichment workflow and shared utilities from the Priority 2 directive must work after the split.** Those modules call FastAPI internal endpoints which execute queries — the FastAPI queries are what need updating, not the Trigger.dev HTTP calls. But verify the full path works.

8. **Deploy protocol applies.** This directive does not include deployment. When deployed: Railway first (to update FastAPI queries), Trigger.dev second. The Trigger.dev workflows call FastAPI endpoints — as long as FastAPI is updated first, the workflows don't need to know about schema names.

9. **Supabase Python client may not support schema-qualified references natively.** The codebase uses the Supabase Python client, which has `.table("table_name")` syntax. This syntax may not support `schema.table_name` references out of the box. The executor must investigate how the Supabase client handles non-`public` schemas and determine the right approach — whether that is a client-level schema selector, explicit per-query schema targeting, raw SQL, RPC helpers, or a tightly-scoped compatibility layer. This is a real technical constraint you will hit, not a hypothetical.

10. **Do not satisfy this directive by relying only on `search_path`.** A connection-level or role-level `search_path` change may be used as a temporary compatibility aid if absolutely required by a library, but it does not satisfy the directive on its own. The application code must still target the intended schema explicitly at each table access path.

11. **Account for the known `company_ads` production drift.** `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` and `docs/DATA_ENGINE_X_ARCHITECTURE.md` both state that production did not have `company_ads` when the audit was taken because migration `019_company_ads.sql` had not reached prod. Priority 1 cleanup exists to correct that. Do not assume every target database already has `public.company_ads`. If the target environment still lacks that table, stop and report the sequencing issue instead of inventing a new replacement table in this directive.

---

## Existing Code to Read Before Starting

- `CLAUDE.md` — project conventions, production state, deploy protocol
- `docs/STRATEGIC_DIRECTIVE.md` — mandatory strategy guardrails before architecture work
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — entity design rules
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — current architecture, known problems, and schema-split implications
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — production table inventory and row counts
- `docs/EXECUTOR_DIRECTIVE_CLEAN_STALE_PRODUCTION_STATE.md` — confirms the pre-existing `company_ads` production drift and the expected sequencing dependency
- `supabase/migrations/001_initial_schema.sql`
- `supabase/migrations/002_users_password_hash.sql`
- `supabase/migrations/003_api_tokens_user_id.sql`
- `supabase/migrations/004_steps_executor_config.sql`
- `supabase/migrations/005_operation_execution_history.sql`
- `supabase/migrations/006_blueprint_operation_steps.sql`
- `supabase/migrations/007_entity_state.sql`
- `supabase/migrations/008_companies_domain.sql`
- `supabase/migrations/009_entity_timeline.sql`
- `supabase/migrations/010_fan_out.sql`
- `supabase/migrations/011_entity_timeline_submission_lookup.sql`
- `supabase/migrations/012_entity_snapshots.sql`
- `supabase/migrations/013_job_posting_entities.sql`
- `supabase/migrations/014_entity_relationships.sql`
- `supabase/migrations/015_icp_job_titles.sql`
- `supabase/migrations/016_intel_briefing_tables.sql`
- `supabase/migrations/017_icp_title_extraction.sql`
- `supabase/migrations/018_alumnigtm_persistence.sql`
- `supabase/migrations/019_company_ads.sql`
- `supabase/migrations/020_salesnav_prospects.sql`
- `app/database.py` — database client construction and any schema/search-path abstraction
- `app/auth/dependencies.py` — tenant auth paths that query ops tables
- `app/auth/super_admin.py` — super-admin auth paths that query ops tables
- `app/routers/auth.py`
- `app/routers/internal.py`
- `app/routers/execute_v1.py`
- `app/routers/entities_v1.py`
- `app/routers/tenant_flow.py`
- `app/routers/tenant_companies.py`
- `app/routers/tenant_users.py`
- `app/routers/tenant_steps.py`
- `app/routers/tenant_blueprints.py`
- `app/routers/super_admin_auth.py`
- `app/routers/super_admin_api.py`
- `app/routers/super_admin_flow.py`
- `app/routers/coverage_v1.py`
- `app/services/submission_flow.py`
- `app/services/operation_history.py`
- `app/services/registry.py`
- `app/services/entity_state.py`
- `app/services/entity_timeline.py`
- `app/services/entity_relationships.py`
- `app/services/icp_job_titles.py`
- `app/services/company_intel_briefings.py`
- `app/services/person_intel_briefings.py`
- `app/services/gemini_icp_job_titles.py`
- `app/services/company_customers.py`
- `app/services/company_ads.py`
- `app/services/salesnav_prospects.py`
- `app/services/change_detection.py`
- `app/services/alumni_gtm_service.py`
- `trigger/src/tasks/run-pipeline.ts`
- `trigger/src/tasks/company-enrichment.ts`
- `trigger/src/workflows/internal-api.ts`
- `trigger/src/workflows/persistence.ts`
- `trigger/src/workflows/company-enrichment.ts`
- `trigger/src/workflows/operations.ts`
- `trigger/src/workflows/lineage.ts`

---

## Deliverable 1: Migration SQL

Create a new migration file in `supabase/migrations/` (next sequential number) that:

- Creates the `ops` and `entities` schemas
- Moves each table to its assigned schema
- Preserves all data, indexes, triggers, constraints, foreign keys, and RLS policies

The executor decides the migration strategy (e.g., `ALTER TABLE SET SCHEMA`, transactional wrapping, ordering to respect FK dependencies). The migration must be safe to run against production with live data.

Before writing the migration, explicitly inventory which existing tables, indexes, triggers, policies, and cross-table constraints exist today from the current migration set. Do not assume `ALTER TABLE ... SET SCHEMA` automatically makes every dependent object land where you expect without verification.

If the target database still does not contain `public.company_ads`, do not paper over that drift in this directive. Stop and report that Priority 1 sequencing has not been completed in the target environment.

Commit standalone.

---

## Deliverable 2: Update FastAPI Application Code

Update all Python code that references the moved tables to use schema-qualified table names. This includes:

- All routers (`internal.py`, `execute_v1.py`, `entities_v1.py`, super-admin, tenant, auth, batch)
- All service modules (`entity_state.py`, `entity_timeline.py`, and any others that issue SQL)
- Any raw SQL queries, ORM references, or table name strings

The executor should search the codebase systematically for every reference to the 27 table names and update them. Do not rely on grep for just the table name — check for query patterns, string interpolation, helper abstractions, auth dependencies, service modules, and any code that constructs Supabase table access dynamically.

This deliverable includes the Supabase access layer itself. If `app/database.py` or a shared query helper must change to make explicit schema targeting possible, do that here. Do not leave a mixture of old `public` assumptions and new schema-qualified call sites.

Commit standalone.

---

## Deliverable 3: Update Trigger.dev Code

Update the shared workflow utilities and the company enrichment workflow from Priority 2 if they contain any direct table references. The Trigger.dev code primarily calls FastAPI endpoints (which handle the SQL), so this deliverable may be minimal — but verify and update anything that references table names directly or assumes `public` in payloads, tests, or persistence helpers.

Also verify that `run-pipeline.ts` does not contain direct SQL or table references that would break. It calls FastAPI via HTTP, so it likely does not — but confirm.

Commit standalone.

---

## Deliverable 4: Verification

Verify the migration and code changes are correct:

- Row counts for all 27 tables match the pre-migration counts in the target database. Use `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` as the production baseline, but still count before and after the migration for exact comparison in the environment you test against.
- All indexes exist in the new schemas
- All foreign keys are intact (especially cross-schema FKs between `entities` and `ops`)
- All triggers are intact
- All RLS policies still exist on the moved tables
- `public` schema contains no application tables
- FastAPI tests pass (`pytest`)
- No hardcoded `public.table_name` references remain in the codebase
- No moved-table access path still depends on an implicit fallback to `public`

Commit standalone (if any fixes are needed from verification).

---

## What is NOT in scope

- No removal of `org_id` from entity tables (future directive)
- No changes to table structure, columns, or data types
- No deploy commands
- No changes to Doppler/Railway/Trigger.dev configuration
- No changes to the auth model
- No new endpoints or API surface changes
- No backfill of broken dedicated tables (`company_customers`, `gemini_icp_job_titles`, `salesnav_prospects`)
- No “fix” that works only by setting a global `search_path` and leaving table references implicit

## Commit convention

Each deliverable is one commit. Do not push.

## Deploy protocol reminder

When this work is eventually deployed: Railway first (FastAPI code with schema-qualified queries must be live before anything else), wait for it to be live, then Trigger.dev second. The migration SQL must be run against production before either deploy — coordinate with the chief agent on sequencing.

## When done

Report back with:
(a) Migration file path and the approach used (ALTER TABLE SET SCHEMA, transaction strategy, FK ordering)
(b) Full list of files changed in Deliverable 2 with count of query references updated per file
(c) Whether Deliverable 3 required any changes (and which files if so)
(d) Pre- and post-migration row counts for all 27 tables
(e) Confirmation that all indexes, FKs, triggers, and RLS policies survived the move
(f) Confirmation that `public` schema contains no application tables
(g) Test results
(h) Anything to flag — edge cases, cross-schema FK concerns, Supabase client schema-targeting constraints, `company_ads` sequencing dependency, search_path considerations, or deployment sequencing risks
