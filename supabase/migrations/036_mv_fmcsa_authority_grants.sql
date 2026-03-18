-- Materialized view: FMCSA Authority Grants
-- Pre-filtered subset of operating_authority_histories containing only grant rows.
-- Eliminates the need for sequential scans with UPPER(...) LIKE '%GRANT%' on 29.7M rows.
--
-- NOTE: No BEGIN/COMMIT wrapper. CREATE MATERIALIZED VIEW populates the view
-- on creation, and that scan is too heavy for Supabase's default statement_timeout
-- inside a transaction. Run with: SET statement_timeout = '0'; before executing.

SET statement_timeout = '0';

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_authority_grants CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_authority_grants AS
SELECT
    id,
    docket_number,
    usdot_number,
    sub_number,
    operating_authority_type,
    original_authority_action_description,
    original_authority_action_served_date,
    final_authority_action_description,
    final_authority_decision_date,
    final_authority_served_date,
    source_feed_name,
    source_observed_at,
    feed_date,
    created_at
FROM entities.operating_authority_histories
WHERE original_authority_action_description IS NOT NULL
  AND UPPER(original_authority_action_description) LIKE '%GRANT%'
  AND original_authority_action_served_date IS NOT NULL;

-- Unique index: enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_ag_id
    ON entities.mv_fmcsa_authority_grants (id);

-- Primary analytics dimension: served date
CREATE INDEX idx_mv_fmcsa_ag_served_date
    ON entities.mv_fmcsa_authority_grants (original_authority_action_served_date);

-- Carrier lookups
CREATE INDEX idx_mv_fmcsa_ag_usdot
    ON entities.mv_fmcsa_authority_grants (usdot_number);

-- Authority type breakdowns
CREATE INDEX idx_mv_fmcsa_ag_auth_type
    ON entities.mv_fmcsa_authority_grants (operating_authority_type);

-- Composite for the exact analytics query pattern
CREATE INDEX idx_mv_fmcsa_ag_date_usdot
    ON entities.mv_fmcsa_authority_grants (original_authority_action_served_date, usdot_number);

RESET statement_timeout;
