-- Composite indexes on (feed_date, source_feed_name) for all FMCSA entity tables.
-- The snapshot-replace path DELETEs by (feed_date, source_feed_name) before INSERT;
-- without a composite index, the DELETE does a sequential scan on large tables
-- and hits statement timeouts.

-- CSV export tables (025)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vehicle_inspection_units_feed_date_feed_name
    ON entities.vehicle_inspection_units(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vehicle_inspection_special_studies_feed_date_feed_name
    ON entities.vehicle_inspection_special_studies(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_vehicle_inspection_citations_feed_date_feed_name
    ON entities.vehicle_inspection_citations(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_commercial_vehicle_crashes_feed_date_feed_name
    ON entities.commercial_vehicle_crashes(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_out_of_service_orders_feed_date_feed_name
    ON entities.out_of_service_orders(feed_date, source_feed_name);

-- SMS tables (024)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_carrier_safety_basic_measures_feed_date_feed_name
    ON entities.carrier_safety_basic_measures(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_carrier_safety_basic_percentiles_feed_date_feed_name
    ON entities.carrier_safety_basic_percentiles(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_carrier_inspection_violations_feed_date_feed_name
    ON entities.carrier_inspection_violations(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_carrier_inspections_feed_date_feed_name
    ON entities.carrier_inspections(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_motor_carrier_census_records_feed_date_feed_name
    ON entities.motor_carrier_census_records(feed_date, source_feed_name);

-- Snapshot history tables (023)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_carrier_registrations_feed_date_feed_name
    ON entities.carrier_registrations(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_process_agent_filings_feed_date_feed_name
    ON entities.process_agent_filings(feed_date, source_feed_name);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_insurance_filing_rejections_feed_date_feed_name
    ON entities.insurance_filing_rejections(feed_date, source_feed_name);
