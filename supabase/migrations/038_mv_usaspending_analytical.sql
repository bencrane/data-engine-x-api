-- Migration 038: USASpending Analytical Materialized Views
--
-- Creates two materialized views for interactive analytical queries from Hex/psql:
--   1. mv_usaspending_contracts_typed — pre-cast typed base (eliminates per-query TEXT casting)
--   2. mv_usaspending_first_contracts — first contract per recipient for first-time awardee analysis
--
-- NOTE: No BEGIN/COMMIT wrapper. The materialized view population is too heavy
-- for Supabase's default statement_timeout inside a transaction.

SET statement_timeout = '0';

-- ============================================================
-- View 1: entities.mv_usaspending_contracts_typed
-- Refresh: weekly, or after USASpending backfill ingestion
-- Source: entities.usaspending_contracts (14.6M+ rows, all TEXT)
-- Purpose: pre-cast typed base for analytical queries from Hex/psql
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_usaspending_contracts_typed CASCADE;

CREATE MATERIALIZED VIEW entities.mv_usaspending_contracts_typed AS
SELECT DISTINCT ON (contract_transaction_unique_key)
    -- Identity / join keys
    contract_transaction_unique_key,
    contract_award_unique_key,
    recipient_uei,
    recipient_name,
    recipient_parent_uei,
    recipient_parent_name,

    -- Agency
    awarding_agency_name,
    awarding_sub_agency_name,
    funding_agency_name,

    -- Industry
    naics_code,
    naics_description,
    product_or_service_code,
    product_or_service_code_description,

    -- Dollar amounts (cast from TEXT to NUMERIC)
    NULLIF(federal_action_obligation, '')::NUMERIC AS federal_action_obligation,
    NULLIF(total_dollars_obligated, '')::NUMERIC AS total_dollars_obligated,
    NULLIF(base_and_exercised_options_value, '')::NUMERIC AS base_and_exercised_options_value,
    NULLIF(current_total_value_of_award, '')::NUMERIC AS current_total_value_of_award,

    -- Dates (cast from TEXT to DATE)
    NULLIF(action_date, '')::DATE AS action_date,
    NULLIF(period_of_performance_start_date, '')::DATE AS period_of_performance_start_date,
    NULLIF(period_of_performance_current_end_date, '')::DATE AS period_of_performance_current_end_date,

    -- Award classification
    award_type,
    type_of_contract_pricing,

    -- Recipient geography
    recipient_city_name,
    recipient_state_code,
    recipient_country_code,

    -- Performance geography
    primary_place_of_performance_state_code,

    -- Business size (TEXT — source column is small_business_competitiveness_demonstration_program, not a boolean flag)
    contracting_officers_determination_of_business_size,

    -- Extract metadata
    extract_date::DATE AS extract_date
FROM entities.usaspending_contracts
WHERE contract_transaction_unique_key IS NOT NULL AND contract_transaction_unique_key != ''
ORDER BY contract_transaction_unique_key, extract_date DESC;

-- Indexes on mv_usaspending_contracts_typed

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_usa_typed_txn_key
    ON entities.mv_usaspending_contracts_typed (contract_transaction_unique_key);

CREATE INDEX idx_mv_usa_typed_recipient_uei
    ON entities.mv_usaspending_contracts_typed (recipient_uei);

CREATE INDEX idx_mv_usa_typed_action_date
    ON entities.mv_usaspending_contracts_typed (action_date);

CREATE INDEX idx_mv_usa_typed_agency
    ON entities.mv_usaspending_contracts_typed (awarding_agency_name);

CREATE INDEX idx_mv_usa_typed_naics
    ON entities.mv_usaspending_contracts_typed (naics_code);

CREATE INDEX idx_mv_usa_typed_state
    ON entities.mv_usaspending_contracts_typed (recipient_state_code);

CREATE INDEX idx_mv_usa_typed_obligation
    ON entities.mv_usaspending_contracts_typed (federal_action_obligation);

-- ============================================================
-- View 2: entities.mv_usaspending_first_contracts
-- Refresh: weekly, or after USASpending backfill ingestion
-- Purpose: first contract per recipient for first-time awardee analysis
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_usaspending_first_contracts CASCADE;

CREATE MATERIALIZED VIEW entities.mv_usaspending_first_contracts AS
SELECT
    recipient_uei,
    MIN(NULLIF(action_date, '')::DATE) AS first_contract_date,
    (array_agg(awarding_agency_name ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_agency,
    (array_agg(naics_code ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_naics,
    (array_agg(contract_award_unique_key ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_award_key,
    COUNT(DISTINCT contract_award_unique_key) AS total_awards
FROM entities.usaspending_contracts
WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
GROUP BY recipient_uei;

-- Indexes on mv_usaspending_first_contracts

CREATE UNIQUE INDEX idx_mv_usa_first_uei
    ON entities.mv_usaspending_first_contracts (recipient_uei);

CREATE INDEX idx_mv_usa_first_date
    ON entities.mv_usaspending_first_contracts (first_contract_date);

CREATE INDEX idx_mv_usa_first_total_awards
    ON entities.mv_usaspending_first_contracts (total_awards);

-- Reset statement timeout to default
RESET statement_timeout;
