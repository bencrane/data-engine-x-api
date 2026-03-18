-- Materialized view: FMCSA Insurance Cancellations
-- Pre-filtered subset of insurance_policy_history_events containing only rows
-- with a non-null cancellation date.
--
-- NOTE: No BEGIN/COMMIT wrapper. CREATE MATERIALIZED VIEW populates the view
-- on creation, and that scan is too heavy for Supabase's default statement_timeout
-- inside a transaction. Run with: SET statement_timeout = '0'; before executing.

SET statement_timeout = '0';

CREATE MATERIALIZED VIEW entities.mv_fmcsa_insurance_cancellations AS
SELECT
    id,
    docket_number,
    usdot_number,
    form_code,
    cancellation_method,
    cancellation_form_code,
    specific_cancellation_method,
    insurance_type_indicator,
    insurance_type_description,
    insurance_company_name,
    policy_number,
    effective_date,
    cancel_effective_date,
    bipd_underlying_limit_amount_thousands_usd,
    bipd_max_coverage_amount_thousands_usd,
    source_feed_name,
    first_observed_at,
    last_observed_at,
    created_at
FROM entities.insurance_policy_history_events
WHERE cancel_effective_date IS NOT NULL;

-- Unique index: enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_ic_id
    ON entities.mv_fmcsa_insurance_cancellations (id);

-- Primary analytics dimension: cancellation date
CREATE INDEX idx_mv_fmcsa_ic_cancel_date
    ON entities.mv_fmcsa_insurance_cancellations (cancel_effective_date);

-- Carrier lookups
CREATE INDEX idx_mv_fmcsa_ic_usdot
    ON entities.mv_fmcsa_insurance_cancellations (usdot_number);

-- Cancellation type breakdowns
CREATE INDEX idx_mv_fmcsa_ic_cancel_method
    ON entities.mv_fmcsa_insurance_cancellations (cancellation_method);

-- Composite for the exact analytics query pattern
CREATE INDEX idx_mv_fmcsa_ic_date_usdot
    ON entities.mv_fmcsa_insurance_cancellations (cancel_effective_date, usdot_number);

RESET statement_timeout;
