-- Migration 042: Analytical MV Expansion — SAM.gov, SBA, Cross-Vertical, FMCSA Gaps
--
-- Creates 8 new materialized views:
--   1. mv_sam_gov_entities_typed        — typed base for sam_gov_entities (TEXT → DATE casts)
--   2. mv_sam_gov_entities_by_state     — aggregate by physical state
--   3. mv_sam_gov_entities_by_naics     — aggregate by primary NAICS code
--   4. mv_sba_loans_typed               — typed base for sba_7a_loans (TEXT → NUMERIC/DATE casts)
--   5. mv_sba_loans_by_state            — aggregate by borrower state with loan amounts
--   6. mv_sam_usaspending_bridge        — cross-vertical: SAM.gov entities × USASpending contracts
--   7. mv_fmcsa_latest_insurance_policies — active (non-removal) insurance policies per docket
--   8. mv_fmcsa_new_carriers_90d        — carriers added within the last 90 days
--
-- Dependency order:
--   mv_sam_gov_entities_typed (base) must exist before mv_sam_usaspending_bridge
--   All other MVs are independent of each other
--
-- NOTE: No BEGIN/COMMIT wrapper. MV population scans are too heavy for Supabase's
-- default statement_timeout inside a transaction.
--
-- Runtime estimate: this migration is HEAVY. Flag for chief agent.
--   - mv_sam_gov_entities_typed: ~867K rows — fast (< 2 min)
--   - mv_sam_gov_entities_by_state: ~57 rows — trivial
--   - mv_sam_gov_entities_by_naics: ~480 rows — trivial
--   - mv_sba_loans_typed: ~356K rows — fast (< 2 min)
--   - mv_sba_loans_by_state: ~57 rows — trivial
--   - mv_sam_usaspending_bridge: ~118K rows — hash join of 867K × 14.7M (already MV) — 5–15 min
--   - mv_fmcsa_latest_insurance_policies: ~1.4M rows — moderate (2–5 min)
--   - mv_fmcsa_new_carriers_90d: ~16K rows — fast (< 2 min, reads from 3.2M row table)
--
-- Run during a low-traffic window. Railway deploy is NOT required before this migration.

SET statement_timeout = '0';

-- ============================================================
-- View 1: entities.mv_sam_gov_entities_typed
-- Refresh: weekly, or after SAM.gov ingestion
-- Source: entities.sam_gov_entities (867K rows, mostly TEXT)
-- Purpose: typed base with DATE casts for date columns and
--          extracted NAICS sector prefix columns for targeting
--
-- SAM.gov column name notes (verified against production):
--   Registration status column is sam_extract_code (A=active, E=expired/inactive)
--   State column is physical_address_province_or_state
--   NAICS column is primary_naics (6-digit TEXT)
--   Date columns are TEXT in YYYYMMDD format (e.g., 20070323)
--   Single extract_date (2026-03-01) — no multi-snapshot dedup needed
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sam_gov_entities_typed CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sam_gov_entities_typed AS
SELECT
    -- Identity / join keys
    id,
    unique_entity_id,
    cage_code,

    -- Entity name
    legal_business_name,
    dba_name,

    -- Registration status (A=active, E=expired/inactive)
    sam_extract_code,
    purpose_of_registration,

    -- Date columns cast from TEXT (format: YYYYMMDD) to DATE
    NULLIF(initial_registration_date, '')::DATE     AS initial_registration_date_cast,
    NULLIF(registration_expiration_date, '')::DATE  AS registration_expiration_date_cast,
    NULLIF(last_update_date, '')::DATE              AS last_update_date_cast,
    NULLIF(activation_date, '')::DATE               AS activation_date_cast,
    NULLIF(entity_start_date, '')::DATE             AS entity_start_date_cast,
    NULLIF(fiscal_year_end_close_date, '')::DATE    AS fiscal_year_end_close_date_cast,

    -- Keep extract_date native (already DATE type)
    extract_date,

    -- NAICS — 6-digit code plus extracted sector prefixes for grouping
    primary_naics,
    LEFT(primary_naics, 2) AS naics_sector,
    LEFT(primary_naics, 3) AS naics_subsector,

    -- Geography
    physical_address_province_or_state  AS physical_state,
    physical_address_city               AS physical_city,
    physical_address_zippostal_code     AS physical_zip,
    physical_address_country_code       AS physical_country,
    physical_address_congressional_district AS congressional_district,

    -- Business characteristics
    entity_structure,
    state_of_incorporation,
    country_of_incorporation,
    bus_type_string,
    sba_business_types_string,
    debt_subject_to_offset_flag,
    exclusion_status_flag,

    -- Web
    entity_url,

    -- Ingestion metadata
    ingested_at,
    created_at,
    updated_at
FROM entities.sam_gov_entities
WHERE unique_entity_id IS NOT NULL AND unique_entity_id != '';

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_sam_typed_uei
    ON entities.mv_sam_gov_entities_typed (unique_entity_id);

CREATE INDEX idx_mv_sam_typed_state
    ON entities.mv_sam_gov_entities_typed (physical_state);

CREATE INDEX idx_mv_sam_typed_naics
    ON entities.mv_sam_gov_entities_typed (primary_naics);

CREATE INDEX idx_mv_sam_typed_naics_sector
    ON entities.mv_sam_gov_entities_typed (naics_sector);

CREATE INDEX idx_mv_sam_typed_expiration
    ON entities.mv_sam_gov_entities_typed (registration_expiration_date_cast);

CREATE INDEX idx_mv_sam_typed_status
    ON entities.mv_sam_gov_entities_typed (sam_extract_code);

-- ============================================================
-- View 2: entities.mv_sam_gov_entities_by_state
-- Refresh: weekly, or after SAM.gov ingestion
-- Source: entities.sam_gov_entities
-- Purpose: entity count by registration state for geographic targeting
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sam_gov_entities_by_state CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sam_gov_entities_by_state AS
SELECT
    physical_address_province_or_state AS physical_state,
    COUNT(*)                           AS total_entities,
    COUNT(*) FILTER (WHERE sam_extract_code = 'A') AS active_entities,
    COUNT(*) FILTER (WHERE sam_extract_code = 'E') AS expired_entities
FROM entities.sam_gov_entities
GROUP BY physical_address_province_or_state;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_sam_state_agg_state
    ON entities.mv_sam_gov_entities_by_state (physical_state);

-- ============================================================
-- View 3: entities.mv_sam_gov_entities_by_naics
-- Refresh: weekly, or after SAM.gov ingestion
-- Source: entities.sam_gov_entities
-- Purpose: entity count by primary NAICS code for vertical targeting
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sam_gov_entities_by_naics CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sam_gov_entities_by_naics AS
SELECT
    primary_naics,
    LEFT(primary_naics, 2) AS naics_sector,
    LEFT(primary_naics, 3) AS naics_subsector,
    COUNT(*)               AS total_entities,
    COUNT(*) FILTER (WHERE sam_extract_code = 'A') AS active_entities
FROM entities.sam_gov_entities
WHERE primary_naics IS NOT NULL AND primary_naics != ''
GROUP BY primary_naics;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_sam_naics_agg_naics
    ON entities.mv_sam_gov_entities_by_naics (primary_naics);

CREATE INDEX idx_mv_sam_naics_agg_sector
    ON entities.mv_sam_gov_entities_by_naics (naics_sector);

-- ============================================================
-- View 4: entities.mv_sba_loans_typed
-- Refresh: weekly, or after SBA ingestion
-- Source: entities.sba_7a_loans (356K rows, mostly TEXT)
-- Purpose: typed base with NUMERIC loan amounts and DATE casts
--
-- SBA column name notes (verified against production):
--   Loan amount column is grossapproval (TEXT, format: integer string e.g. "2138000")
--   Guaranteed amount column is sbaguaranteedapproval (TEXT)
--   Borrower state column is borrstate
--   Approval date column is approvaldate (TEXT, format: M/D/YYYY e.g. "7/18/2020")
--   Term column is terminmonths (TEXT integer string)
--   Single extract_date (2025-12-31) — no multi-snapshot dedup needed
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sba_loans_typed CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sba_loans_typed AS
SELECT
    id,

    -- Loan identity
    program,
    subprogram,
    processingmethod,

    -- Borrower
    borrname,
    borrstreet,
    borrcity,
    borrstate,
    borrzip,
    businesstype,
    businessage,

    -- Lender
    bankname,
    bankstate,

    -- NAICS
    naicscode,
    naicsdescription,
    LEFT(naicscode, 2) AS naics_sector,

    -- Loan amounts cast from TEXT to NUMERIC
    NULLIF(grossapproval, '')::NUMERIC              AS grossapproval_numeric,
    NULLIF(sbaguaranteedapproval, '')::NUMERIC      AS sbaguaranteedapproval_numeric,
    NULLIF(grosschargeoffamount, '')::NUMERIC       AS grosschargeoffamount_numeric,

    -- Loan terms
    NULLIF(terminmonths, '')::INTEGER               AS terminmonths_int,
    NULLIF(jobssupported, '')::INTEGER              AS jobssupported_int,
    NULLIF(approvalfiscalyear, '')::INTEGER         AS approvalfiscalyear_int,
    initialinterestrate,
    fixedorvariableinterestind,

    -- Dates cast from TEXT (format: M/D/YYYY) to DATE
    NULLIF(approvaldate, '')::DATE                  AS approvaldate_cast,
    NULLIF(firstdisbursementdate, '')::DATE         AS firstdisbursementdate_cast,
    NULLIF(paidinfulldate, '')::DATE                AS paidinfulldate_cast,
    NULLIF(chargeoffdate, '')::DATE                 AS chargeoffdate_cast,

    -- Loan status and flags
    loanstatus,
    collateralind,
    soldsecmrktind,
    revolverstatus,

    -- Geography
    projectstate,
    projectcounty,
    sbadistrictoffice,
    congressionaldistrict,

    -- Franchise
    franchisecode,
    franchisename,

    -- Extract metadata
    extract_date,
    ingested_at,
    created_at,
    updated_at
FROM entities.sba_7a_loans;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
-- No single unique column in SBA data; use composite near-key matching the source table's
-- unique constraint (uq_sba_7a_loans_extract_date_composite)
CREATE UNIQUE INDEX idx_mv_sba_typed_composite_key
    ON entities.mv_sba_loans_typed (extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval_numeric);

CREATE INDEX idx_mv_sba_typed_state
    ON entities.mv_sba_loans_typed (borrstate);

CREATE INDEX idx_mv_sba_typed_naics
    ON entities.mv_sba_loans_typed (naicscode);

CREATE INDEX idx_mv_sba_typed_approval_date
    ON entities.mv_sba_loans_typed (approvaldate_cast);

CREATE INDEX idx_mv_sba_typed_gross
    ON entities.mv_sba_loans_typed (grossapproval_numeric);

CREATE INDEX idx_mv_sba_typed_status
    ON entities.mv_sba_loans_typed (loanstatus);

-- ============================================================
-- View 5: entities.mv_sba_loans_by_state
-- Refresh: weekly, or after SBA ingestion
-- Source: entities.sba_7a_loans
-- Purpose: aggregate loan count and volume by borrower state for geographic targeting
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sba_loans_by_state CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sba_loans_by_state AS
SELECT
    borrstate,
    COUNT(*)                                      AS loan_count,
    SUM(NULLIF(grossapproval, '')::NUMERIC)       AS total_gross_approval,
    AVG(NULLIF(grossapproval, '')::NUMERIC)       AS avg_gross_approval,
    COUNT(*) FILTER (WHERE loanstatus = 'EXEMPT') AS active_loan_count,
    COUNT(*) FILTER (WHERE loanstatus = 'PIF')    AS paid_in_full_count,
    COUNT(*) FILTER (WHERE loanstatus = 'CHGOFF') AS charged_off_count
FROM entities.sba_7a_loans
WHERE grossapproval IS NOT NULL AND grossapproval ~ '^[0-9]'
GROUP BY borrstate;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_sba_state_agg_state
    ON entities.mv_sba_loans_by_state (borrstate);

-- ============================================================
-- View 6: entities.mv_sam_usaspending_bridge
-- Refresh: weekly (after both SAM.gov and USASpending are refreshed)
-- Source: entities.mv_sam_gov_entities_typed + entities.mv_usaspending_contracts_typed
-- Purpose: cross-vertical join pre-computing contract history per registered SAM.gov entity
--
-- DEPENDS ON: mv_sam_gov_entities_typed (created above in this migration)
--             mv_usaspending_contracts_typed (from migration 038)
--
-- Join key: sam_gov_entities.unique_entity_id = usaspending_contracts.recipient_uei
--   Confirmed in production: 118,422 distinct SAM.gov UEIs match USASpending records
--   (out of 867,137 SAM.gov entities = ~13.6% match rate)
--
-- Runtime warning: hash join of 118K SAM entities × 14.7M USASpending rows (MV)
-- with recipient_uei index. Estimated 5–15 min. Run during low-traffic window.
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_sam_usaspending_bridge CASCADE;

CREATE MATERIALIZED VIEW entities.mv_sam_usaspending_bridge AS
SELECT
    -- SAM.gov entity identity
    sam.unique_entity_id,
    sam.cage_code,
    sam.legal_business_name,
    sam.dba_name,
    sam.sam_extract_code,
    sam.physical_state,
    sam.physical_city,
    sam.physical_zip,
    sam.primary_naics,
    sam.naics_sector,
    sam.entity_url,
    sam.entity_structure,
    sam.sba_business_types_string,

    -- USASpending aggregate per entity
    COUNT(usa.contract_transaction_unique_key)  AS total_contract_transactions,
    COUNT(DISTINCT usa.contract_award_unique_key) AS total_distinct_awards,
    SUM(usa.total_dollars_obligated)            AS total_obligated_dollars,
    MIN(usa.action_date)                        AS first_contract_date,
    MAX(usa.action_date)                        AS latest_contract_date,
    MODE() WITHIN GROUP (ORDER BY usa.awarding_agency_name) AS top_awarding_agency,
    COUNT(DISTINCT usa.naics_code)              AS distinct_naics_codes_count,
    COUNT(DISTINCT usa.recipient_state_code)    AS distinct_perf_states_count
FROM entities.mv_sam_gov_entities_typed sam
INNER JOIN entities.mv_usaspending_contracts_typed usa
    ON sam.unique_entity_id = usa.recipient_uei
WHERE usa.total_dollars_obligated IS NOT NULL
GROUP BY
    sam.unique_entity_id,
    sam.cage_code,
    sam.legal_business_name,
    sam.dba_name,
    sam.sam_extract_code,
    sam.physical_state,
    sam.physical_city,
    sam.physical_zip,
    sam.primary_naics,
    sam.naics_sector,
    sam.entity_url,
    sam.entity_structure,
    sam.sba_business_types_string;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_sam_usa_bridge_uei
    ON entities.mv_sam_usaspending_bridge (unique_entity_id);

CREATE INDEX idx_mv_sam_usa_bridge_state
    ON entities.mv_sam_usaspending_bridge (physical_state);

CREATE INDEX idx_mv_sam_usa_bridge_naics
    ON entities.mv_sam_usaspending_bridge (primary_naics);

CREATE INDEX idx_mv_sam_usa_bridge_obligated
    ON entities.mv_sam_usaspending_bridge (total_obligated_dollars);

CREATE INDEX idx_mv_sam_usa_bridge_latest_contract
    ON entities.mv_sam_usaspending_bridge (latest_contract_date);

-- ============================================================
-- View 7: entities.mv_fmcsa_latest_insurance_policies
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.insurance_policies
-- Purpose: active (non-removal-signal) insurance posture per carrier docket
--
-- FMCSA insurance_policies notes (verified against production):
--   No usdot_number column — join key to other FMCSA tables is docket_number
--   is_removal_signal = FALSE means the record represents current active coverage
--   feed_date is native DATE; effective_date is native DATE
--   bipd_maximum_dollar_limit_thousands_usd is TEXT in source
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_latest_insurance_policies CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_latest_insurance_policies AS
SELECT
    id,
    feed_date,
    docket_number,
    insurance_type_code,
    insurance_type_description,
    bipd_class_code,
    NULLIF(bipd_maximum_dollar_limit_thousands_usd, '')::NUMERIC
        AS bipd_max_limit_thousands_usd,
    NULLIF(bipd_underlying_dollar_limit_thousands_usd, '')::NUMERIC
        AS bipd_underlying_limit_thousands_usd,
    policy_number,
    effective_date,
    form_code,
    insurance_company_name,
    source_feed_name,
    source_observed_at
FROM entities.insurance_policies
WHERE is_removal_signal = FALSE
  AND source_feed_name != 'test_feed';

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
-- Composite key: docket + type + policy_number (natural identifier per coverage record)
CREATE UNIQUE INDEX idx_mv_fmcsa_lip_docket_type_policy
    ON entities.mv_fmcsa_latest_insurance_policies (docket_number, insurance_type_code, policy_number);

CREATE INDEX idx_mv_fmcsa_lip_docket
    ON entities.mv_fmcsa_latest_insurance_policies (docket_number);

CREATE INDEX idx_mv_fmcsa_lip_feed_date
    ON entities.mv_fmcsa_latest_insurance_policies (feed_date);

CREATE INDEX idx_mv_fmcsa_lip_ins_type
    ON entities.mv_fmcsa_latest_insurance_policies (insurance_type_code);

CREATE INDEX idx_mv_fmcsa_lip_bipd_limit
    ON entities.mv_fmcsa_latest_insurance_policies (bipd_max_limit_thousands_usd);

-- ============================================================
-- View 8: entities.mv_fmcsa_new_carriers_90d
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.motor_carrier_census_records
-- Purpose: carriers registered within the last 90 days — high-value outbound signal
--
-- Uses same DISTINCT ON pattern as mv_fmcsa_latest_census.
-- add_date is native DATE type (confirmed in audit).
-- The 90-day window is applied at refresh time — the MV must be refreshed daily
-- to keep the window current.
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_new_carriers_90d CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_new_carriers_90d AS
SELECT DISTINCT ON (dot_number)
    dot_number,
    legal_name,
    dba_name,
    carrier_operation_code,
    physical_street,
    physical_city,
    physical_state,
    physical_zip,
    telephone,
    email_address,
    power_unit_count,
    driver_total,
    add_date,
    authorized_for_hire,
    hazmat_flag,
    passenger_carrier_flag,
    fleet_size_code,
    feed_date
FROM entities.motor_carrier_census_records
WHERE feed_date = (
    SELECT MAX(feed_date)
    FROM entities.motor_carrier_census_records
    WHERE source_feed_name != 'test_feed'
)
  AND source_feed_name != 'test_feed'
  AND add_date >= CURRENT_DATE - INTERVAL '90 days'
ORDER BY dot_number, row_position;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_nc90_dot
    ON entities.mv_fmcsa_new_carriers_90d (dot_number);

CREATE INDEX idx_mv_fmcsa_nc90_add_date
    ON entities.mv_fmcsa_new_carriers_90d (add_date);

CREATE INDEX idx_mv_fmcsa_nc90_state
    ON entities.mv_fmcsa_new_carriers_90d (physical_state);

CREATE INDEX idx_mv_fmcsa_nc90_op_code
    ON entities.mv_fmcsa_new_carriers_90d (carrier_operation_code);

-- Reset statement timeout to default
RESET statement_timeout;
