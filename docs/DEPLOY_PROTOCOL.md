# Deploy Protocol

**Last updated:** 2026-03-18T19:00:00Z

Deploy ordering, common commands, and migration reference for `data-engine-x-api`.

## Common Commands

```bash
# API tests
pytest

# Trigger.dev local runtime
cd trigger && npx trigger.dev@latest dev

# Run API locally with Doppler-injected env
doppler run -- uvicorn app.main:app --reload

# Run tests with Doppler-injected env
doppler run -- pytest
```

## Deploy Protocol

**Deploy Railway FIRST, Trigger.dev SECOND. Never simultaneously.**

```bash
# Step 1: Push to main (Railway auto-deploys)
git push origin main
# WAIT 1-2 minutes for Railway deploy to complete

# Step 2: Deploy Trigger.dev (only after Railway is live)
cd trigger && npx trigger.dev@4.4.3 deploy
```

Trigger.dev calls FastAPI internal endpoints. If Trigger.dev deploys before Railway, new endpoint calls fail silently — pipeline succeeds but data doesn't persist to dedicated tables. See `docs/troubleshooting-fixes/` for incidents.

## Production Database Access

**Critical:** `$DATABASE_URL` is injected by Doppler at runtime. You must wrap commands in `bash -c` so the variable expands *inside* Doppler's environment, not in your outer shell.

**Wrong** — `$DATABASE_URL` expands before Doppler runs (empty or wrong value):

```bash
doppler run -p data-engine-x-api -c prd -- psql "$DATABASE_URL" -c "SELECT 1;"
```

**Right** — `bash -c` ensures `$DATABASE_URL` resolves after Doppler injects env vars:

```bash
# Single query
doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "SELECT 1;"'

# Multi-line query
doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_schema = '"'"'entities'"'"'
ORDER BY table_name;
"'

# Verify which env vars Doppler injects
doppler run -p data-engine-x-api -c prd -- bash -c 'printenv DATABASE_URL | sed "s/\(:[^:@]*\)@/:***@/"'
```

Without the `bash -c` wrapper, queries may silently connect to a different database (if `DATABASE_URL` is set in your local shell) or fail with a connection error. This caused a false-negative incident on 2026-03-18 where production tables appeared missing.

## Database / Migrations

Migration order:

1. `001_initial_schema.sql`
2. `002_users_password_hash.sql`
3. `003_api_tokens_user_id.sql`
4. `004_steps_executor_config.sql`
5. `005_operation_execution_history.sql`
6. `006_blueprint_operation_steps.sql`
7. `007_entity_state.sql`
8. `008_companies_domain.sql`
9. `009_entity_timeline.sql`
10. `010_fan_out.sql`
11. `011_entity_timeline_submission_lookup.sql`
12. `012_entity_snapshots.sql`
13. `013_job_posting_entities.sql`
14. `014_entity_relationships.sql`
15. `015_icp_job_titles.sql`
16. `016_intel_briefing_tables.sql`
17. `017_icp_title_extraction.sql`
18. `018_alumnigtm_persistence.sql`
19. `019_company_ads.sql`
20. `020_salesnav_prospects.sql`
21. `021_schema_split_ops_entities.sql`
22. `022_fmcsa_top5_daily_diff_tables.sql`
23. `023_fmcsa_snapshot_history_tables.sql`
24. `024_fmcsa_sms_tables.sql`
25. `025_fmcsa_remaining_csv_export_tables.sql`
26. `026_client_automation_and_entity_associations.sql`
27. `027_fmcsa_snapshot_replace_indexes.sql`
28. `028_leads_query_function.sql`
29. `029_lists.sql`
30. `030_sam_gov_entities.sql`
31. `031_usaspending_contracts.sql`
32. `032_sba_7a_loans.sql`
33. `033_mv_federal_contract_leads.sql`
34. `034_mv_federal_contract_leads_agency_first_time.sql`
35. `035_fmcsa_carrier_signals.sql`
36. `036_mv_fmcsa_authority_grants.sql`
37. `037_mv_fmcsa_insurance_cancellations.sql`
38. `038_mv_usaspending_analytical.sql` — USASpending typed base MV + first-contract MV (**heavy: 10-30 min on 14.6M rows, run during low-traffic window**)
39. `039_mv_fmcsa_analytical.sql` — FMCSA latest census, safety percentiles, crash counts, master carrier MVs (**heavy: run during low-traffic window**)
40. `040_analytical_missing_indexes.sql` — supplemental composite indexes for USASpending, SAM.gov, SBA
41. `041_enigma_brand_discoveries.sql` — Enigma brand discoveries + location enrichments tables (2 new tables in `entities` schema with indexes)
42. `042_mv_analytical_expansion.sql` — 8 new analytical MVs: SAM.gov typed base + state/NAICS aggregates, SBA typed base + state aggregate, SAM×USASpending cross-vertical bridge, FMCSA latest insurance policies snapshot, FMCSA new carriers 90d (**heavy: ~30-60 min, run during low-traffic window**)
