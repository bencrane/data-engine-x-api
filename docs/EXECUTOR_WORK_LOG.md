# Executor Work Log

**Last updated:** 2026-03-18T22:30:00Z

Reverse-chronological log of completed executor directive work.

---

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_PERSISTENCE_MODEL_AUDIT.md`
**Summary:** Created `docs/PERSISTENCE_MODEL.md` — 10 sections covering: persistence overview (layered diagram of all write paths), standalone operation execution (operation_runs + operation_attempts, no entity upsert), pipeline execution persistence (batch submit upfront rows, per-step updates, entity state upsert at pipeline end only, 9 auto-persist branches with try/catch swallowing), confirmed writes vs auto-persist comparison (with production evidence), cumulative context durability (volatile — in-memory only, but snapshots stored in step_results.output_payload), array and multi-entity handling (fan-out required for entity materialization), fan-out persistence model, data loss risk inventory (9 risks enumerated), persistence decision tree for new operations, and table-level persistence reference (27+ tables with reliability ratings and production row counts). Traced 15+ source files with line-number references. Cross-referenced all claims against OPERATIONAL_REALITY_CHECK_2026-03-18.
**Flagged:** Cumulative context is volatile (in-memory only) but recoverable from step_results.output_payload snapshots — no automated recovery exists. Entity state upsert happens once at pipeline END, not per-step — mid-pipeline crashes lose all entity-level persistence from earlier steps. 4 dedicated tables have 0 production rows due to auto-persist silent failures: company_customers, gemini_icp_job_titles, salesnav_prospects, company_ads. salesnav_prospects has a context-shape failure where the auto-persist guard checks for `sourceCompanyDomain` which upstream steps don't provide. Entity relationships are NOT recorded by run-pipeline.ts — all 1,892 rows come from Clay ingestion and fan-out. Timeline events are explicitly best-effort (never raises).

---

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_ENIGMA_API_REFERENCE.md`
**Summary:** Created `docs/ENIGMA_API_REFERENCE.md` consolidating 61 source files from `docs/api-reference-docs/enigma/` into a single actionable reference. 9 sections covering: platform overview, data model (3 core entity types + 4 supporting types with full relationship hierarchy), authentication and rate limits (4 plan tiers), credit/billing model (4 pricing tiers with cost estimation examples), GraphQL endpoint inventory (10 capability domains: search, brand retrieval, operating location data with 20 attribute domains, aggregates, card revenue analytics, person data, KYB verification, screening, enrichment, directives), coverage gap matrix (19 capabilities assessed — 3 with adapters, 16 not built), 4 use case query chains (SMB list building, location-level analysis, vertical discovery, competitive intelligence) with estimated credit costs and query shapes, GraphQL schema quick reference (10 major types, 16 filter operators, pagination patterns), and error handling. 20 files in `09-operating-location/` were empty (0 bytes) — operating location details derived from GraphQL SDL and attribute reference instead. 1 file in `02-verification-and-kyb/` was a duplicate (`02-kyb-api-quickstart.md` contained same content as `03-kyb-response-task-results.md`). MCP tools section flagged `search_negative_news` and `search_gov_archive` as capabilities not documented in the core GraphQL API reference.
**Flagged:** `09-operating-location/` (20 files, all 0 bytes) — entire subdirectory is placeholder stubs, never populated with content. `02-kyb-api-quickstart.md` is a duplicate of `03-kyb-response-task-results.md` — actual KYB quickstart content (endpoint URL, request body shape) is missing from the source docs. `search_negative_news` and `search_gov_archive` MCP tools expose capabilities with no corresponding GraphQL API documentation — these may be separate REST endpoints. The `enrich` GraphQL query and `OperatingLocationCache` type are present in the SDL but have insufficient documentation for integration — need live API verification.

---

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_ENIGMA_INTEGRATION_AUDIT.md`
**Summary:** Created `docs/ENIGMA_INTEGRATION_AUDIT.md` covering 8 sections: Enigma API surface inventory (~15 distinct capabilities across GraphQL, KYB, screening, MCP), provider adapter analysis (3 functions: `match_business`, `get_card_analytics`, `get_brand_locations`), operation wiring (2 operations: `company.enrich.card_revenue` and `company.enrich.locations`), Trigger.dev integration status (none), gap analysis (documented vs built vs wired vs called), credential configuration (`ENIGMA_API_KEY` via `app/config.py`), rate limits and credit pricing model, and prioritized recommendations. Key finding: of ~15 documented capabilities, only 2 are built into operations — the vast majority of Enigma's API surface (KYB, screening, legal entities, person data, semantic search, aggregate queries, per-location analytics) has no adapter code.
**Flagged:** `company.enrich.card_revenue` has been called in production (not in never-called list), confirming `ENIGMA_API_KEY` is configured. `company.enrich.locations` is fully built and tested but has never been called. No Trigger.dev integration or blueprint references exist for either Enigma operation — both are only reachable via ad-hoc `/api/v1/execute` calls. No retry or rate-limit handling in the adapter; 429 responses are treated as generic failures.

---

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_ANALYTICAL_MATERIALIZED_VIEWS.md`
**Summary:** Created migrations 038-040 adding analytical materialized views and supplemental indexes. Migration 038 adds two USASpending MVs: `mv_usaspending_contracts_typed` (28 columns, pre-cast from TEXT to proper types with DISTINCT ON dedup) and `mv_usaspending_first_contracts` (first contract per recipient_uei for first-time awardee analysis). Migration 039 adds four FMCSA MVs: `mv_fmcsa_latest_census` (latest snapshot per carrier), `mv_fmcsa_latest_safety_percentiles` (latest percentiles per carrier), `mv_fmcsa_crash_counts_12mo` (trailing 12-month crash aggregation), and `mv_fmcsa_carrier_master` (master join of all three). Migration 040 adds 4 composite indexes across USASpending, SAM.gov, and SBA tables after auditing all 18 FMCSA tables (no gaps found). Created `scripts/refresh_analytical_views.sql` covering 9 total MVs with dependency ordering. Updated DEPLOY_PROTOCOL.md with migrations 038-040.
**Flagged:** Column name mismatches vs directive: `small_business_competitive_flag` does not exist — used `contracting_officers_determination_of_business_size` (TEXT) instead. `place_of_performance_state_code` is actually `primary_place_of_performance_state_code`. Directive suggested `awarding_agency_name` index on base usaspending_contracts but existing index is on `awarding_agency_code` — both the MV index and composite index use `awarding_agency_name`. Migrations 036/037 (FMCSA authority grants and insurance cancellations) still not applied to production per operational reality check — refresh script includes them with a note.

---

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_DATA_ACCESS_AND_AUTH_GUIDE.md`
**Summary:** Created `docs/DATA_ACCESS_AND_AUTH_GUIDE.md` covering 4 auth types (tenant JWT, tenant API token, super-admin key/JWT, internal service auth), data visibility by auth context, connection patterns for 4 client types (frontend, notebook/Hex, script, Trigger.dev), 5 write paths (batch submit, single execute, internal callbacks, Clay ingest, FMCSA feed ingest), credential disambiguation table, schema/table scoping reference (46 tables: 24 org-scoped, 22+ global), and 6 practical curl examples. All claims traced to actual code paths.
**Flagged:** Auth gap: `/api/v1/entities/companies` and `/api/v1/entities/persons` use `get_current_auth` instead of `_resolve_flexible_auth`, so super-admin API key/JWT cannot query these two endpoints (all other entity endpoints accept super-admin). Internal auth produces `auth_method="api_token"` making it indistinguishable from tenant API tokens in audit logs. AUTH_MODEL.md does not mention super-admin JWT path (only API key), but code supports both.

## 2026-03-18
**Directive:** Migration list update (standalone fix)
**Summary:** Updated docs/DEPLOY_PROTOCOL.md migration list from 020 to 037, adding 17 missing migrations covering schema split, FMCSA tables, federal data tables, materialized views, and supporting infrastructure.
**Flagged:** Nothing.

## 2026-03-18
**Directive:** CLAUDE.md Restructure and Repo Convention Files
**Summary:** Broke CLAUDE.md into slim routing doc plus 3 breakout files (AUTH_MODEL.md, API_SURFACE.md, DEPLOY_PROTOCOL.md). Merged Chief Agent Rules into CHIEF_AGENT_DIRECTIVE.md. Created REPO_CONVENTIONS.md and EXECUTOR_WORK_LOG.md. Updated CHIEF_AGENT_DOC_AUTHORITY_MAP.md and WRITING_EXECUTOR_DIRECTIVES.md to reference new files and work log standard.
**Flagged:** Core Concepts section kept in CLAUDE.md rather than moved to AUTH_MODEL.md — it describes pipeline behavior, not auth, so it belongs in the project overview area.

## 2026-03-18
**Directive:** `docs/EXECUTOR_DIRECTIVE_OPERATIONAL_REALITY_CHECK_REFRESH_2026-03-18.md`
**Summary:** Fresh production audit covering ops + entities schemas, 18 FMCSA tables (75.8M rows), federal data tables (SAM.gov, SBA, USASpending). Updated CLAUDE.md production state section and 5 cross-reference docs. Schema split from public to ops/entities confirmed live.
**Flagged:** Two FMCSA materialized views missing (migrations 036/037 not applied). No pipeline orchestration activity since March 4 — all growth from external ingestion paths. SMS safety feeds lagging 4 days behind other FMCSA feeds.
