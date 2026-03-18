-- Migration 039: FMCSA Analytical Materialized Views
--
-- Creates four materialized views for interactive analytical queries from Hex/psql:
--   1. mv_fmcsa_latest_census — latest census snapshot per carrier
--   2. mv_fmcsa_latest_safety_percentiles — latest safety percentile snapshot per carrier
--   3. mv_fmcsa_crash_counts_12mo — trailing 12-month crash counts per carrier
--   4. mv_fmcsa_carrier_master — master join of census + safety + crashes
--
-- NOTE: No BEGIN/COMMIT wrapper. The materialized view population is too heavy
-- for Supabase's default statement_timeout inside a transaction.

SET statement_timeout = '0';

-- ============================================================
-- View 1: entities.mv_fmcsa_latest_census
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.motor_carrier_census_records
-- Purpose: latest snapshot per carrier, eliminating repeated DISTINCT ON CTE
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_carrier_master CASCADE;
DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_latest_census CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_latest_census AS
SELECT DISTINCT ON (dot_number) *
FROM entities.motor_carrier_census_records
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
ORDER BY dot_number, row_position;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_lc_dot
    ON entities.mv_fmcsa_latest_census (dot_number);

CREATE INDEX idx_mv_fmcsa_lc_state
    ON entities.mv_fmcsa_latest_census (physical_state);

CREATE INDEX idx_mv_fmcsa_lc_op_code
    ON entities.mv_fmcsa_latest_census (carrier_operation_code);

CREATE INDEX idx_mv_fmcsa_lc_legal_name
    ON entities.mv_fmcsa_latest_census (legal_name);

CREATE INDEX idx_mv_fmcsa_lc_power_units
    ON entities.mv_fmcsa_latest_census (power_unit_count);

-- ============================================================
-- View 2: entities.mv_fmcsa_latest_safety_percentiles
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.carrier_safety_basic_percentiles
-- Purpose: latest safety percentile snapshot per carrier
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_latest_safety_percentiles CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_latest_safety_percentiles AS
SELECT DISTINCT ON (dot_number) *
FROM entities.carrier_safety_basic_percentiles
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_safety_basic_percentiles)
ORDER BY dot_number, row_position;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_lsp_dot
    ON entities.mv_fmcsa_latest_safety_percentiles (dot_number);

-- Percentile columns commonly filtered in fmcsa_safety_risk.py
CREATE INDEX idx_mv_fmcsa_lsp_unsafe_driving
    ON entities.mv_fmcsa_latest_safety_percentiles (unsafe_driving_percentile);

CREATE INDEX idx_mv_fmcsa_lsp_hos
    ON entities.mv_fmcsa_latest_safety_percentiles (hours_of_service_percentile);

CREATE INDEX idx_mv_fmcsa_lsp_vehicle_maint
    ON entities.mv_fmcsa_latest_safety_percentiles (vehicle_maintenance_percentile);

CREATE INDEX idx_mv_fmcsa_lsp_driver_fitness
    ON entities.mv_fmcsa_latest_safety_percentiles (driver_fitness_percentile);

CREATE INDEX idx_mv_fmcsa_lsp_controlled_sub
    ON entities.mv_fmcsa_latest_safety_percentiles (controlled_substances_alcohol_percentile);

-- ============================================================
-- View 3: entities.mv_fmcsa_crash_counts_12mo
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.commercial_vehicle_crashes
-- Purpose: trailing 12-month crash counts per carrier
-- ============================================================

DROP MATERIALIZED VIEW IF EXISTS entities.mv_fmcsa_crash_counts_12mo CASCADE;

CREATE MATERIALIZED VIEW entities.mv_fmcsa_crash_counts_12mo AS
SELECT
    dot_number,
    COUNT(*) AS crash_count_12mo,
    MAX(report_date) AS latest_crash_date,
    SUM(CASE WHEN fatalities > 0 THEN 1 ELSE 0 END) AS fatal_crash_count_12mo
FROM entities.commercial_vehicle_crashes
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
  AND report_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY dot_number;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_cc12_dot
    ON entities.mv_fmcsa_crash_counts_12mo (dot_number);

CREATE INDEX idx_mv_fmcsa_cc12_count
    ON entities.mv_fmcsa_crash_counts_12mo (crash_count_12mo);

-- ============================================================
-- View 4: entities.mv_fmcsa_carrier_master
-- Refresh: daily, after the three upstream MVs are refreshed
-- Source: mv_fmcsa_latest_census + mv_fmcsa_latest_safety_percentiles + mv_fmcsa_crash_counts_12mo
-- Purpose: master carrier view joining census + safety + crashes for one-stop analytical queries
--
-- Uses LEFT JOIN for both safety and crashes so all carriers appear even without
-- safety data or crash history (differs from fmcsa_safety_risk.py which uses INNER JOIN
-- for safety — the MV is for analysis, not risk scoring).
-- ============================================================

CREATE MATERIALIZED VIEW entities.mv_fmcsa_carrier_master AS
SELECT
    census.*,
    -- Safety percentiles
    safety.unsafe_driving_percentile,
    safety.hours_of_service_percentile,
    safety.vehicle_maintenance_percentile,
    safety.driver_fitness_percentile,
    safety.controlled_substances_alcohol_percentile,
    -- Safety alert flags
    safety.unsafe_driving_basic_alert,
    safety.hours_of_service_basic_alert,
    safety.vehicle_maintenance_basic_alert,
    safety.driver_fitness_basic_alert,
    safety.controlled_substances_alcohol_basic_alert,
    safety.inspection_total AS safety_inspection_total,
    -- Crash counts
    COALESCE(crashes.crash_count_12mo, 0) AS crash_count_12mo,
    crashes.latest_crash_date,
    COALESCE(crashes.fatal_crash_count_12mo, 0) AS fatal_crash_count_12mo
FROM entities.mv_fmcsa_latest_census census
LEFT JOIN entities.mv_fmcsa_latest_safety_percentiles safety ON census.dot_number = safety.dot_number
LEFT JOIN entities.mv_fmcsa_crash_counts_12mo crashes ON census.dot_number = crashes.dot_number;

-- Unique index enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_cm_dot
    ON entities.mv_fmcsa_carrier_master (dot_number);

CREATE INDEX idx_mv_fmcsa_cm_state
    ON entities.mv_fmcsa_carrier_master (physical_state);

CREATE INDEX idx_mv_fmcsa_cm_op_code
    ON entities.mv_fmcsa_carrier_master (carrier_operation_code);

CREATE INDEX idx_mv_fmcsa_cm_crash_count
    ON entities.mv_fmcsa_carrier_master (crash_count_12mo);

CREATE INDEX idx_mv_fmcsa_cm_unsafe_driving
    ON entities.mv_fmcsa_carrier_master (unsafe_driving_percentile);

-- Reset statement timeout to default
RESET statement_timeout;
