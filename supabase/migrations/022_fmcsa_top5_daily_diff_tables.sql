BEGIN;

CREATE SCHEMA IF NOT EXISTS entities;

CREATE TABLE IF NOT EXISTS entities.operating_authority_histories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_fingerprint TEXT NOT NULL UNIQUE,
    docket_number TEXT,
    usdot_number TEXT,
    sub_number TEXT,
    operating_authority_type TEXT,
    original_authority_action_description TEXT,
    original_authority_action_served_date DATE,
    final_authority_action_description TEXT,
    final_authority_decision_date DATE,
    final_authority_served_date DATE,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operating_authority_histories_docket
    ON entities.operating_authority_histories(docket_number);
CREATE INDEX IF NOT EXISTS idx_operating_authority_histories_usdot
    ON entities.operating_authority_histories(usdot_number);
CREATE INDEX IF NOT EXISTS idx_operating_authority_histories_last_observed
    ON entities.operating_authority_histories(last_observed_at DESC);

DROP TRIGGER IF EXISTS update_operating_authority_histories_updated_at ON entities.operating_authority_histories;
CREATE TRIGGER update_operating_authority_histories_updated_at
    BEFORE UPDATE ON entities.operating_authority_histories
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.operating_authority_histories ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.operating_authority_revocations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_fingerprint TEXT NOT NULL UNIQUE,
    docket_number TEXT,
    usdot_number TEXT,
    operating_authority_registration_type TEXT,
    serve_date DATE,
    revocation_type TEXT,
    effective_date DATE,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_operating_authority_revocations_docket
    ON entities.operating_authority_revocations(docket_number);
CREATE INDEX IF NOT EXISTS idx_operating_authority_revocations_usdot
    ON entities.operating_authority_revocations(usdot_number);
CREATE INDEX IF NOT EXISTS idx_operating_authority_revocations_effective_date
    ON entities.operating_authority_revocations(effective_date DESC);

DROP TRIGGER IF EXISTS update_operating_authority_revocations_updated_at ON entities.operating_authority_revocations;
CREATE TRIGGER update_operating_authority_revocations_updated_at
    BEFORE UPDATE ON entities.operating_authority_revocations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.operating_authority_revocations ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.insurance_policies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_fingerprint TEXT NOT NULL UNIQUE,
    docket_number TEXT,
    insurance_type_code TEXT,
    insurance_type_description TEXT,
    bipd_class_code TEXT,
    bipd_maximum_dollar_limit_thousands_usd INTEGER,
    bipd_underlying_dollar_limit_thousands_usd INTEGER,
    policy_number TEXT,
    effective_date DATE,
    form_code TEXT,
    insurance_company_name TEXT,
    is_removal_signal BOOLEAN NOT NULL DEFAULT FALSE,
    removal_signal_reason TEXT,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insurance_policies_docket
    ON entities.insurance_policies(docket_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_policy_number
    ON entities.insurance_policies(policy_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_effective_date
    ON entities.insurance_policies(effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_insurance_policies_removal_signal
    ON entities.insurance_policies(is_removal_signal);

DROP TRIGGER IF EXISTS update_insurance_policies_updated_at ON entities.insurance_policies;
CREATE TRIGGER update_insurance_policies_updated_at
    BEFORE UPDATE ON entities.insurance_policies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.insurance_policies ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.insurance_policy_filings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_fingerprint TEXT NOT NULL UNIQUE,
    docket_number TEXT,
    usdot_number TEXT,
    form_code TEXT,
    insurance_type_description TEXT,
    insurance_company_name TEXT,
    policy_number TEXT,
    posted_date DATE,
    bipd_underlying_limit_thousands_usd INTEGER,
    bipd_maximum_limit_thousands_usd INTEGER,
    effective_date DATE,
    cancel_effective_date DATE,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insurance_policy_filings_docket
    ON entities.insurance_policy_filings(docket_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_filings_usdot
    ON entities.insurance_policy_filings(usdot_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_filings_policy_number
    ON entities.insurance_policy_filings(policy_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_filings_posted_date
    ON entities.insurance_policy_filings(posted_date DESC);

DROP TRIGGER IF EXISTS update_insurance_policy_filings_updated_at ON entities.insurance_policy_filings;
CREATE TRIGGER update_insurance_policy_filings_updated_at
    BEFORE UPDATE ON entities.insurance_policy_filings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.insurance_policy_filings ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.insurance_policy_history_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_fingerprint TEXT NOT NULL UNIQUE,
    docket_number TEXT,
    usdot_number TEXT,
    form_code TEXT,
    cancellation_method TEXT,
    cancellation_form_code TEXT,
    insurance_type_indicator TEXT,
    insurance_type_description TEXT,
    policy_number TEXT,
    minimum_coverage_amount_thousands_usd INTEGER,
    insurance_class_code TEXT,
    effective_date DATE,
    bipd_underlying_limit_amount_thousands_usd INTEGER,
    bipd_max_coverage_amount_thousands_usd INTEGER,
    cancel_effective_date DATE,
    specific_cancellation_method TEXT,
    insurance_company_branch TEXT,
    insurance_company_name TEXT,
    source_provider TEXT NOT NULL DEFAULT 'fmcsa_open_data',
    source_feed_name TEXT NOT NULL,
    source_download_url TEXT NOT NULL,
    source_file_variant TEXT NOT NULL,
    source_observed_at TIMESTAMPTZ NOT NULL,
    source_task_id TEXT NOT NULL,
    source_schedule_id TEXT,
    source_run_metadata JSONB NOT NULL,
    raw_source_row JSONB NOT NULL,
    first_observed_at TIMESTAMPTZ NOT NULL,
    last_observed_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_insurance_policy_history_events_docket
    ON entities.insurance_policy_history_events(docket_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_history_events_usdot
    ON entities.insurance_policy_history_events(usdot_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_history_events_policy_number
    ON entities.insurance_policy_history_events(policy_number);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_history_events_cancel_effective_date
    ON entities.insurance_policy_history_events(cancel_effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_insurance_policy_history_events_cancellation_method
    ON entities.insurance_policy_history_events(cancellation_method);

DROP TRIGGER IF EXISTS update_insurance_policy_history_events_updated_at ON entities.insurance_policy_history_events;
CREATE TRIGGER update_insurance_policy_history_events_updated_at
    BEFORE UPDATE ON entities.insurance_policy_history_events
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.insurance_policy_history_events ENABLE ROW LEVEL SECURITY;

COMMIT;
