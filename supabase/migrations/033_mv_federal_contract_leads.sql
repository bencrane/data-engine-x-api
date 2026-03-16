BEGIN;

-- Materialized view: Federal Contract Leads
-- Joins USASpending contracts with SAM.gov entity registrations on UEI.
-- Uses latest snapshot from each source table.

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
-- Award counts per UEI (for first-time awardee detection)
award_counts AS (
    SELECT
        recipient_uei,
        COUNT(DISTINCT contract_award_unique_key) AS total_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
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

    -- Computed columns
    (COALESCE(ac.total_awards, 0) = 1) AS is_first_time_awardee,
    COALESCE(ac.total_awards, 0)::INTEGER AS total_awards_count,
    (s.unique_entity_id IS NOT NULL) AS has_sam_match

FROM latest_usa u
LEFT JOIN latest_sam s
    ON u.recipient_uei = s.unique_entity_id
LEFT JOIN award_counts ac
    ON u.recipient_uei = ac.recipient_uei;

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

CREATE INDEX idx_mv_fcl_biz_size
    ON entities.mv_federal_contract_leads (contracting_officers_determination_of_business_size);

CREATE INDEX idx_mv_fcl_obligation
    ON entities.mv_federal_contract_leads (federal_action_obligation);

COMMIT;

-- Populate the view (outside transaction — materialized view refresh cannot run inside BEGIN/COMMIT)
REFRESH MATERIALIZED VIEW entities.mv_federal_contract_leads;
