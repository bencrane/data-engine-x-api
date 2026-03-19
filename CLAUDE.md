<!-- Last updated: 2026-03-18T23:59:00Z -->

# CLAUDE.md

Authoritative context for agents working in `data-engine-x-api`.

## Strategic Directive (Read First)

Read `docs/STRATEGIC_DIRECTIVE.md` before architecture or implementation decisions.

## Documentation Authority

Before relying on repo documentation beyond the audited reports, read `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`.

Production-truth precedence is:

1. `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`
2. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
3. `CLAUDE.md`

Important boundary:

- `docs/EXECUTOR_DIRECTIVE_*.md` files are scope documents and calibration examples.
- They are not evidence that the described work is deployed, production-verified, or currently healthy.
- Treat directives as intent unless the production-truth reports independently confirm the result.

## Repo Conventions

See `docs/REPO_CONVENTIONS.md`.

## Executor Work Log

See `docs/EXECUTOR_WORK_LOG.md`.

## Production State (as of 2026-03-18)

This section is based on `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`, which was verified against live production SQL.

### What Works End-to-End

- Schema split is complete: application tables live in `ops` (orchestration) and `entities` (domain data) schemas. `public` no longer contains application tables.
- The core pipeline loop works: submission -> pipeline run -> step execution -> entity state upsert. Production has `48` `submissions`, `837` `pipeline_runs`, `3283` `step_results`, `45,679` `company_entities`, `2,116` `person_entities`, `1` `job_posting_entities`, `4,345` `entity_timeline` rows, and `6,407` `entity_snapshots`.
- All previously stuck `running` pipeline runs and step results have resolved. No stuck runs remain.
- Blueprints with at least one completed production submission:
  - `AlumniGTM Company Resolution Only v1` - `2` completed submissions
  - `AlumniGTM Company Workflow v1` - `5` completed submissions
  - `AlumniGTM Prospect Discovery v1` - `1` completed submission
  - `Company Intel Briefing v1` - `3` completed submissions
  - `ICP Job Titles Discovery v1` - `3` completed submissions
  - `Person Intel Briefing v1` - `1` completed submission
  - `Company Enrichment + Person Enrichment Fan Out` - `1` completed submission
  - `Staffing Enrichment v1` - `1` completed submission
- Healthy auto-persist paths in production:
  - `icp_job_titles` - healthy; `161` successful found steps materialized into `156` distinct table rows with `0` missing matches
  - `company_intel_briefings` - healthy; `3` successful steps materialized into `3` rows
  - `person_intel_briefings` - healthy; `1` successful step materialized into `1` row
  - `entity_relationships` - healthy; `1,892` rows (all `person` → `works_at` → `company`, from Clay ingestion)
- FMCSA infrastructure: `18` canonical tables with `~75.8M` total rows, daily feed ingestion active with data current as of `2026-03-17`.
- Federal data: `sam_gov_entities` (`867,137`), `sba_7a_loans` (`356,375`), `usaspending_contracts` (`14,665,610`), `mv_federal_contract_leads` materialized view (`1,340,862`).
- Clay ingestion: `45,591` company entities and `1,613` person entities added since March 10 via `external.ingest.clay.find_companies` and `external.ingest.clay.find_people`.

### What Is Broken

- `company_customers` is broken. Production has `18` successful customer-producing steps, but the table has `0` rows.
- `gemini_icp_job_titles` is broken. Production has `20` successful upstream steps, but the table has `0` rows.
- `salesnav_prospects` is broken. Production has `35` successful prospect-producing steps, but the table has `0` rows. The most likely cause is context shape failure: successful `person.search.sales_nav_url` steps do not carry a usable `source_company_domain`, so the Trigger auto-persist branch never fires.
- `company_ads` exists in production (was missing in March 10) but has `0` rows.
- `fmcsa_carrier_signals` table exists but has `0` rows — signal detection has not populated it.
- End-to-end pipeline reliability is not clean. Pipelines frequently fail to complete cleanly due to silent auto-persist failures, context-shape issues, and the deploy-sequencing landmine between Railway and Trigger.dev.

### What Has Never Been Used

- `69` executable operations in the current code catalog have never been called in production:
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
  - `company.search.enigma.brands`
  - `company.search.enigma.aggregate`
  - `company.search.enigma.person`
  - `company.enrich.enigma.legal_entities`
  - `company.enrich.enigma.address_deliverability`
  - `company.enrich.enigma.technologies`
  - `company.enrich.enigma.industries`
  - `company.enrich.enigma.affiliated_brands`
  - `company.enrich.enigma.marketability`
  - `company.enrich.enigma.activity_flags`
  - `company.enrich.enigma.bankruptcy`
  - `company.enrich.enigma.watchlist`
  - `person.search.enigma.roles`
  - `person.enrich.enigma.profile`
  - `company.verify.enigma.kyb`
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
- Unused blueprints:
  - `AlumniGTM Prospect Resolution v1`
  - `Phase6 Blueprint 1771280001`
  - `Revenue Activation / CRM Cleanup v1`
  - `Revenue Activation / CRM Enrichment v1`
  - `Revenue Activation / Staffing Enrichment v1`
  - `Staffing Activation / CRM Cleanup v1`
  - `Staffing Activation / CRM Enrichment v1`
- Tables with zero production usage:
  - `extracted_icp_job_title_details` has `0` rows

### Known Architectural Problems

- See `docs/DATA_ENGINE_X_ARCHITECTURE.md`, section `7. Known Architectural Problems`, for the full list.
- Top 3 problems (being addressed across current migration and reliability workstreams):
  - auto-persist silent failures: the legacy `run-pipeline.ts` wraps dedicated-table writes in try/catch and swallows failures. Dedicated workflows use confirmed writes that surface failures. Standalone `/api/v1/execute` with `persist: true` now also surfaces persistence errors in the response (implemented 2026-03-18). The `run-pipeline.ts` auto-persist silent failures remain unresolved.
  - `run-pipeline.ts` monolith: being replaced by dedicated workflow files with shared utilities. Do NOT add to `run-pipeline.ts`.
  - deploy-sequencing landmine: Railway must be live before Trigger.dev deploys, or new Trigger code calls internal FastAPI endpoints that do not exist yet. Exception: the fan-out router deploy reverses this order (Trigger first, then Railway).

## Diagnostic Reports

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` - live production state audit
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` - full architecture doc including known problems
- `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` - auth paths and data visibility model; grounded in code; supersedes AUTH_MODEL.md for technical detail
- `docs/PERSISTENCE_MODEL.md` - full persistence audit; 9 data loss risks; read before any persistence work
- `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` - analysis of globalizing entity model; 13 sections; recommendation: hybrid approach deferred pending 4 prerequisites

If `CLAUDE.md` or `docs/SYSTEM_OVERVIEW.md` conflict with these reports, the reports are correct.

## Repo Workstreams In Docs

Do not infer the current project picture from an older subset of directives.

The repo's recent documentation spans multiple workstream families, including:

- dedicated workflow migration and fan-out routing
- schema split work plus post-split verification
- production reliability and runtime/deploy investigations
- FMCSA ingestion and mapping across multiple feed families
- newer workflow families such as job-posting-led discovery

Those workstreams may exist as directives, mapping docs, or in-repo implementation. Their presence does not by itself prove production completion.

## Entity Database Design

Read `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` before any schema work on entity tables.

## Project Overview

`data-engine-x-api` is a multi-tenant enrichment backend. It accepts operation and batch requests, executes deterministic provider-backed steps through Trigger.dev, and persists execution lineage plus canonical entity intelligence.

## Tech Stack

- **FastAPI (Python):** auth, API contracts, persistence, Trigger task triggering, internal callbacks.
- **Trigger.dev (TypeScript):** pipeline orchestration, cumulative context chaining, fail-fast behavior, fan-out child-run orchestration.
- **Supabase/Postgres:** tenancy, submissions/runs/step results, operation audit, entity state, timeline.

## Python vs TypeScript Boundary

- **FastAPI owns:** auth resolution, tenant checks, request validation, DB reads/writes, `/api/v1/*`, `/api/internal/*`.
- **Trigger owns:** `run-pipeline` task execution flow, per-step calls to `/api/v1/execute`, retries/failure propagation, fan-out continuation.
- Boundary is internal HTTP with service auth.

## Core Concepts

1. **Operations (`/api/v1/execute`)**: canonical operation IDs call provider adapters and return canonical output + provider attempts.
2. **Batch orchestration (`/api/v1/batch/submit`, `/api/v1/batch/status`)**: creates submission and root pipeline runs, then aggregates status/results.
3. **Fan-out**: operation steps can create child pipeline runs (`parent_pipeline_run_id`) and continue execution from a later step position.
4. **Entity state accumulation**: succeeded runs upsert canonical records into `company_entities` / `person_entities` / `job_posting_entities`.
5. **Entity timeline**: upserts and fan-out discoveries emit timeline events into `entity_timeline`.
6. **Output chaining**: each succeeded step merges `result.output` into cumulative context for the next step.

## Auth & Multi-Tenancy

See `docs/AUTH_MODEL.md`.

## API Surface

See `docs/API_SURFACE.md`.

## Deploy Protocol, Commands & Migrations

See `docs/DEPLOY_PROTOCOL.md`.

## Trigger.dev Conventions

- Tasks live in `trigger/src/tasks/`.
- Shared workflow utilities live in `trigger/src/` (internal HTTP client, confirmed writes, context merge, Parallel.ai polling).
- Parallel.ai prompt templates are extracted into standalone files under `trigger/src/` (not hardcoded in task files).
- `run-pipeline.ts` is the legacy generic orchestrator. It is being replaced by dedicated workflow files — one task per pipeline. Do NOT modify `run-pipeline.ts` for new work.
- A fan-out router task sits between the DB-backed fan-out path and the dedicated workflows. It receives generic fan-out payloads, determines the target workflow, translates the payload, and triggers the correct task. Falls back to `run-pipeline` for unmigrated pipelines.
- Generic `execute-step` remains legacy and is not used.

## Environment Configuration

- App settings use non-prefixed env names (for example `DATABASE_URL`, `INTERNAL_API_KEY`, `LEADMAGIC_API_KEY`).
- `REVENUEINFRA_INGEST_API_KEY` — API key data-engine-x uses to authenticate against HQ ingest/validation endpoints (same value as `INGEST_API_KEY` in HQ).
- `RAPIDAPI_SALESNAV_SCRAPE_API_KEY` — API key for RapidAPI Sales Navigator scraper (alumni search).
- `PARALLEL_API_KEY` — API key for Parallel.ai Deep Research (set in Trigger.dev env vars, NOT in Doppler/Railway — this operation runs directly from Trigger.dev).
- Trigger task runtime supports `DATA_ENGINE_API_URL` / `DATA_ENGINE_INTERNAL_API_KEY` fallback in `run-pipeline.ts`.
- Docker runtime injects secrets via Doppler (`CMD ["doppler", "run", "--", ...]` in `Dockerfile`).
- Railway only needs `DOPPLER_TOKEN`; Doppler provides the rest at runtime.

## HQ Integration (api.revenueinfra.com)

data-engine-x calls HQ endpoints for:
- **Research lookups**: competitors, customers, alumni, champions, VC funding, similar companies, SEC filings
- **CRM resolution**: domain from email/LinkedIn/name, LinkedIn from domain, person LinkedIn from email, location from domain (6 `/single` endpoints)
- **Job validation**: Bright Data cross-source check (`/api/ingest/brightdata/validate-job`)
- **Sales Nav templates**: client-specific Sales Nav URL templates (`/api/hq/clients/salesnav-template`)

HQ is read-only from data-engine-x's perspective. data-engine-x never writes to HQ's DB.

## Live Orgs

| Org | ID | Companies |
|---|---|---|
| Staffing Activation | `58203c4a-1654-42f8-8486-bd37016223a5` | Sales Talent (`6749b0b9-3e9a-4382-8e4d-353771ef78d4`, domain: salestalent.inc) |
| Revenue Activation | `d319a533-356a-4592-bd7a-b79dd4d27802` | — |
| AlumniGTM | `b0293785-aa7a-4234-8201-cc47305295f8` | global (`8cc8b8f3-fc26-49eb-992b-abe8cb46ec53`, domain: global.alumnigtm.com) |
| Substrate | `7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19` | — |

## Directory Structure

- `app/`
  - `app/providers/` — provider adapters (prospeo, blitzapi, enigma, theirstack, revenueinfra/, etc.)
    - includes HQ workflow `/run/` adapters for `infer_linkedin_url`, `icp_job_titles_gemini`, `discover_customers_gemini`, `icp_criterion`, `salesnav_url`, `evaluate_icp_fit`
  - `app/contracts/` — Pydantic output models
  - `app/services/` — operation service functions
    - `app/services/hq_workflow_operations.py` — HQ workflow operation services (6 RevenueInfra-backed workflow ops)
    - `app/services/persistence_routing.py` — DEDICATED_TABLE_REGISTRY and persist_standalone_result() for standalone execute persistence
    - `app/services/enigma_brand_discoveries.py` — array-capable upsert service for Enigma brand discovery results
    - `app/services/enigma_location_enrichments.py` — array-capable upsert service for Enigma location enrichment results
  - `app/routers/execute_v1.py` — operation dispatch + SUPPORTED_OPERATION_IDS
  - `app/routers/entities_v1.py` — entity query endpoints (companies, persons, job-postings, timeline)
  - `app/services/entity_state.py` — entity upsert + identity resolution (company, person, job)
  - `app/services/entity_timeline.py` — timeline event recording
  - `app/services/resolve_operations.py` — 7 CRM resolve operations
- `trigger/`
  - `trigger/src/tasks/run-pipeline.ts` — legacy generic pipeline runner (being replaced by dedicated workflows)
  - `trigger/src/tasks/` — dedicated workflow files and ingestion tasks, including company enrichment, person search/enrichment, ICP job titles, company intel briefing, person intel briefing, fan-out router, TAM building, FMCSA feed ingestion, newer workflow families, and `enigma-smb-discovery.ts` (dedicated Enigma SMB discovery workflow with confirmed writes)
  - `trigger/src/` — shared workflow utilities (internal HTTP, confirmed writes, context merge, Parallel.ai polling, prompt templates)
- `tests/`
- `scripts/` — backfill scripts for dedicated tables (icp_job_titles, company/person intel briefings)
- `supabase/migrations/`
- `docs/`
  - `docs/blueprints/` — blueprint definition JSON files, including `enigma_smb_discovery_v1.json` (Substrate org, 3 steps)
  - `docs/EXECUTOR_DIRECTIVE_*.md` — executor agent directives (documentation)
  - `docs/FMCSA_*.md` — FMCSA contract-lock and mapping docs for current ingestion workstreams
  - `docs/directives-hq/` — directives for HQ database work (job title matching, dedup)
  - `docs/troubleshooting-fixes/` — incident post-mortems and fixes
  - `docs/api-reference-docs/` — provider API documentation (Enigma, Parallel.ai)
  - `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` — auth paths, data visibility by auth type, practical access examples; grounded in code
  - `docs/PERSISTENCE_MODEL.md` — full persistence audit, 9 data loss risks, persistence decision tree
  - `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference from 61 source files
  - `docs/GLOBAL_DATA_MODEL_ANALYSIS.md` — analysis of moving from org-scoped to global entity model
- `Dockerfile`
