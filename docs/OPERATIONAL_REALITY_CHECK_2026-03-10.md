# Operational Reality Check

As of `2026-03-10`.

This report is based on:

- Live production SQL run against the production `DATABASE_URL` via `doppler run -p data-engine-x-api -c prd -- psql`.
- Live Trigger.dev production state from the prod worker and prod env-var inventory.
- Live code in `app/routers/execute_v1.py`, `trigger/src/tasks/run-pipeline.ts`, `app/routers/internal.py`, and the repo migrations under `supabase/migrations/`.

## Executive Summary

Production is still running entirely out of the `public` schema. There is no live `ops` schema and no live `entities` schema yet.

Core orchestration is real and partially healthy:

- `submissions`, `pipeline_runs`, `step_results`, `operation_runs`, entity tables, timeline tables, and `icp_job_titles` all have live data.
- `company.derive.icp_job_titles`, `company.derive.intel_briefing`, and `person.derive.intel_briefing` are materially persisting correctly.

There is also clear production drift and breakage:

- `company_ads` is missing entirely in prod, even though the repo has `supabase/migrations/019_company_ads.sql` and the code attempts to write it.
- `company_customers`, `gemini_icp_job_titles`, and `salesnav_prospects` all exist in prod but have `0` rows despite successful upstream step outputs.
- `8` `pipeline_runs` are stuck in `running` for `7-14` days.
- `7` `step_results` are stuck in `running`, and `190` are still `queued`.
- The live system is overwhelmingly operation-native: `72/73` `blueprint_steps` rows use `operation_id`; only `1` legacy `step_id` row remains.

## 1. What's Actually Running?

### Live Schema Reality

Production currently has the application tables in `public`, not in separate `ops` / `entities` schemas.

Observed application tables in `public`:

- `api_tokens`
- `blueprint_steps`
- `blueprints`
- `companies`
- `company_customers`
- `company_entities`
- `company_intel_briefings`
- `entity_relationships`
- `entity_snapshots`
- `entity_timeline`
- `extracted_icp_job_title_details`
- `gemini_icp_job_titles`
- `icp_job_titles`
- `job_posting_entities`
- `operation_attempts`
- `operation_runs`
- `orgs`
- `person_entities`
- `person_intel_briefings`
- `pipeline_runs`
- `salesnav_prospects`
- `step_results`
- `steps`
- `submissions`
- `super_admins`
- `users`

### Row Counts

| Table | Exists in prod | Rows |
|---|---:|---:|
| `submissions` | yes | 48 |
| `pipeline_runs` | yes | 837 |
| `step_results` | yes | 3283 |
| `operation_runs` | yes | 1899 |
| `operation_attempts` | yes | 1846 |
| `company_entities` | yes | 88 |
| `person_entities` | yes | 503 |
| `job_posting_entities` | yes | 1 |
| `entity_timeline` | yes | 4345 |
| `entity_snapshots` | yes | 93 |
| `icp_job_titles` | yes | 156 |
| `company_intel_briefings` | yes | 3 |
| `person_intel_briefings` | yes | 1 |
| `gemini_icp_job_titles` | yes | 0 |
| `company_customers` | yes | 0 |
| `company_ads` | no | n/a |
| `salesnav_prospects` | yes | 0 |
| `extracted_icp_job_title_details` | yes | 0 |
| `entity_relationships` | yes | 0 |

### `submissions`

- Total rows: `48`
- Status breakdown:

| Status | Count |
|---|---:|
| `failed` | 30 |
| `completed` | 17 |
| `queued` | 1 |

- Most recent submission:

| id | org | company | blueprint | status | source | created_at |
|---|---|---|---|---|---|---|
| `e87a29e9-e231-41f4-8cdc-e288656435b8` | `AlumniGTM` | `global` | `AlumniGTM Prospect Discovery v1` | `failed` | `api_v1_batch` | `2026-03-04 03:03:11+00` |

### `pipeline_runs`

- Total rows: `837`

| Status | Count |
|---|---:|
| `succeeded` | 679 |
| `failed` | 150 |
| `running` | 8 |

- Most recent pipeline run:

| id | submission_id | org | company | status | trigger_run_id | parent_pipeline_run_id | created_at |
|---|---|---|---|---|---|---|---|
| `654486ba-227d-49f1-81ee-c3dc0b712df8` | `e87a29e9-e231-41f4-8cdc-e288656435b8` | `AlumniGTM` | `global` | `succeeded` | `run_cmmbgdcoob99h0okbr78gfpl1` | `0b80d964-13a5-4274-8732-3e7fa28b45ed` | `2026-03-04 03:04:04+00` |

### `step_results`

- Total rows: `3283`

| Status | Count |
|---|---:|
| `succeeded` | 1946 |
| `skipped` | 990 |
| `queued` | 190 |
| `failed` | 150 |
| `running` | 7 |

- Most recent step result:

| id | pipeline_run_id | submission_id | step_position | status | created_at |
|---|---|---|---:|---|---|
| `0d443927-3d2d-4a5a-8c3e-aba0f2725af1` | `654486ba-227d-49f1-81ee-c3dc0b712df8` | `e87a29e9-e231-41f4-8cdc-e288656435b8` | 2 | `succeeded` | `2026-03-04 03:04:04+00` |

### `operation_runs` and `operation_attempts`

- `operation_runs`: `1899`
- `operation_runs` failed: `111`
- `operation_runs` non-failed: `1788`
- Most recent `operation_run`:

| run_id | operation_id | status | created_at |
|---|---|---|---|
| `fd4b421b-7ba9-49ba-b716-5f85acc54c52` | `person.search.sales_nav_url` | `failed` | `2026-03-04 03:34:46+00` |

- `operation_attempts`: `1846`

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
| `Phase6 Org 1771280001` | `Phase6 Blueprint 1771280001` | no | 0 | 0 | — |
| `Revenue Activation` | `Basic Company Enrichment` | yes | 5 | 0 | `2026-02-17 19:52:13+00` |
| `Revenue Activation` | `Company Enrichment + Person Enrichment Fan Out` | yes | 5 | 1 | `2026-02-17 21:41:42+00` |
| `Revenue Activation` | `CRM Cleanup v1` | no | 0 | 0 | — |
| `Revenue Activation` | `CRM Enrichment v1` | no | 0 | 0 | — |
| `Revenue Activation` | `Staffing Enrichment v1` | no | 0 | 0 | — |
| `Staffing Activation` | `CRM Cleanup v1` | no | 0 | 0 | — |
| `Staffing Activation` | `CRM Enrichment v1` | no | 0 | 0 | — |
| `Staffing Activation` | `Staffing Enrichment v1` | yes | 2 | 1 | `2026-02-20 04:25:23+00` |

## 3. Which Operations Have Actually Been Called?

### Important Boundary

`operation_runs` only captures FastAPI-dispatched operations from `app/routers/execute_v1.py`. It does not capture Trigger-direct operations in `trigger/src/tasks/run-pipeline.ts`, specifically:

- `company.derive.icp_job_titles`
- `company.derive.intel_briefing`
- `person.derive.intel_briefing`
- `company.resolve.domain_from_name_parallel`

So the real “actually called” set in production is:

- `operation_runs` data
- plus executed Trigger-direct steps from `step_results` joined to `pipeline_runs.blueprint_snapshot`

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

### Trigger-Direct Operations

| Operation | Executed steps | Failed steps | Last called |
|---|---:|---:|---|
| `company.derive.icp_job_titles` | 176 | 8 | `2026-02-28 03:31:16+00` |
| `company.resolve.domain_from_name_parallel` | 66 | 44 | `2026-03-03 00:13:34+00` |
| `company.derive.intel_briefing` | 3 | 0 | `2026-02-24 21:56:36+00` |
| `person.derive.intel_briefing` | 2 | 1 | `2026-02-28 02:43:50+00` |

### Operations Actually Called in the Last 30 Days

All observed production activity falls within the last 30 days. The actual called set is `36` operations:

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

- `78` operations from `app/routers/execute_v1.py`
- plus `4` Trigger-direct operations from `trigger/src/tasks/run-pipeline.ts`
- `82` total operations in the executable code catalog
- `36` actually called in production
- `46` never called

Never-called operations:

- `address.search`
- `address.search.residents`
- `company.analyze.sec_10k`
- `company.analyze.sec_10q`
- `company.analyze.sec_8k_executive`
- `company.derive.detect_changes`
- `company.derive.extract_icp_titles`
- `company.enrich.ecommerce`
- `company.enrich.fmcsa`
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
- `person.resolve.linkedin_from_email`
- `person.search.employee_finder_blitzapi`
- `person.search.waterfall_icp_blitzapi`

## 4. Entity Data Quality

### `company_entities`

| Metric | Value |
|---|---:|
| Total rows | 88 |
| `canonical_domain` populated | 63 |
| `last_enriched_at` populated | 88 |
| `source_providers` populated | 11 |
| `last_enriched_at` min | `2026-02-17 19:52:35+00` |
| `last_enriched_at` max | `2026-03-04 01:36:48+00` |

### `person_entities`

`person_entities` in prod does not have a top-level `source_providers` column. The live columns are:

- `org_id`
- `company_id`
- `entity_id`
- `full_name`
- `first_name`
- `last_name`
- `linkedin_url`
- `title`
- `seniority`
- `department`
- `work_email`
- `email_status`
- `phone_e164`
- `contact_confidence`
- `last_enriched_at`
- `last_operation_id`
- `last_run_id`
- `record_version`
- `canonical_payload`
- `created_at`
- `updated_at`

So the direct analog of the `company_entities.source_providers` question cannot be answered from a first-class column in prod. The closest observable proxy is whether `canonical_payload.source_providers` exists.

| Metric | Value |
|---|---:|
| Total rows | 503 |
| `linkedin_url` populated | 308 |
| `work_email` populated | 24 |
| `last_enriched_at` populated | 503 |
| `canonical_payload.source_providers` present | 27 |
| `last_enriched_at` min | `2026-02-17 21:42:33+00` |
| `last_enriched_at` max | `2026-03-04 03:04:35+00` |

### `job_posting_entities`

| Metric | Value |
|---|---:|
| Total rows | 1 |
| `posting_status = active` | 1 |
| `posting_status = closed` | 0 |

## 5. Auto-Persist Health

### Summary

| Materialized table | Upstream evidence from successful steps | Table state | Verdict |
|---|---|---|---|
| `icp_job_titles` | 161 successful found steps, 156 distinct org/domain outputs | 156 rows | healthy |
| `company_intel_briefings` | 3 successful steps, 3 distinct domains | 3 rows | healthy |
| `person_intel_briefings` | 1 successful step | 1 row | healthy |
| `gemini_icp_job_titles` | 20 successful steps, 12 distinct domains | 0 rows | broken |
| `company_customers` | 17 successful steps, 331 customer items, 11 source companies | 0 rows | broken |
| `company_ads` | 2 successful steps, 29 ads | table missing | broken |
| `salesnav_prospects` | 17 successful steps, 349 prospects | 0 rows | broken |

### `icp_job_titles`

- Successful found steps: `161`
- Distinct org/domain outputs: `156`
- Table rows: `156`
- Missing matches: `0`

This one is healthy. The dedicated table count matches the normalized distinct company-domain outputs from the successful steps.

### `company_customers`

- Successful steps with customers: `17`
- Distinct source companies: `11`
- Total customer items emitted by steps: `331`
- Table rows: `0`
- Missing source-company matches: `11`

Examples of missing source companies:

- `forethought.ai`
- `securitypalhq.com`
- `cartesia.ai`
- `openevidence.com`
- `gotogether.ai`
- `together.ai`
- `arena.ai`
- `glean.com`
- `databricks.com`
- `harvey.ai`
- `maxima.ai`

This is direct evidence of silent auto-persist failure.

### `company_ads`

- Successful ad-producing steps: `2`
- Distinct platform/company pairs: `2`
- Total ad items emitted by steps: `29`
- Live table exists: `false`

Examples:

- `company.ads.search.google` on `oncactus.com` produced `11` ads
- `company.ads.search.meta` on `oncactus.com` produced `18` ads

The repo has `supabase/migrations/019_company_ads.sql`, but production does not have the `company_ads` table at all. This is schema drift, not just a timing issue.

### `salesnav_prospects`

- Successful prospect-producing steps: `17`
- Total prospect items emitted by steps: `349`
- Table rows: `0`

Important detail: in every successful sampled `person.search.sales_nav_url` result I inspected, the `cumulative_context` did not carry a usable source company domain. The successful rows had `source_company_domain = ''`.

That means the Trigger auto-persist branch in `trigger/src/tasks/run-pipeline.ts` is very likely never firing the upsert, because it explicitly requires `sourceCompanyDomain` before posting to `/api/internal/salesnav-prospects/upsert`.

This looks like an input/context-shape bug, not a missing-table bug.

### `gemini_icp_job_titles`

- Successful steps: `20`
- Distinct org/domain pairs: `12`
- Table rows: `0`
- Missing matches: `12`

Examples of missing domains:

- `forethought.ai`
- `securitypalhq.com`
- `openevidence.com`
- `cartesia.ai`
- `gotogether.ai`
- `together.ai`
- `databricks.com`
- `glean.com`
- `getgarner.com`
- `arena.ai`
- `harvey.ai`
- `maxima.ai`

This is also direct evidence of silent auto-persist failure.

## 6. What's Broken or Stale?

### Tables with Zero Rows That Should Have Data

These are not just unused tables. They have live upstream evidence from successful steps:

- `company_customers`: `0` rows despite `17` successful customer-producing steps.
- `gemini_icp_job_titles`: `0` rows despite `20` successful Gemini ICP title steps.
- `salesnav_prospects`: `0` rows despite `17` successful prospect-producing steps and `349` emitted prospects.

These look unused rather than broken:

- `extracted_icp_job_title_details`: `0` rows, but `company.derive.extract_icp_titles` has never been called.
- `entity_relationships`: `0` rows, and code search found endpoints and service code but no pipeline/orchestrator call sites writing relationships from runtime execution.

### Tables Missing Entirely

- `company_ads` is missing entirely in prod.

Evidence:

- The repo has `supabase/migrations/019_company_ads.sql`.
- The code expects the table via `app/routers/internal.py` and the auto-persist block in `trigger/src/tasks/run-pipeline.ts`.
- Live production does not have `public.company_ads`.

### Stale `running` Pipeline Runs

There are `8` `pipeline_runs` stuck in `running` for more than 24 hours.

| pipeline_run_id | submission_id | age | trigger_run_id |
|---|---|---|---|
| `ffd463e3-a1d7-4dc3-82b2-b84ef4f82337` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:35` | `run_cmm0y1drt8m2v0on3hnma1rd9` |
| `00dee7e3-dc6a-4159-8a22-0c6e36021050` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:35` | `run_cmm0y1n8x8is80un3gluezbky` |
| `e95dd175-baa0-481a-94b4-aa6089176a14` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:34` | `run_cmm0y262c8i3h0un0esz15zbp` |
| `db7a404e-ac3f-4728-b717-ffa7e20d9cce` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:34` | `run_cmm0y28de8lzd0uojwjg80ep3` |
| `dc159488-14ce-45d0-a8de-8e17934e9093` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:34` | `run_cmm0y2rty8h1c0hojh63t3m0m` |
| `7a0ca070-dc52-4ce7-88dc-d0698856ae21` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:34` | `run_cmm0y2s448k240hn0igwhly4z` |
| `2c3fe5f2-a07d-436a-8ef6-7f46a72a5a97` | `0921f10b-890b-47ab-8ceb-b1986df51cbb` | `14 days 02:33` | `run_cmm0y3d0w8hf40hogjnfwgpaw` |
| `788f8ff3-fecd-4dd4-ba3d-56cebe6a83eb` | `2b333f02-903c-46bf-80ff-b25e9e1b92fa` | `7 days 15:02` | `run_cmma7fpbscr1b0ooek1k5wniw` |

There are also `7` `step_results` still stuck in `running`, all on `step_position = 2`, and `190` `step_results` still `queued`.

### Legacy vs Operation-Native State

`steps` table:

- total rows: `1`
- active rows: `1`

`blueprint_steps`:

- total rows: `73`
- operation-native only: `72`
- hybrid rows: `0`
- legacy step rows: `1`
- invalid rows: `0`

The single legacy row is:

- org: `Phase6 Org 1771280001`
- blueprint: `Phase6 Blueprint 1771280001`
- position: `1`
- `step_slug`: `phase6-step-1771280001`

That blueprint has never been used. So live traffic is effectively operation-native already.

### Evidence of the Known Deploy-Timing Class of Failure

Yes. There is direct production evidence of the same failure class described in the documented ICP auto-persist incident:

- successful `company.research.discover_customers_gemini` / `lookup_customers_resolved` steps with customer arrays, but `company_customers = 0`
- successful `company.research.icp_job_titles_gemini` steps with domainable outputs, but `gemini_icp_job_titles = 0`

Those are exactly “step_results have data, dedicated table has nothing” symptoms.

`icp_job_titles` itself looks healthy now, so the historic issue there appears to have been backfilled or corrected.

## 7. Trigger.dev State

### Current Deployed Version

Prod worker:

- version: `20260303.3`
- SDK: `4.4.0`

Registered tasks on the current prod worker:

- `deduplicate`
- `enrich-apollo`
- `execute-step`
- `hello-trigger`
- `normalize`
- `provider-waterfall-test`
- `run-pipeline`

### Active Scheduled Triggers

I could not get a direct schedule inventory from the available Trigger tooling.

What I could verify:

- code search in `trigger/src` found no cron/schedule definitions
- the current prod worker exposes tasks, but no schedule objects

So there is no code evidence of active cron-style scheduled triggers in this repo, but I cannot prove the negative from the Trigger API with the tools available here.

### Trigger Env Vars That Differ From Doppler

This comparison is by variable name only, not by value.

Trigger prod currently has `24` environment variables. The `data-engine-x-api` Doppler `prd` config has `43` secrets.

Shared names between Trigger and Doppler: `9`

Trigger-only names:

- `ADYNTEL_API_URL`
- `DATA_ENGINE_API_URL`
- `DATA_ENGINE_INTERNAL_API_KEY`
- `HEARTBEAT_INTERVAL_MS`
- `OTEL_BATCH_PROCESSING_ENABLED`
- `OTEL_LOG_EXPORT_TIMEOUT_MILLIS`
- `OTEL_LOG_MAX_EXPORT_BATCH_SIZE`
- `OTEL_LOG_MAX_QUEUE_SIZE`
- `OTEL_LOG_SCHEDULED_DELAY_MILLIS`
- `OTEL_SPAN_EXPORT_TIMEOUT_MILLIS`
- `OTEL_SPAN_MAX_EXPORT_BATCH_SIZE`
- `OTEL_SPAN_MAX_QUEUE_SIZE`
- `OTEL_SPAN_SCHEDULED_DELAY_MILLIS`
- `USAGE_EVENT_URL`
- `USAGE_HEARTBEAT_INTERVAL_MS`

Doppler-only names:

- `ADYNTEL_ACCOUNT_EMAIL`
- `AMPLELEADS_API_KEY`
- `API_URL`
- `BRIGHTDATA_API_KEY`
- `BUILTWITH_API_KEY`
- `COURTLISTENER_API_KEY`
- `DATABASE_URL`
- `DOPPLER_CONFIG`
- `DOPPLER_ENVIRONMENT`
- `DOPPLER_PROJECT`
- `ENIGMA_API_KEY`
- `EXA_API_KEY`
- `FMCSA_API_KEY`
- `FMCSA_SECRET_KEY`
- `GEMINI_API_KEY`
- `ICYPEAS_API_SECRET`
- `INTERNAL_API_KEY`
- `INTERNAL_AUTH_KEY`
- `JWT_SECRET`
- `MILLIONVERIFIER_API_KEY`
- `OPENWEBNINJA_API_KEY`
- `RAPIDAPI_LINKEDIN_SALES_NAV_SCRAPER_API_KEY`
- `RAPIDAPI_SALESNAV_SCRAPE_API_KEY`
- `REOON_API_KEY`
- `REVENUEINFRA_INGEST_API_KEY`
- `SERPER_API_KEY`
- `SUPABASE_SERVICE_KEY`
- `SUPABASE_URL`
- `SUPER_ADMIN_API_KEY`
- `SUPER_ADMIN_JWT_SECRET`
- `THEIRSTACK_API_KEY`
- `TRIGGER_DEV_SECRET_KEY`
- `TRIGGER_PROJECT_ID`
- `TRIGGER_SECRET_KEY`

## Bottom Line

Before a schema split, the production baseline to protect is:

- `submissions` / `pipeline_runs` / `step_results` / `operation_runs`
- `company_entities` / `person_entities` / `job_posting_entities`
- `entity_timeline` / `entity_snapshots`
- healthy dedicated tables:
  - `icp_job_titles`
  - `company_intel_briefings`
  - `person_intel_briefings`

The production issues you should assume are already broken before any schema move:

- `company_customers` materialization
- `gemini_icp_job_titles` materialization
- `salesnav_prospects` materialization
- `company_ads` schema presence in prod
- stale `running` pipeline and step rows

That means the schema split should be planned as:

- preserve the healthy paths exactly
- do not treat the currently broken materialization paths as a regression introduced by the split
- explicitly repair code/schema drift for the broken paths as separate tracked work
