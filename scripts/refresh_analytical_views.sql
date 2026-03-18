-- =============================================================
-- Analytical Materialized View Refresh Script
-- =============================================================
-- Run with: doppler run -p data-engine-x-api -c prd -- psql -f scripts/refresh_analytical_views.sql
--
-- Refresh frequency guide:
--   DAILY (after FMCSA feed ingestion): FMCSA views
--   WEEKLY (or after USASpending backfill): USASpending views
--   WEEKLY: Federal contract leads view
--
-- Dependency order:
--   1. Latest-snapshot MVs first (census, safety, crashes)
--   2. Master carrier view second (depends on step 1)
--   3. Independent views in any order
-- =============================================================

SET statement_timeout = '0';

-- ---- DAILY: FMCSA latest-snapshot views (run after feed ingestion) ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_latest_census;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_latest_safety_percentiles;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_crash_counts_12mo;

-- depends on the three above
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_carrier_master;

-- existing FMCSA views (from migrations 036, 037)
-- NOTE: these depend on migrations 036/037 being applied. As of 2026-03-18, the
-- operational reality check notes these migrations have NOT been applied to production.
-- These lines will fail until those migrations are run.
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_authority_grants;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_insurance_cancellations;

-- ---- WEEKLY: USASpending views ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_usaspending_contracts_typed;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_usaspending_first_contracts;

-- ---- WEEKLY: Federal contract leads (existing, from migration 034) ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_federal_contract_leads;

RESET statement_timeout;
