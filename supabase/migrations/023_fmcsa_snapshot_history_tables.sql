BEGIN;

CREATE SCHEMA IF NOT EXISTS entities;

ALTER TABLE entities.operating_authority_histories
    DROP CONSTRAINT IF EXISTS operating_authority_histories_feed_date_row_position_key;
ALTER TABLE entities.operating_authority_histories
    ADD CONSTRAINT operating_authority_histories_feed_date_source_feed_name_row_position_key
    UNIQUE(feed_date, source_feed_name, row_position);

ALTER TABLE entities.operating_authority_revocations
    DROP CONSTRAINT IF EXISTS operating_authority_revocations_feed_date_row_position_key;
ALTER TABLE entities.operating_authority_revocations
    ADD CONSTRAINT operating_authority_revocations_feed_date_source_feed_name_row_position_key
    UNIQUE(feed_date, source_feed_name, row_position);

ALTER TABLE entities.insurance_policies
    DROP CONSTRAINT IF EXISTS insurance_policies_feed_date_row_position_key;
ALTER TABLE entities.insurance_policies
    ADD CONSTRAINT insurance_policies_feed_date_source_feed_name_row_position_key
    UNIQUE(feed_date, source_feed_name, row_position);

ALTER TABLE entities.insurance_policy_filings
    DROP CONSTRAINT IF EXISTS insurance_policy_filings_feed_date_row_position_key;
ALTER TABLE entities.insurance_policy_filings
    ADD CONSTRAINT insurance_policy_filings_feed_date_source_feed_name_row_position_key
    UNIQUE(feed_date, source_feed_name, row_position);

ALTER TABLE entities.insurance_policy_history_events
    DROP CONSTRAINT IF EXISTS insurance_policy_history_events_feed_date_row_position_key;
ALTER TABLE entities.insurance_policy_history_events
    ADD CONSTRAINT insurance_policy_history_events_feed_date_source_feed_name_row_position_key
    UNIQUE(feed_date, source_feed_name, row_position);

CREATE TABLE IF NOT EXISTS entities.carrier_registrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    docket_number TEXT,
    usdot_number TEXT,
    mx_type TEXT,
    rfc_number TEXT,
    common_authority_status TEXT,
    contract_authority_status TEXT,
    broker_authority_status TEXT,
    pending_common_authority TEXT,
    pending_contract_authority TEXT,
    pending_broker_authority TEXT,
    common_authority_revocation TEXT,
    contract_authority_revocation TEXT,
    broker_authority_revocation TEXT,
    property_authority TEXT,
    passenger_authority TEXT,
    household_goods_authority TEXT,
    private_check TEXT,
    enterprise_check TEXT,
    bipd_required_thousands_usd INTEGER,
    cargo_required TEXT,
    bond_surety_required TEXT,
    bipd_on_file_thousands_usd INTEGER,
    cargo_on_file TEXT,
    bond_surety_on_file TEXT,
    address_status TEXT,
    dba_name TEXT,
    legal_name TEXT,
    business_address_street TEXT,
    business_address_colonia TEXT,
    business_address_city TEXT,
    business_address_state_code TEXT,
    business_address_country_code TEXT,
    business_address_zip_code TEXT,
    business_address_telephone_number TEXT,
    business_address_fax_number TEXT,
    mailing_address_street TEXT,
    mailing_address_colonia TEXT,
    mailing_address_city TEXT,
    mailing_address_state_code TEXT,
    mailing_address_country_code TEXT,
    mailing_address_zip_code TEXT,
    mailing_address_telephone_number TEXT,
    mailing_address_fax_number TEXT,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(feed_date, source_feed_name, row_position)
);

CREATE INDEX IF NOT EXISTS idx_carrier_registrations_feed_date
    ON entities.carrier_registrations(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_registrations_docket
    ON entities.carrier_registrations(docket_number);
CREATE INDEX IF NOT EXISTS idx_carrier_registrations_usdot
    ON entities.carrier_registrations(usdot_number);
CREATE INDEX IF NOT EXISTS idx_carrier_registrations_legal_name
    ON entities.carrier_registrations(legal_name);

DROP TRIGGER IF EXISTS update_carrier_registrations_updated_at ON entities.carrier_registrations;
CREATE TRIGGER update_carrier_registrations_updated_at
    BEFORE UPDATE ON entities.carrier_registrations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.carrier_registrations ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.process_agent_filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    docket_number TEXT,
    usdot_number TEXT,
    process_agent_company_name TEXT,
    attention_to_or_title TEXT,
    street_or_po_box TEXT,
    city TEXT,
    state TEXT,
    country TEXT,
    zip_code TEXT,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(feed_date, source_feed_name, row_position)
);

CREATE INDEX IF NOT EXISTS idx_process_agent_filings_feed_date
    ON entities.process_agent_filings(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_process_agent_filings_docket
    ON entities.process_agent_filings(docket_number);
CREATE INDEX IF NOT EXISTS idx_process_agent_filings_usdot
    ON entities.process_agent_filings(usdot_number);
CREATE INDEX IF NOT EXISTS idx_process_agent_filings_state
    ON entities.process_agent_filings(state);

DROP TRIGGER IF EXISTS update_process_agent_filings_updated_at ON entities.process_agent_filings;
CREATE TRIGGER update_process_agent_filings_updated_at
    BEFORE UPDATE ON entities.process_agent_filings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.process_agent_filings ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.insurance_filing_rejections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    docket_number TEXT,
    usdot_number TEXT,
    form_code TEXT,
    insurance_type_description TEXT,
    policy_number TEXT,
    received_date DATE,
    insurance_class_code TEXT,
    insurance_type_code TEXT,
    underlying_limit_amount_thousands_usd INTEGER,
    maximum_coverage_amount_thousands_usd INTEGER,
    rejected_date DATE,
    insurance_branch TEXT,
    insurance_company_name TEXT,
    rejected_reason TEXT,
    minimum_coverage_amount_thousands_usd INTEGER,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(feed_date, source_feed_name, row_position)
);

CREATE INDEX IF NOT EXISTS idx_insurance_filing_rejections_feed_date
    ON entities.insurance_filing_rejections(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_insurance_filing_rejections_docket
    ON entities.insurance_filing_rejections(docket_number);
CREATE INDEX IF NOT EXISTS idx_insurance_filing_rejections_usdot
    ON entities.insurance_filing_rejections(usdot_number);
CREATE INDEX IF NOT EXISTS idx_insurance_filing_rejections_policy_number
    ON entities.insurance_filing_rejections(policy_number);
CREATE INDEX IF NOT EXISTS idx_insurance_filing_rejections_rejected_date
    ON entities.insurance_filing_rejections(rejected_date DESC);

DROP TRIGGER IF EXISTS update_insurance_filing_rejections_updated_at ON entities.insurance_filing_rejections;
CREATE TRIGGER update_insurance_filing_rejections_updated_at
    BEFORE UPDATE ON entities.insurance_filing_rejections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.insurance_filing_rejections ENABLE ROW LEVEL SECURITY;

COMMIT;
