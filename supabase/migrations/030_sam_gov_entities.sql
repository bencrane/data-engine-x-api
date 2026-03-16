BEGIN;

CREATE TABLE IF NOT EXISTS entities.sam_gov_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- SAM.gov extract columns (142 Public V2 positional fields)
    unique_entity_id TEXT,
    col_002_deprecated TEXT,
    entity_eft_indicator TEXT,
    cage_code TEXT,
    dodaac TEXT,
    sam_extract_code TEXT,
    purpose_of_registration TEXT,
    initial_registration_date TEXT,
    registration_expiration_date TEXT,
    last_update_date TEXT,
    activation_date TEXT,
    legal_business_name TEXT,
    dba_name TEXT,
    entity_division_name TEXT,
    entity_division_number TEXT,
    physical_address_line_1 TEXT,
    physical_address_line_2 TEXT,
    physical_address_city TEXT,
    physical_address_province_or_state TEXT,
    physical_address_zippostal_code TEXT,
    physical_address_zip_code_4 TEXT,
    physical_address_country_code TEXT,
    physical_address_congressional_district TEXT,
    db_open_data_flag TEXT,
    entity_start_date TEXT,
    fiscal_year_end_close_date TEXT,
    entity_url TEXT,
    entity_structure TEXT,
    state_of_incorporation TEXT,
    country_of_incorporation TEXT,
    business_type_counter TEXT,
    bus_type_string TEXT,
    primary_naics TEXT,
    naics_code_counter TEXT,
    naics_code_string TEXT,
    psc_code_counter TEXT,
    psc_code_string TEXT,
    credit_card_usage TEXT,
    correspondence_flag TEXT,
    mailing_address_line_1 TEXT,
    mailing_address_line_2 TEXT,
    mailing_address_city TEXT,
    mailing_address_zippostal_code TEXT,
    mailing_address_zip_code_4 TEXT,
    mailing_address_country TEXT,
    mailing_address_state_or_province TEXT,
    govt_bus_poc_first_name TEXT,
    govt_bus_poc_middle_initial TEXT,
    govt_bus_poc_last_name TEXT,
    govt_bus_poc_title TEXT,
    govt_bus_poc_st_add_1 TEXT,
    govt_bus_poc_st_add_2 TEXT,
    govt_bus_poc_city TEXT,
    govt_bus_poc_zippostal_code TEXT,
    govt_bus_poc_zip_code_4 TEXT,
    govt_bus_poc_country_code TEXT,
    govt_bus_poc_state_or_province TEXT,
    alt_govt_bus_poc_first_name TEXT,
    alt_govt_bus_poc_middle_initial TEXT,
    alt_govt_bus_poc_last_name TEXT,
    alt_govt_bus_poc_title TEXT,
    alt_govt_bus_poc_st_add_1 TEXT,
    alt_govt_bus_poc_st_add_2 TEXT,
    alt_govt_bus_poc_city TEXT,
    alt_govt_bus_poc_zippostal_code TEXT,
    alt_govt_bus_poc_zip_code_4 TEXT,
    alt_govt_bus_poc_country_code TEXT,
    alt_govt_bus_poc_state_or_province TEXT,
    past_perf_poc_poc_first_name TEXT,
    past_perf_poc_poc_middle_initial TEXT,
    past_perf_poc_poc_last_name TEXT,
    past_perf_poc_poc_title TEXT,
    past_perf_poc_st_add_1 TEXT,
    past_perf_poc_st_add_2 TEXT,
    past_perf_poc_city TEXT,
    past_perf_poc_zippostal_code TEXT,
    past_perf_poc_zip_code_4 TEXT,
    past_perf_poc_country_code TEXT,
    past_perf_poc_state_or_province TEXT,
    alt_past_perf_poc_first_name TEXT,
    alt_past_perf_poc_middle_initial TEXT,
    alt_past_perf_poc_last_name TEXT,
    alt_past_perf_poc_title TEXT,
    alt_past_perf_poc_st_add_1 TEXT,
    alt_past_perf_poc_st_add_2 TEXT,
    alt_past_perf_poc_city TEXT,
    alt_past_perf_poc_zippostal_code TEXT,
    alt_past_perf_poc_zip_code_4 TEXT,
    alt_past_perf_poc_country_code TEXT,
    alt_past_perf_poc_state_or_province TEXT,
    elec_bus_poc_first_name TEXT,
    elec_bus_poc_middle_initial TEXT,
    elec_bus_poc_last_name TEXT,
    elec_bus_poc_title TEXT,
    elec_bus_poc_st_add_1 TEXT,
    elec_bus_poc_st_add_2 TEXT,
    elec_bus_poc_city TEXT,
    elec_bus_poc_zippostal_code TEXT,
    elec_bus_poc_zip_code_4 TEXT,
    elec_bus_poc_country_code TEXT,
    elec_bus_poc_state_or_province TEXT,
    alt_elec_poc_bus_poc_first_name TEXT,
    alt_elec_poc_bus_poc_middle_initial TEXT,
    alt_elec_poc_bus_poc_last_name TEXT,
    alt_elec_poc_bus_poc_title TEXT,
    alt_elec_poc_bus_st_add_1 TEXT,
    alt_elec_poc_bus_st_add_2 TEXT,
    alt_elec_poc_bus_city TEXT,
    alt_elec_poc_bus_zippostal_code TEXT,
    alt_elec_poc_bus_zip_code_4 TEXT,
    alt_elec_poc_bus_country_code TEXT,
    alt_elec_poc_bus_state_or_province TEXT,
    naics_exception_counter TEXT,
    naics_exception_string TEXT,
    debt_subject_to_offset_flag TEXT,
    exclusion_status_flag TEXT,
    sba_business_types_counter TEXT,
    sba_business_types_string TEXT,
    no_public_display_flag TEXT,
    disaster_response_counter TEXT,
    disaster_response_string TEXT,
    entity_evs_source TEXT,
    flex_field_6 TEXT,
    flex_field_7 TEXT,
    flex_field_8 TEXT,
    flex_field_9 TEXT,
    flex_field_10 TEXT,
    flex_field_11 TEXT,
    flex_field_12 TEXT,
    flex_field_13 TEXT,
    flex_field_14 TEXT,
    flex_field_15 TEXT,
    flex_field_16 TEXT,
    flex_field_17 TEXT,
    flex_field_18 TEXT,
    flex_field_19 TEXT,
    flex_field_20 TEXT,
    flex_field_21 TEXT,
    flex_field_22 TEXT,
    flex_field_23 TEXT,
    flex_field_24 TEXT,
    end_of_record_indicator TEXT,

    -- Extract metadata columns
    extract_date DATE NOT NULL,
    extract_type TEXT NOT NULL,
    extract_code TEXT,
    source_filename TEXT NOT NULL,
    source_provider TEXT NOT NULL DEFAULT 'sam_gov',
    source_download_url TEXT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_position INTEGER NOT NULL,
    raw_source_row TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one UEI per extract_date (upsert conflict target)
ALTER TABLE entities.sam_gov_entities
    ADD CONSTRAINT uq_sam_gov_entities_extract_date_uei
    UNIQUE (extract_date, unique_entity_id);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_uei
    ON entities.sam_gov_entities(unique_entity_id);

CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_extract_date
    ON entities.sam_gov_entities(extract_date DESC);

CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_extract_code
    ON entities.sam_gov_entities(extract_code);

CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_primary_naics
    ON entities.sam_gov_entities(primary_naics);

CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_state
    ON entities.sam_gov_entities(physical_address_province_or_state);

CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_legal_name
    ON entities.sam_gov_entities(legal_business_name text_pattern_ops);

-- updated_at trigger
DROP TRIGGER IF EXISTS update_sam_gov_entities_updated_at ON entities.sam_gov_entities;
CREATE TRIGGER update_sam_gov_entities_updated_at
    BEFORE UPDATE ON entities.sam_gov_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Row Level Security
ALTER TABLE entities.sam_gov_entities ENABLE ROW LEVEL SECURITY;

COMMIT;
