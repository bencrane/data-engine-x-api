# Operational Reality Check

**Last updated:** 2026-03-18T23:59:00Z

## Post-Audit Updates (2026-03-18, end of day)

This section documents what changed after the initial 06:30 UTC audit. Row counts in the sections below reflect the 06:30 UTC state unless noted otherwise.

### Migrations Applied After Initial Audit

Migrations 036–041 were applied to production during the day:

- **036** (`mv_fmcsa_authority_grants`): materialized view created. Was listed as missing in the "Missing Expected Tables" section below — that entry is now stale.
- **037** (`mv_fmcsa_insurance_cancellations`): materialized view created. Was listed as missing — now stale.
- **038** (`mv_usaspending_contracts_typed`, `mv_usaspending_first_contracts`): two USASpending analytical materialized views created. `mv_usaspending_contracts_typed` covers 14.6M rows with typed column casts. `mv_usaspending_first_contracts` covers 133K rows (first contract per recipient).
- **039** (four FMCSA analytical MVs): `mv_fmcsa_latest_census` (2.58M rows), `mv_fmcsa_safety_percentiles` (36K rows), `mv_fmcsa_crash_counts` (40K rows), `mv_fmcsa_carrier_master` (2.58M rows). Test feed rows were deleted from `motor_carrier_census_records` and `commercial_vehicle_crashes` tables — row counts in the audit sections below may be slightly overstated.
- **040** (supplemental indexes): composite indexes added to `usaspending_contracts`, `sam_gov_entities`, `sba_7a_loans` for analytical query performance. No row count changes.
- **041** (`enigma_brand_discoveries`, `enigma_location_enrichments`): two new tables in `entities` schema. Both currently have 0 rows (tables newly created, no operations have been run against production yet).

### Bug Fixes

- **Super-admin auth on entity endpoints (fixed):** `/api/v1/entities/companies` and `/api/v1/entities/persons` previously used `Depends(get_current_auth)` which blocked super-admin API key with 401. Both now use `Depends(_resolve_flexible_auth)`. Super-admin can query these endpoints by passing `org_id` in the request body, consistent with all other entity query endpoints. Noted as Auth Gap #1 in `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — now resolved.
- **`run-pipeline.ts` `internalPost()` headers (fixed):** The generic `internalPost()` function was not sending `x-internal-org-id` or `x-internal-company-id` headers, unlike the `InternalApiClient` class used by dedicated workflows. Fixed — `internalPost()` now sets both headers from the pipeline payload. The existing behavior of passing org_id in the request body was preserved for backward compatibility.

### New Operations Added

15 new Enigma operations were wired into `/api/v1/execute`, bringing total Enigma coverage to 17 operations (2 pre-existing + 15 new). All 15 new operations have 0 `operation_runs` rows in production (never called). Operation IDs:

`company.search.enigma.brands`, `company.search.enigma.aggregate`, `company.search.enigma.person`, `company.enrich.enigma.legal_entities`, `company.enrich.enigma.address_deliverability`, `company.enrich.enigma.technologies`, `company.enrich.enigma.industries`, `company.enrich.enigma.affiliated_brands`, `company.enrich.enigma.marketability`, `company.enrich.enigma.activity_flags`, `company.enrich.enigma.bankruptcy`, `company.enrich.enigma.watchlist`, `person.search.enigma.roles`, `person.enrich.enigma.profile`, `company.verify.enigma.kyb`.

### Standalone Execute Persistence

`POST /api/v1/execute` now accepts `persist: bool = False`. When `persist=true`, the endpoint attempts entity state upsert and dedicated table writes and returns a `persistence` status field in the response. Errors are surfaced, not swallowed. `app/services/persistence_routing.py` implements a `DEDICATED_TABLE_REGISTRY` mapping 11 operation IDs to write functions. `_finalize_execute_response()` was created and replaced all 93 dispatch branch endings in `execute_v1.py`. This addresses Risk #1 from `docs/PERSISTENCE_MODEL.md` for standalone execute calls.

### Row Counts Not Re-Verified

Row counts in the audit sections below reflect the 06:30 UTC state. They have NOT been re-verified after migrations 036–041 were applied. To get current counts:

```bash
doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM entities.mv_fmcsa_authority_grants;"'
```

---

As of `2026-03-18`.

This report is based on:

- Live production SQL run against the production `DATABASE_URL` via `doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "..."'`.
- Live code in `app/routers/execute_v1.py`, `trigger/src/tasks/run-pipeline.ts`, `app/routers/fmcsa_v1.py`, and the repo migrations under `supabase/migrations/`.

## Executive Summary

Production has completed the schema split. Application tables now live in `ops` (orchestration) and `entities` (domain data) schemas. The `public` schema contains only a single test table.

Core orchestration is unchanged since March 10 — no new submissions, pipeline runs, or step results have been created. All previously stuck `running` pipeline runs and step results have resolved (to `failed` or `skipped`).

The entity layer has grown massively:

- `company_entities`: `88` → `45,679` (Clay ingestion via `external.ingest.clay.find_companies`)
- `person_entities`: `503` → `2,116` (Clay ingestion via `external.ingest.clay.find_people`)
- `entity_snapshots`: `93` → `6,407`
- `entity_relationships`: `0` → `1,892` (now populated — was broken in March 10)

FMCSA infrastructure is fully deployed with 18 canonical tables containing `~75.8M` total rows, all with data as recent as `2026-03-17`.

Federal data infrastructure is new: `sam_gov_entities` (`867,137`), `sba_7a_loans` (`356,375`), `usaspending_contracts` (`14,665,610`), and `mv_federal_contract_leads` materialized view (`1,340,862`).

The previously broken auto-persist paths (`company_customers`, `gemini_icp_job_titles`, `salesnav_prospects`) remain broken with `0` rows. `company_ads` now exists as a table but still has `0` rows. `fmcsa_carrier_signals` exists but has `0` rows.

Two FMCSA analytics materialized views (`mv_fmcsa_authority_grants`, `mv_fmcsa_insurance_cancellations`) do not exist in production despite having repo migrations (036, 037).

## Changes Since 2026-03-10

### Submissions / Pipeline Runs / Step Results

- No new submissions, pipeline runs, or step results since March 10. Counts unchanged: `48` submissions, `837` pipeline runs, `3283` step results.
- `1` submission changed: `queued` → `failed` (was `30` failed + `17` completed + `1` queued; now `31` failed + `17` completed).
- `8` stuck `running` pipeline runs all resolved to `failed` (was `679` succeeded + `150` failed + `8` running; now `679` succeeded + `158` failed + `0` running).
- `7` stuck `running` step results resolved to `failed` (was `150` failed; now `157`).
- `190` `queued` step results resolved to `skipped` (was `990` skipped; now `1180`).

### Schema Changes

- Schema split completed: `ops` and `entities` schemas now live. All application tables moved from `public`.
- `public` schema no longer contains application tables — only `temp_test_companies`.
- `reference` schema exists with `countries` table.
- `pgbouncer` schema exists (connection pooling).

### New Tables

- `entities.company_ads` — now exists (was missing in March 10), `0` rows.
- 18 FMCSA canonical tables in `entities` schema — all populated with `~75.8M` total rows.
- `entities.fmcsa_carrier_signals` — exists, `0` rows.
- `entities.sam_gov_entities` — `867,137` rows (latest: `2026-03-16`).
- `entities.sba_7a_loans` — `356,375` rows (latest: `2026-03-16`).
- `entities.usaspending_contracts` — `14,665,610` rows (latest: `2026-03-17`).
- `entities.mv_federal_contract_leads` — materialized view, `1,340,862` rows.

### Missing Expected Tables

- `entities.mv_fmcsa_authority_grants` — migration 036 exists in repo, table does not exist in production.
- `entities.mv_fmcsa_insurance_cancellations` — migration 037 exists in repo, table does not exist in production.

### Entity Table Growth

| Table | March 10 | March 18 | Delta |
|---|---:|---:|---:|
| `company_entities` | 88 | 45,679 | +45,591 |
| `person_entities` | 503 | 2,116 | +1,613 |
| `entity_snapshots` | 93 | 6,407 | +6,314 |
| `entity_relationships` | 0 | 1,892 | +1,892 |
| `entity_timeline` | 4,345 | 4,345 | 0 |

### Previously Broken Tables

- `entity_relationships`: **improved** — `0` → `1,892` rows (all `person` → `works_at` → `company` relationships).
- `company_ads`: **improved** — table now exists (was missing), but still `0` rows.
- `company_customers`: unchanged, still `0` rows.
- `gemini_icp_job_titles`: unchanged, still `0` rows.
- `salesnav_prospects`: unchanged, still `0` rows.

### New Data Paths

- Clay ingestion operations: `external.ingest.clay`, `external.ingest.clay.find_companies`, `external.ingest.clay.find_people` — responsible for the massive entity growth.
- FMCSA feed ingestion — 18 tables populated by Trigger.dev scheduled tasks.
- Federal data ingestion — SAM.gov, SBA 7(a), USAspending.

### Migrations

- `17` new migrations since March 10 (021–037), including schema split, FMCSA tables, federal data tables, and materialized views.

## 1. What's Actually Running?

### Live Schema Reality

Production now has application tables split across two schemas:

- `ops` — orchestration tables (submissions, pipeline_runs, step_results, operation_runs, etc.)
- `entities` — domain data tables (company_entities, person_entities, FMCSA tables, federal data, etc.)

Other schemas present:

- `public` — contains only `temp_test_companies`
- `reference` — contains `countries`
- `pgbouncer` — connection pooling

### Row Counts

#### Ops Schema

| Table | Rows |
|---|---:|
| `ops.submissions` | 48 |
| `ops.pipeline_runs` | 837 |
| `ops.step_results` | 3,283 |
| `ops.operation_runs` | 1,899 |
| `ops.operation_attempts` | 1,846 |
| `ops.orgs` | 5 |
| `ops.companies` | 5 |
| `ops.users` | 4 |
| `ops.super_admins` | 7 |
| `ops.api_tokens` | 3 |
| `ops.steps` | 1 |
| `ops.blueprints` | 16 |
| `ops.blueprint_steps` | 73 |

#### Entities Schema — Core

| Table | Rows |
|---|---:|
| `entities.company_entities` | 45,679 |
| `entities.person_entities` | 2,116 |
| `entities.job_posting_entities` | 1 |
| `entities.entity_timeline` | 4,345 |
| `entities.entity_snapshots` | 6,407 |
| `entities.entity_relationships` | 1,892 |
| `entities.icp_job_titles` | 156 |
| `entities.company_intel_briefings` | 3 |
| `entities.person_intel_briefings` | 1 |
| `entities.gemini_icp_job_titles` | 0 |
| `entities.company_customers` | 0 |
| `entities.company_ads` | 0 |
| `entities.salesnav_prospects` | 0 |
| `entities.extracted_icp_job_title_details` | 0 |
| `entities.fmcsa_carrier_signals` | 0 |

#### Entities Schema — Federal Data

| Table | Rows |
|---|---:|
| `entities.sam_gov_entities` | 867,137 |
| `entities.sba_7a_loans` | 356,375 |
| `entities.usaspending_contracts` | 14,665,610 |

#### Entities Schema — Materialized Views

| View | Rows |
|---|---:|
| `entities.mv_federal_contract_leads` | 1,340,862 |

### `submissions`

- Total rows: `48`
- Status breakdown:

| Status | Count |
|---|---:|
| `failed` | 31 |
| `completed` | 17 |

- Most recent submission:

| id | org | company | blueprint | status | source | created_at |
|---|---|---|---|---|---|---|
| `e87a29e9-e231-41f4-8cdc-e288656435b8` | `AlumniGTM` | `global` | `AlumniGTM Prospect Discovery v1` | `failed` | `api_v1_batch` | `2026-03-04 03:03:11+00` |

### `pipeline_runs`

- Total rows: `837`

| Status | Count |
|---|---:|
| `succeeded` | 679 |
| `failed` | 158 |

- No `running` pipeline runs (all 8 previously stuck runs resolved to `failed`).
- Most recent pipeline run:

| id | submission_id | org | company | status | trigger_run_id | parent_pipeline_run_id | created_at |
|---|---|---|---|---|---|---|---|
| `654486ba-227d-49f1-81ee-c3dc0b712df8` | `e87a29e9-...` | `AlumniGTM` | `global` | `succeeded` | `run_cmmbgdcoob99h0okbr78gfpl1` | `0b80d964-...` | `2026-03-04 03:04:04+00` |

### `step_results`

- Total rows: `3,283`

| Status | Count |
|---|---:|
| `succeeded` | 1,946 |
| `skipped` | 1,180 |
| `failed` | 157 |

- No `running` or `queued` step results (all previously stuck results resolved).
- Most recent step result:

| id | pipeline_run_id | submission_id | step_position | status | created_at |
|---|---|---|---:|---|---|
| `0d443927-...` | `654486ba-...` | `e87a29e9-...` | 2 | `succeeded` | `2026-03-04 03:04:04+00` |

### `operation_runs` and `operation_attempts`

- `operation_runs`: `1,899`
- `operation_runs` failed: `111`
- `operation_runs` non-failed: `1,788`
- Most recent `operation_run`:

| operation_id | status | created_at |
|---|---|---|
| `person.search.sales_nav_url` | `failed` | `2026-03-04 03:34:46+00` |

- `operation_attempts`: `1,846`

## 2. Which Blueprints Exist and Have Been Used?

| Org | Blueprint | Used | Submissions | Completed submissions | Last run |
|---|---|---:|---:|---:|---|
| `AlumniGTM` | `AlumniGTM Company Resolution Only v1` | yes | 9 | 2 | `2026-03-04 01:36:19+00` |
| `AlumniGTM` | `AlumniGTM Company Workflow v1` | yes | 10 | 5 | `2026-03-03 04:09:05+00` |
| `AlumniGTM` | `AlumniGTM Prospect Discovery v1` | yes | 8 | 1 | `2026-03-04 03:03:11+00` |
| `AlumniGTM` | `AlumniGTM Prospect Resolution v1` | no | 0 | 0 | — |
| `AlumniGTM` | `Company Intel Briefing v1` | yes | 3 | 3 | `2026-02-24 21:38:59+00` |
| `AlumniGTM` | `ICP Job Titles Discovery v1` | yes | 4 | 3 | `2026-02-28 03:21:18+00` |
| `AlumniGTM` | `Person Intel Briefing v1` | yes | 2 | 1 | `2026-02-28 02:43:45+00` |
| `Phase6 Org` | `Phase6 Blueprint 1771280001` | no | 0 | 0 | — |
| `Revenue Activation` | `Basic Company Enrichment` | yes | 5 | 0 | `2026-02-17 19:52:13+00` |
| `Revenue Activation` | `Company Enrichment + Person Enrichment Fan Out` | yes | 5 | 1 | `2026-02-17 21:41:42+00` |
| `Revenue Activation` | `CRM Cleanup v1` | no | 0 | 0 | — |
| `Revenue Activation` | `CRM Enrichment v1` | no | 0 | 0 | — |
| `Revenue Activation` | `Staffing Enrichment v1` | no | 0 | 0 | — |
| `Staffing Activation` | `CRM Cleanup v1` | no | 0 | 0 | — |
| `Staffing Activation` | `CRM Enrichment v1` | no | 0 | 0 | — |
| `Staffing Activation` | `Staffing Enrichment v1` | yes | 2 | 1 | `2026-02-20 04:25:23+00` |

No changes from March 10. No new blueprints used.

## 3. Which Operations Have Actually Been Called?

### Important Boundary

`operation_runs` only captures FastAPI-dispatched operations from `app/routers/execute_v1.py`. It does not capture:

- Trigger-direct operations in `trigger/src/tasks/run-pipeline.ts` (e.g., `company.derive.icp_job_titles`, `company.derive.intel_briefing`, `person.derive.intel_briefing`, `company.resolve.domain_from_name_parallel`)
- External ingestion operations recorded in entity `last_operation_id` (e.g., `external.ingest.clay`, `external.ingest.clay.find_companies`, `external.ingest.clay.find_people`)
- FMCSA feed ingestion tasks (pure Trigger.dev tasks, no pipeline orchestration)
- Federal data ingestion tasks (SAM.gov, SBA, USAspending)

### FastAPI-Backed Operations (`operation_runs`)

| Operation | Calls | Failed | Failure rate | Last called |
|---|---:|---:|---:|---|
| `company.resolve.domain_from_name_hq` | 533 | 0 | 0.0% | `2026-03-04 03:04:22+00` |
| `company.research.infer_linkedin_url` | 426 | 41 | 9.6% | `2026-03-04 03:04:34+00` |
| `company.enrich.profile_blitzapi` | 420 | 0 | 0.0% | `2026-03-04 03:04:29+00` |
| `company.derive.evaluate_icp_fit` | 221 | 16 | 7.2% | `2026-03-04 03:04:35+00` |
| `company.derive.salesnav_url` | 76 | 0 | 0.0% | `2026-03-04 01:36:46+00` |
| `person.search.sales_nav_url` | 66 | 28 | 42.4% | `2026-03-04 03:34:46+00` |
| `person.contact.resolve_email` | 27 | 0 | 0.0% | `2026-02-17 21:42:56+00` |
| `company.research.icp_job_titles_gemini` | 20 | 0 | 0.0% | `2026-03-03 04:10:04+00` |
| `company.derive.icp_criterion` | 18 | 9 | 50.0% | `2026-03-03 04:10:44+00` |
| `company.research.discover_customers_gemini` | 14 | 1 | 7.1% | `2026-03-03 00:48:57+00` |
| `company.enrich.card_revenue` | 10 | 2 | 20.0% | `2026-03-01 19:43:31+00` |
| `company.research.discover_competitors` | 9 | 4 | 44.4% | `2026-02-24 02:03:26+00` |
| `company.enrich.profile` | 6 | 0 | 0.0% | `2026-03-02 02:26:36+00` |
| `company.research.lookup_customers_resolved` | 6 | 1 | 16.7% | `2026-03-03 04:10:28+00` |
| `company.ads.search.google` | 5 | 0 | 0.0% | `2026-02-17 21:42:07+00` |
| `company.ads.search.linkedin` | 5 | 0 | 0.0% | `2026-02-17 21:41:59+00` |
| `company.ads.search.meta` | 5 | 0 | 0.0% | `2026-02-17 21:42:05+00` |
| `company.research.resolve_g2_url` | 5 | 0 | 0.0% | `2026-02-17 21:41:54+00` |
| `company.research.resolve_pricing_page_url` | 5 | 0 | 0.0% | `2026-02-17 21:41:56+00` |
| `person.search` | 5 | 0 | 0.0% | `2026-02-17 21:42:10+00` |
| `company.fetch.icp_candidates` | 4 | 0 | 0.0% | `2026-02-28 03:21:24+00` |
| `company.enrich.technographics` | 2 | 2 | 100.0% | `2026-02-18 04:13:23+00` |
| `company.research.lookup_customers` | 2 | 2 | 100.0% | `2026-02-18 04:13:23+00` |
| `company.derive.pricing_intelligence` | 1 | 0 | 0.0% | `2026-02-18 04:13:04+00` |
| `company.research.check_vc_funding` | 1 | 1 | 100.0% | `2026-02-18 04:12:15+00` |
| `company.research.find_similar_companies` | 1 | 1 | 100.0% | `2026-02-18 04:12:15+00` |
| `company.research.lookup_alumni` | 1 | 1 | 100.0% | `2026-02-18 04:12:15+00` |
| `company.research.lookup_champion_testimonials` | 1 | 1 | 100.0% | `2026-02-18 04:12:15+00` |
| `company.research.lookup_champions` | 1 | 1 | 100.0% | `2026-02-18 04:12:15+00` |
| `job.search` | 1 | 0 | 0.0% | `2026-02-20 04:25:31+00` |
| `job.validate.is_active` | 1 | 0 | 0.0% | `2026-02-20 04:10:17+00` |
| `person.enrich.profile` | 1 | 0 | 0.0% | `2026-03-03 03:16:42+00` |

No change from March 10.

### Trigger-Direct Operations

| Operation | Executed steps | Succeeded | Failed | Last called |
|---|---:|---:|---:|---|
| `company.resolve.linkedin_from_domain_blitzapi` | 595 | 0 | 0 | `2026-03-04 03:04:04+00` |
| `company.derive.icp_job_titles` | 180 | 161 | 15 | `2026-02-28 03:21:24+00` |
| `company.resolve.domain_from_name_parallel` | 75 | 22 | 44 | `2026-03-03 00:08:37+00` |
| `person.contact.resolve_mobile_phone` | 5 | 0 | 0 | `2026-02-20 04:25:31+00` |
| `person.contact.verify_email` | 5 | 0 | 0 | `2026-02-20 04:25:31+00` |
| `company.derive.intel_briefing` | 3 | 3 | 0 | `2026-02-24 21:38:59+00` |
| `person.derive.intel_briefing` | 2 | 1 | 1 | `2026-02-28 02:43:45+00` |

Note: `company.resolve.linkedin_from_domain_blitzapi`, `person.contact.resolve_mobile_phone`, and `person.contact.verify_email` appear in blueprint snapshots as step positions but all their step_results are `skipped` — they were never actually executed. They are counted as "in blueprints but never executed."

### External Ingestion Operations

These operations appear in entity `last_operation_id` but do not go through the pipeline orchestration:

| Operation | Entity type | Entities created |
|---|---|---:|
| `external.ingest.clay.find_companies` | company | 41,146 |
| `external.ingest.clay` | company | 4,445 |
| `external.ingest.clay.find_people` | person | (subset of 2,116) |

### Operations Actually Called in Production

All observed pipeline activity falls within February–March 2026. The actually called set through the pipeline is `36` operations (unchanged from March 10):

- `company.ads.search.google`
- `company.ads.search.linkedin`
- `company.ads.search.meta`
- `company.derive.evaluate_icp_fit`
- `company.derive.icp_criterion`
- `company.derive.icp_job_titles`
- `company.derive.intel_briefing`
- `company.derive.pricing_intelligence`
- `company.derive.salesnav_url`
- `company.enrich.card_revenue`
- `company.enrich.profile`
- `company.enrich.profile_blitzapi`
- `company.enrich.technographics`
- `company.fetch.icp_candidates`
- `company.research.check_vc_funding`
- `company.research.discover_competitors`
- `company.research.discover_customers_gemini`
- `company.research.find_similar_companies`
- `company.research.icp_job_titles_gemini`
- `company.research.infer_linkedin_url`
- `company.research.lookup_alumni`
- `company.research.lookup_champion_testimonials`
- `company.research.lookup_champions`
- `company.research.lookup_customers`
- `company.research.lookup_customers_resolved`
- `company.research.resolve_g2_url`
- `company.research.resolve_pricing_page_url`
- `company.resolve.domain_from_name_hq`
- `company.resolve.domain_from_name_parallel`
- `job.search`
- `job.validate.is_active`
- `person.contact.resolve_email`
- `person.derive.intel_briefing`
- `person.enrich.profile`
- `person.search`
- `person.search.sales_nav_url`

### Operations in the Live Code Catalog That Have Never Been Called

Comparison basis:

- `86` operations from `app/routers/execute_v1.py` (was `78` in March 10)
- plus `4` Trigger-direct operations from `trigger/src/tasks/run-pipeline.ts`
- `90` total operations in the executable code catalog (was `82`)
- `36` actually called in production
- `54` never called (was `46`)

New operations added to the catalog since March 10 (all never called):

- `company.enrich.bulk_profile`
- `company.enrich.bulk_prospeo`
- `company.enrich.fmcsa.carrier_all_history`
- `company.enrich.fmcsa.company_census`
- `company.enrich.fmcsa.insur_all_history`
- `company.enrich.fmcsa.revocation_all_history`
- `person.resolve.from_email`
- `person.resolve.from_phone`

Complete never-called list (`54` operations):

- `address.search`
- `address.search.residents`
- `company.analyze.sec_10k`
- `company.analyze.sec_10q`
- `company.analyze.sec_8k_executive`
- `company.derive.detect_changes`
- `company.derive.extract_icp_titles`
- `company.enrich.bulk_profile`
- `company.enrich.bulk_prospeo`
- `company.enrich.ecommerce`
- `company.enrich.fmcsa`
- `company.enrich.fmcsa.carrier_all_history`
- `company.enrich.fmcsa.company_census`
- `company.enrich.fmcsa.insur_all_history`
- `company.enrich.fmcsa.revocation_all_history`
- `company.enrich.hiring_signals`
- `company.enrich.locations`
- `company.enrich.tech_stack`
- `company.research.check_court_filings`
- `company.research.fetch_sec_filings`
- `company.research.get_docket_detail`
- `company.resolve.domain_from_email`
- `company.resolve.domain_from_linkedin`
- `company.resolve.domain_from_name`
- `company.resolve.linkedin_from_domain`
- `company.resolve.linkedin_from_domain_blitzapi`
- `company.resolve.location_from_domain`
- `company.search`
- `company.search.blitzapi`
- `company.search.by_job_postings`
- `company.search.by_tech_stack`
- `company.search.ecommerce`
- `company.search.fmcsa`
- `company.signal.bankruptcy_filings`
- `contractor.enrich`
- `contractor.search`
- `contractor.search.employees`
- `market.enrich.geo_detail`
- `market.enrich.metrics_current`
- `market.enrich.metrics_monthly`
- `market.search.cities`
- `market.search.counties`
- `market.search.jurisdictions`
- `market.search.zipcodes`
- `permit.search`
- `person.contact.resolve_email_blitzapi`
- `person.contact.resolve_mobile_phone`
- `person.contact.verify_email`
- `person.derive.detect_changes`
- `person.resolve.from_email`
- `person.resolve.from_phone`
- `person.resolve.linkedin_from_email`
- `person.search.employee_finder_blitzapi`
- `person.search.waterfall_icp_blitzapi`

### FMCSA Query Endpoints

`app/routers/fmcsa_v1.py` provides `10` dedicated FMCSA query/analytics endpoints. These are read-only query endpoints, not operation IDs:

- `POST /fmcsa-carriers/query`
- `POST /fmcsa-carriers/stats`
- `POST /fmcsa-carriers/safety-risk`
- `POST /fmcsa-carriers/export`
- `POST /fmcsa-crashes/query`
- `GET /fmcsa-carriers/{dot_number}`
- `POST /fmcsa-signals/query`
- `GET /fmcsa-signals/summary`
- `GET /fmcsa-carriers/{dot_number}/signals`
- `POST /fmcsa-carriers/analytics`

## 4. Entity Data Quality

### `company_entities`

| Metric | Value |
|---|---:|
| Total rows | 45,679 |
| `canonical_domain` populated | 39,101 |
| `last_enriched_at` populated | 45,679 |
| `source_providers` populated | 45,602 |
| `last_enriched_at` min | `2026-02-17 19:52:35+00` |
| `last_enriched_at` max | `2026-03-18 01:00:22+00` |

Source breakdown by `last_operation_id`:

| Operation | Count |
|---|---:|
| `external.ingest.clay.find_companies` | 41,146 |
| `external.ingest.clay` | 4,445 |
| `company.derive.salesnav_url` | 45 |
| `company.resolve.domain_from_name_parallel` | 20 |
| Other pipeline operations | 23 |

The vast majority (`99.8%`) of company entities are from Clay ingestion, not from pipeline execution.

### `person_entities`

| Metric | Value |
|---|---:|
| Total rows | 2,116 |
| `linkedin_url` populated | 1,921 |
| `work_email` populated | 24 |
| `last_enriched_at` populated | 2,116 |
| `last_enriched_at` min | `2026-02-17 21:42:33+00` |
| `last_enriched_at` max | `2026-03-14 21:26:09+00` |

Source breakdown by `last_operation_id`:

- `external.ingest.clay.find_people` (new since March 10)
- `company.derive.evaluate_icp_fit`
- `company.derive.icp_job_titles`
- `company.enrich.profile_blitzapi`
- `company.research.infer_linkedin_url`
- `person.contact.resolve_email`
- `person.derive.intel_briefing`
- `person.search.sales_nav_url`

### `job_posting_entities`

| Metric | Value |
|---|---:|
| Total rows | 1 |
| `posting_status = active` | 1 |
| `posting_status = closed` | 0 |

No change from March 10.

## 5. Auto-Persist Health

### Summary

| Materialized table | Upstream evidence from successful steps | Table state | Verdict |
|---|---|---|---|
| `icp_job_titles` | 161 successful steps | 156 rows | healthy |
| `company_intel_briefings` | 3 successful steps | 3 rows | healthy |
| `person_intel_briefings` | 1 successful step | 1 row | healthy |
| `entity_relationships` | n/a (Clay ingestion path) | 1,892 rows | healthy (new) |
| `gemini_icp_job_titles` | 20 successful steps | 0 rows | broken |
| `company_customers` | 18 successful steps | 0 rows | broken |
| `company_ads` | table exists, 0 rows | 0 rows | broken (improved — table now exists) |
| `salesnav_prospects` | 35 successful steps | 0 rows | broken |
| `extracted_icp_job_title_details` | 0 upstream steps | 0 rows | unused |

### `icp_job_titles`

- Successful found steps: `161`
- Table rows: `156`
- Verdict: **healthy** (unchanged from March 10)

### `company_intel_briefings`

- Successful steps: `3`
- Table rows: `3`
- Verdict: **healthy** (unchanged from March 10)

### `person_intel_briefings`

- Successful steps: `1`
- Table rows: `1`
- Verdict: **healthy** (unchanged from March 10)

### `entity_relationships`

- Table rows: `1,892`
- All rows: `person` → `works_at` → `company`
- Verdict: **healthy** (was `0` rows in March 10 — now populated via Clay ingestion path)

### `company_customers`

- Successful customer-producing steps: `18` (was `17` in March 10)
- Table rows: `0`
- Verdict: **broken** (unchanged)

### `gemini_icp_job_titles`

- Successful steps: `20`
- Table rows: `0`
- Verdict: **broken** (unchanged)

### `company_ads`

- Table now exists in production (was missing in March 10)
- Table rows: `0`
- No upstream step evidence with ad data found in recent step results
- Verdict: **broken** (improved — table exists but still no data)

### `salesnav_prospects`

- Successful prospect-producing steps: `35` (was `17` in March 10)
- Table rows: `0`
- Verdict: **broken** (unchanged — upstream evidence increased but still no persisted data)

### `extracted_icp_job_title_details`

- Table rows: `0`
- `company.derive.extract_icp_titles` has never been called
- Verdict: **unused** (unchanged)

## 6. What's Broken or Stale?

### Tables with Zero Rows That Should Have Data

These have live upstream evidence from successful steps but `0` persisted rows:

- `entities.company_customers`: `0` rows despite `18` successful customer-producing steps.
- `entities.gemini_icp_job_titles`: `0` rows despite `20` successful Gemini ICP title steps.
- `entities.salesnav_prospects`: `0` rows despite `35` successful prospect-producing steps.
- `entities.fmcsa_carrier_signals`: `0` rows — table exists (migration 035) but signal detection has not populated it.

These are unused rather than broken:

- `entities.extracted_icp_job_title_details`: `0` rows, `company.derive.extract_icp_titles` has never been called.

### Tables with Zero Rows but Table Now Exists

- `entities.company_ads`: `0` rows. Table now exists in production (was missing in March 10). The original ad-producing steps (`company.ads.search.google`, `company.ads.search.meta`) ran in February but auto-persist failed. No new ad steps since.

### Tables Missing Entirely

- `entities.mv_fmcsa_authority_grants` — migration 036 exists in repo but has not been applied to production.
- `entities.mv_fmcsa_insurance_cancellations` — migration 037 exists in repo but has not been applied to production.

### Stale `running` Pipeline Runs

**None.** All 8 previously stuck `running` pipeline runs from March 10 have resolved to `failed`. No pipeline runs are currently stuck.

### Stale `running` or `queued` Step Results

**None.** All 7 previously `running` step results resolved to `failed`. All 190 previously `queued` step results resolved to `skipped`. No step results are currently stuck.

### Legacy vs Operation-Native State

`steps` table:

- total rows: `1`
- active rows: `1`

`blueprint_steps`:

- total rows: `73`
- operation-native only: `72`
- legacy step rows: `1`

The single legacy row remains the Phase6 test blueprint, which has never been used. Live traffic is operation-native.

### Evidence of Deploy-Timing Class Failures

The same patterns documented in March 10 persist:

- `company_customers = 0` despite `18` successful customer-producing steps
- `gemini_icp_job_titles = 0` despite `20` successful Gemini ICP title steps
- `salesnav_prospects = 0` despite `35` successful prospect-producing steps

These are pre-existing failures, not new regressions. No new pipeline activity has occurred since March 4, so no new deploy-timing failures could have been introduced.

### New: Schema Drift — Migrations Not Applied

Two materialized view migrations exist in the repo but are not reflected in production:

- `036_mv_fmcsa_authority_grants.sql`
- `037_mv_fmcsa_insurance_cancellations.sql`

This is the same class of problem as the `company_ads` table in March 10 (migration exists in repo but not in production), now affecting materialized views.

## 7. Trigger.dev State

### Observable State

Trigger.dev state cannot be directly queried from the production database. What can be observed:

- The most recent `trigger_run_id` in `ops.pipeline_runs` is `run_cmmbgdcoob99h0okbr78gfpl1` from `2026-03-04`.
- No pipeline runs are in `running` state, meaning Trigger.dev is not actively executing any pipeline tasks.
- FMCSA feed ingestion is clearly active based on `feed_date = 2026-03-17` across all 18 FMCSA tables, meaning Trigger.dev scheduled tasks are running daily.
- Federal data ingestion (SAM.gov, SBA, USAspending) has data as recent as `2026-03-17`, confirming active Trigger.dev task execution.
- Entity data (`company_entities`, `person_entities`) shows `last_enriched_at` as recent as `2026-03-18`, confirming active Clay ingestion tasks.

### What Cannot Be Observed

- Current deployed worker version (not queryable from psql)
- Registered tasks on the current prod worker
- Scheduled trigger state
- Trigger.dev environment variables

## 8. FMCSA Tables

All 18 FMCSA canonical tables exist in the `entities` schema and are populated with data as recent as `2026-03-17`.

| Table | Exists | Rows | Latest feed_date |
|---|---|---:|---|
| `entities.operating_authority_histories` | yes | 29,698,317 | 2026-03-17 |
| `entities.operating_authority_revocations` | yes | 4,560,479 | 2026-03-17 |
| `entities.insurance_policies` | yes | 1,461,896 | 2026-03-17 |
| `entities.insurance_policy_filings` | yes | 3,141,690 | 2026-03-17 |
| `entities.insurance_policy_history_events` | yes | 3,707,493 | 2026-03-17 |
| `entities.carrier_registrations` | yes | 2,427,513 | 2026-03-17 |
| `entities.process_agent_filings` | yes | 7,773,930 | 2026-03-17 |
| `entities.insurance_filing_rejections` | yes | 123,064 | 2026-03-17 |
| `entities.carrier_safety_basic_measures` | yes | 4,569,132 | 2026-03-13 |
| `entities.carrier_safety_basic_percentiles` | yes | 109,728 | 2026-03-13 |
| `entities.carrier_inspection_violations` | yes | 2,195,501 | 2026-03-17 |
| `entities.carrier_inspections` | yes | 2,840,501 | 2026-03-17 |
| `entities.motor_carrier_census_records` | yes | 3,221,542 | 2026-03-17 |
| `entities.commercial_vehicle_crashes` | yes | 3,808,001 | 2026-03-17 |
| `entities.vehicle_inspection_units` | yes | 2,007,501 | 2026-03-17 |
| `entities.vehicle_inspection_special_studies` | yes | 2,944,780 | 2026-03-17 |
| `entities.out_of_service_orders` | yes | 1,150,850 | 2026-03-17 |
| `entities.vehicle_inspection_citations` | yes | 81,691 | 2026-03-17 |

**Total FMCSA rows across 18 tables: `75,823,609`**

### FMCSA Signal Detection

| Table | Exists | Rows |
|---|---|---:|
| `entities.fmcsa_carrier_signals` | yes | 0 |

Signal detection table exists but has not been populated.

### FMCSA Analytics Materialized Views

| View | Exists | Rows |
|---|---|---:|
| `entities.mv_fmcsa_authority_grants` | **no** | n/a |
| `entities.mv_fmcsa_insurance_cancellations` | **no** | n/a |

Migrations 036 and 037 have not been applied to production.

### FMCSA Data Freshness

- 16 of 18 tables have data as recent as `2026-03-17` (yesterday).
- `carrier_safety_basic_measures` and `carrier_safety_basic_percentiles` have data as recent as `2026-03-13` — 5 days behind the other tables. This may indicate a less frequent update schedule for SMS (Safety Measurement System) data or a stalled ingestion task.

### Federal Data Tables

| Table | Exists | Rows | Latest |
|---|---|---:|---|
| `entities.sam_gov_entities` | yes | 867,137 | `2026-03-16` |
| `entities.sba_7a_loans` | yes | 356,375 | `2026-03-16` |
| `entities.usaspending_contracts` | yes | 14,665,610 | `2026-03-17` |
| `entities.mv_federal_contract_leads` | yes (MV) | 1,340,862 | n/a |

## Bottom Line

The production baseline to protect is:

**Orchestration** (in `ops` schema):

- `submissions` / `pipeline_runs` / `step_results` / `operation_runs` — unchanged since March 10, all stuck runs resolved.

**Entity core** (in `entities` schema):

- `company_entities` (`45,679` rows — 99.8% from Clay ingestion)
- `person_entities` (`2,116` rows)
- `job_posting_entities` (`1` row)
- `entity_timeline` (`4,345` rows)
- `entity_snapshots` (`6,407` rows)
- `entity_relationships` (`1,892` rows — now healthy)

**Healthy auto-persist paths**:

- `icp_job_titles` (`156` rows)
- `company_intel_briefings` (`3` rows)
- `person_intel_briefings` (`1` row)

**FMCSA** (in `entities` schema):

- 18 canonical tables with `75.8M` total rows, data current as of `2026-03-17`
- Daily feed ingestion is active and healthy

**Federal data** (in `entities` schema):

- `sam_gov_entities` (`867K`), `sba_7a_loans` (`356K`), `usaspending_contracts` (`14.7M`)
- `mv_federal_contract_leads` materialized view (`1.3M` rows)

**Known broken (pre-existing, not regressions)**:

- `company_customers` materialization (`0` rows, `18` successful upstream steps)
- `gemini_icp_job_titles` materialization (`0` rows, `20` successful upstream steps)
- `salesnav_prospects` materialization (`0` rows, `35` successful upstream steps)
- `company_ads` (`0` rows — table exists now but no data)
- `fmcsa_carrier_signals` (`0` rows — table exists but not populated)
- `mv_fmcsa_authority_grants` and `mv_fmcsa_insurance_cancellations` — migrations not applied to production
