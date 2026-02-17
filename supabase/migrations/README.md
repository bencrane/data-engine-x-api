# Supabase Migration Manifest

This directory contains the ordered schema migration history for `data-engine-x-api`.

## Run Order

Apply migrations in filename order:

1. `001_initial_schema.sql` - Creates base multi-tenant schema, enums, core tables, tenancy triggers, and `updated_at` trigger function.
2. `002_users_password_hash.sql` - Adds `users.password_hash` for tenant password authentication.
3. `003_api_tokens_user_id.sql` - Adds `api_tokens.user_id` ownership relation and index.
4. `004_steps_executor_config.sql` - Adds legacy generic HTTP executor config columns to `steps`.
5. `005_operation_execution_history.sql` - Adds durable operation history tables (`operation_runs`, `operation_attempts`).
6. `006_blueprint_operation_steps.sql` - Adds operation-native blueprint fields (`operation_id`, `step_config`) and relaxes legacy `step_id` nullability.
7. `007_entity_state.sql` - Adds canonical entity state tables (`company_entities`, `person_entities`) and indexes.
8. `008_companies_domain.sql` - Adds canonical company domain fields and supporting indexes.
9. `009_entity_timeline.sql` - Adds `entity_timeline` table and timeline lineage indexes.
10. `010_fan_out.sql` - Adds fan-out parent/child pipeline run linkage and indexes.

## Run Command

Run each file manually in order:

```bash
psql "$DATA_ENGINE_DATABASE_URL" -f supabase/migrations/00X_*.sql
```

Example:

```bash
psql "$DATA_ENGINE_DATABASE_URL" -f supabase/migrations/006_blueprint_operation_steps.sql
```

## Idempotency Notes

Migrations are written to be re-runnable where possible:

- `CREATE ... IF NOT EXISTS`
- `ADD COLUMN IF NOT EXISTS`
- `DROP TRIGGER IF EXISTS` / guarded trigger recreation where needed

Re-running should still be done intentionally and with migration history awareness.

## Ordering Dependencies

- `001` must run first (defines base tables/functions used by all later migrations).
- `005` depends on `001` for `orgs`, `companies`, `users`, and `update_updated_at_column()`.
- `006` depends on `001` for `blueprint_steps` and `step_results`.
- `007` depends on `001` for `orgs`, `companies`, `pipeline_runs`, and `update_updated_at_column()`.
- `009` depends on `001` for base tenancy/run tables and `update_updated_at_column()`.
- `010` depends on `001` for `pipeline_runs` and base table definitions.
