# Executor Work Log

**Last updated:** 2026-03-18T16:00:00Z

Reverse-chronological log of completed executor directive work.

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
