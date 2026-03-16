-- Migration 034: Add agency-specific first-time awardee flags to the federal contract leads view.
--
-- Adds: is_first_time_dod_awardee, is_first_time_nasa_awardee,
--        is_first_time_doe_awardee, is_first_time_dhs_awardee
--
-- A company is "first-time DoD awardee" if their UEI has exactly 1 distinct
-- contract_award_unique_key where the awarding agency is DoD. They may have
-- prior awards from other agencies. Same logic for NASA, DOE, DHS.
--
-- NOTE: No BEGIN/COMMIT wrapper. The materialized view population is too heavy
-- for Supabase's default statement_timeout inside a transaction.

SET statement_timeout = '0';

-- Drop existing view and indexes (CASCADE drops dependent indexes)
DROP MATERIALIZED VIEW IF EXISTS entities.mv_federal_contract_leads CASCADE;

CREATE MATERIALIZED VIEW entities.mv_federal_contract_leads AS
WITH
-- Latest snapshot per SAM.gov entity (one row per unique_entity_id)
latest_sam AS (
    SELECT DISTINCT ON (unique_entity_id) *
    FROM entities.sam_gov_entities
    WHERE unique_entity_id IS NOT NULL AND unique_entity_id != ''
    ORDER BY unique_entity_id, extract_date DESC
),
-- Latest snapshot per USASpending transaction (one row per contract_transaction_unique_key)
latest_usa AS (
    SELECT DISTINCT ON (contract_transaction_unique_key) *
    FROM entities.usaspending_contracts
    WHERE contract_transaction_unique_key IS NOT NULL AND contract_transaction_unique_key != ''
    ORDER BY contract_transaction_unique_key, extract_date DESC
),
-- Award counts per UEI (for first-time awardee detection — all agencies)
award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS total_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
    GROUP BY recipient_uei
),
-- Award counts per UEI for DoD specifically
dod_award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS dod_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND awarding_agency_name = 'Department of Defense'
    GROUP BY recipient_uei
),
-- Award counts per UEI for NASA
nasa_award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS nasa_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND awarding_agency_name = 'National Aeronautics and Space Administration'
    GROUP BY recipient_uei
),
-- Award counts per UEI for DOE
doe_award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS doe_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND awarding_agency_name = 'Department of Energy'
    GROUP BY recipient_uei
),
-- Award counts per UEI for DHS
dhs_award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS dhs_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND awarding_agency_name = 'Department of Homeland Security'
    GROUP BY recipient_uei
)
SELECT
    -- USASpending columns
    u.contract_transaction_unique_key,
    u.contract_award_unique_key,
    u.recipient_uei,
    u.recipient_name,
    u.recipient_address_line_1,
    u.recipient_city_name,
    u.recipient_state_code,
    u.recipient_zip_4_code,
    u.recipient_country_code,
    u.recipient_phone_number,
    u.award_type,
    u.action_date,
    u.federal_action_obligation,
    u.total_dollars_obligated,
    u.potential_total_value_of_award,
    u.awarding_agency_code,
    u.awarding_agency_name,
    u.awarding_sub_agency_name,
    u.naics_code,
    u.naics_description,
    u.product_or_service_code,
    u.product_or_service_code_description,
    u.contracting_officers_determination_of_business_size,
    u.type_of_set_aside,
    u.extent_competed,
    u.number_of_offers_received,
    u.usaspending_permalink,
    u.extract_date AS usaspending_extract_date,

    -- SAM.gov columns (NULLable via LEFT JOIN)
    s.legal_business_name,
    s.dba_name,
    s.physical_address_line_1,
    s.physical_address_city,
    s.physical_address_province_or_state,
    s.physical_address_zippostal_code,
    s.entity_url,
    s.primary_naics,
    s.bus_type_string,
    s.sba_business_types_string,
    s.cage_code,
    s.registration_expiration_date,
    s.activation_date,
    s.entity_structure,
    s.govt_bus_poc_first_name,
    s.govt_bus_poc_last_name,
    s.govt_bus_poc_title,
    s.alt_govt_bus_poc_first_name,
    s.alt_govt_bus_poc_last_name,
    s.alt_govt_bus_poc_title,
    s.elec_bus_poc_first_name,
    s.elec_bus_poc_last_name,
    s.elec_bus_poc_title,
    s.extract_date AS sam_extract_date,

    -- Computed columns — overall
    (COALESCE(ac.total_awards, 0) = 1) AS is_first_time_awardee,
    COALESCE(ac.total_awards, 0)::INTEGER AS total_awards_count,
    (s.unique_entity_id IS NOT NULL) AS has_sam_match,

    -- Computed columns — agency-specific first-time flags
    (COALESCE(dod.dod_awards, 0) = 1) AS is_first_time_dod_awardee,
    COALESCE(dod.dod_awards, 0)::INTEGER AS dod_awards_count,
    (COALESCE(nasa.nasa_awards, 0) = 1) AS is_first_time_nasa_awardee,
    COALESCE(nasa.nasa_awards, 0)::INTEGER AS nasa_awards_count,
    (COALESCE(doe.doe_awards, 0) = 1) AS is_first_time_doe_awardee,
    COALESCE(doe.doe_awards, 0)::INTEGER AS doe_awards_count,
    (COALESCE(dhs.dhs_awards, 0) = 1) AS is_first_time_dhs_awardee,
    COALESCE(dhs.dhs_awards, 0)::INTEGER AS dhs_awards_count

FROM latest_usa u
LEFT JOIN latest_sam s
    ON u.recipient_uei = s.unique_entity_id
LEFT JOIN award_counts ac
    ON u.recipient_uei = ac.recipient_uei
LEFT JOIN dod_award_counts dod
    ON u.recipient_uei = dod.recipient_uei
LEFT JOIN nasa_award_counts nasa
    ON u.recipient_uei = nasa.recipient_uei
LEFT JOIN doe_award_counts doe
    ON u.recipient_uei = doe.recipient_uei
LEFT JOIN dhs_award_counts dhs
    ON u.recipient_uei = dhs.recipient_uei;

-- Indexes on the materialized view

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fcl_txn_key
    ON entities.mv_federal_contract_leads (contract_transaction_unique_key);

CREATE INDEX idx_mv_fcl_recipient_uei
    ON entities.mv_federal_contract_leads (recipient_uei);

CREATE INDEX idx_mv_fcl_state
    ON entities.mv_federal_contract_leads (recipient_state_code);

CREATE INDEX idx_mv_fcl_naics
    ON entities.mv_federal_contract_leads (naics_code);

CREATE INDEX idx_mv_fcl_action_date
    ON entities.mv_federal_contract_leads (action_date);

CREATE INDEX idx_mv_fcl_agency
    ON entities.mv_federal_contract_leads (awarding_agency_code);

CREATE INDEX idx_mv_fcl_first_time
    ON entities.mv_federal_contract_leads (is_first_time_awardee)
    WHERE is_first_time_awardee = TRUE;

CREATE INDEX idx_mv_fcl_first_time_dod
    ON entities.mv_federal_contract_leads (is_first_time_dod_awardee)
    WHERE is_first_time_dod_awardee = TRUE;

CREATE INDEX idx_mv_fcl_biz_size
    ON entities.mv_federal_contract_leads (contracting_officers_determination_of_business_size);

CREATE INDEX idx_mv_fcl_obligation
    ON entities.mv_federal_contract_leads (federal_action_obligation);

-- Reset statement timeout to default
RESET statement_timeout;
