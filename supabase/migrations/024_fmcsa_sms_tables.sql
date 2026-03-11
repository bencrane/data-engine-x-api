BEGIN;

CREATE SCHEMA IF NOT EXISTS entities;

CREATE TABLE IF NOT EXISTS entities.carrier_safety_basic_measures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    carrier_segment TEXT NOT NULL,
    dot_number TEXT,
    inspection_total INTEGER,
    driver_inspection_total INTEGER,
    driver_oos_inspection_total INTEGER,
    vehicle_inspection_total INTEGER,
    vehicle_oos_inspection_total INTEGER,
    unsafe_driving_inspections_with_violations INTEGER,
    unsafe_driving_measure NUMERIC,
    unsafe_driving_acute_critical BOOLEAN,
    hours_of_service_inspections_with_violations INTEGER,
    hours_of_service_measure NUMERIC,
    hours_of_service_acute_critical BOOLEAN,
    driver_fitness_inspections_with_violations INTEGER,
    driver_fitness_measure NUMERIC,
    driver_fitness_acute_critical BOOLEAN,
    controlled_substances_alcohol_inspections_with_violations INTEGER,
    controlled_substances_alcohol_measure NUMERIC,
    controlled_substances_alcohol_acute_critical BOOLEAN,
    vehicle_maintenance_inspections_with_violations INTEGER,
    vehicle_maintenance_measure NUMERIC,
    vehicle_maintenance_acute_critical BOOLEAN,
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

CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_measures_feed_date
    ON entities.carrier_safety_basic_measures(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_measures_dot_number
    ON entities.carrier_safety_basic_measures(dot_number);
CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_measures_carrier_segment
    ON entities.carrier_safety_basic_measures(carrier_segment);

DROP TRIGGER IF EXISTS update_carrier_safety_basic_measures_updated_at ON entities.carrier_safety_basic_measures;
CREATE TRIGGER update_carrier_safety_basic_measures_updated_at
    BEFORE UPDATE ON entities.carrier_safety_basic_measures
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.carrier_safety_basic_measures ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.carrier_safety_basic_percentiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    carrier_segment TEXT NOT NULL,
    dot_number TEXT,
    inspection_total INTEGER,
    driver_inspection_total INTEGER,
    driver_oos_inspection_total INTEGER,
    vehicle_inspection_total INTEGER,
    vehicle_oos_inspection_total INTEGER,
    unsafe_driving_inspections_with_violations INTEGER,
    unsafe_driving_measure NUMERIC,
    unsafe_driving_percentile NUMERIC,
    unsafe_driving_roadside_alert BOOLEAN,
    unsafe_driving_acute_critical BOOLEAN,
    unsafe_driving_basic_alert BOOLEAN,
    hours_of_service_inspections_with_violations INTEGER,
    hours_of_service_measure NUMERIC,
    hours_of_service_percentile NUMERIC,
    hours_of_service_roadside_alert BOOLEAN,
    hours_of_service_acute_critical BOOLEAN,
    hours_of_service_basic_alert BOOLEAN,
    driver_fitness_inspections_with_violations INTEGER,
    driver_fitness_measure NUMERIC,
    driver_fitness_percentile NUMERIC,
    driver_fitness_roadside_alert BOOLEAN,
    driver_fitness_acute_critical BOOLEAN,
    driver_fitness_basic_alert BOOLEAN,
    controlled_substances_alcohol_inspections_with_violations INTEGER,
    controlled_substances_alcohol_measure NUMERIC,
    controlled_substances_alcohol_percentile NUMERIC,
    controlled_substances_alcohol_roadside_alert BOOLEAN,
    controlled_substances_alcohol_acute_critical BOOLEAN,
    controlled_substances_alcohol_basic_alert BOOLEAN,
    vehicle_maintenance_inspections_with_violations INTEGER,
    vehicle_maintenance_measure NUMERIC,
    vehicle_maintenance_percentile NUMERIC,
    vehicle_maintenance_roadside_alert BOOLEAN,
    vehicle_maintenance_acute_critical BOOLEAN,
    vehicle_maintenance_basic_alert BOOLEAN,
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

CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_percentiles_feed_date
    ON entities.carrier_safety_basic_percentiles(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_percentiles_dot_number
    ON entities.carrier_safety_basic_percentiles(dot_number);
CREATE INDEX IF NOT EXISTS idx_carrier_safety_basic_percentiles_carrier_segment
    ON entities.carrier_safety_basic_percentiles(carrier_segment);

DROP TRIGGER IF EXISTS update_carrier_safety_basic_percentiles_updated_at ON entities.carrier_safety_basic_percentiles;
CREATE TRIGGER update_carrier_safety_basic_percentiles_updated_at
    BEFORE UPDATE ON entities.carrier_safety_basic_percentiles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.carrier_safety_basic_percentiles ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.carrier_inspection_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    inspection_unique_id TEXT,
    inspection_date DATE,
    dot_number TEXT,
    violation_code TEXT,
    basic_description TEXT,
    oos_indicator BOOLEAN,
    oos_weight INTEGER,
    severity_weight INTEGER,
    time_weight INTEGER,
    total_severity_weight INTEGER,
    section_description TEXT,
    group_description TEXT,
    violation_unit TEXT,
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

CREATE INDEX IF NOT EXISTS idx_carrier_inspection_violations_feed_date
    ON entities.carrier_inspection_violations(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_inspection_violations_dot_number
    ON entities.carrier_inspection_violations(dot_number);
CREATE INDEX IF NOT EXISTS idx_carrier_inspection_violations_unique_id
    ON entities.carrier_inspection_violations(inspection_unique_id);
CREATE INDEX IF NOT EXISTS idx_carrier_inspection_violations_basic_description
    ON entities.carrier_inspection_violations(basic_description);

DROP TRIGGER IF EXISTS update_carrier_inspection_violations_updated_at ON entities.carrier_inspection_violations;
CREATE TRIGGER update_carrier_inspection_violations_updated_at
    BEFORE UPDATE ON entities.carrier_inspection_violations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.carrier_inspection_violations ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.carrier_inspections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    inspection_unique_id TEXT,
    report_number TEXT,
    report_state TEXT,
    dot_number TEXT,
    inspection_date DATE,
    inspection_level_id INTEGER,
    county_code_state TEXT,
    time_weight INTEGER,
    driver_oos_total INTEGER,
    vehicle_oos_total INTEGER,
    total_hazmat_sent INTEGER,
    oos_total INTEGER,
    hazmat_oos_total INTEGER,
    hazmat_placard_required BOOLEAN,
    primary_unit_type_description TEXT,
    primary_unit_make TEXT,
    primary_unit_license TEXT,
    primary_unit_license_state TEXT,
    primary_unit_vin TEXT,
    primary_unit_decal_number TEXT,
    secondary_unit_type_description TEXT,
    secondary_unit_make TEXT,
    secondary_unit_license TEXT,
    secondary_unit_license_state TEXT,
    secondary_unit_vin TEXT,
    secondary_unit_decal_number TEXT,
    unsafe_driving_inspection BOOLEAN,
    hours_of_service_inspection BOOLEAN,
    driver_fitness_inspection BOOLEAN,
    controlled_substances_alcohol_inspection BOOLEAN,
    vehicle_maintenance_inspection BOOLEAN,
    hazmat_inspection BOOLEAN,
    basic_violation_total INTEGER,
    unsafe_driving_violation_total INTEGER,
    hours_of_service_violation_total INTEGER,
    driver_fitness_violation_total INTEGER,
    controlled_substances_alcohol_violation_total INTEGER,
    vehicle_maintenance_violation_total INTEGER,
    hazmat_violation_total INTEGER,
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

CREATE INDEX IF NOT EXISTS idx_carrier_inspections_feed_date
    ON entities.carrier_inspections(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_carrier_inspections_dot_number
    ON entities.carrier_inspections(dot_number);
CREATE INDEX IF NOT EXISTS idx_carrier_inspections_unique_id
    ON entities.carrier_inspections(inspection_unique_id);
CREATE INDEX IF NOT EXISTS idx_carrier_inspections_report_number
    ON entities.carrier_inspections(report_number);

DROP TRIGGER IF EXISTS update_carrier_inspections_updated_at ON entities.carrier_inspections;
CREATE TRIGGER update_carrier_inspections_updated_at
    BEFORE UPDATE ON entities.carrier_inspections
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.carrier_inspections ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.motor_carrier_census_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    dot_number TEXT,
    legal_name TEXT,
    dba_name TEXT,
    carrier_operation_code TEXT,
    hazmat_flag BOOLEAN,
    passenger_carrier_flag BOOLEAN,
    physical_street TEXT,
    physical_city TEXT,
    physical_state TEXT,
    physical_zip TEXT,
    physical_country TEXT,
    mailing_street TEXT,
    mailing_city TEXT,
    mailing_state TEXT,
    mailing_zip TEXT,
    mailing_country TEXT,
    telephone TEXT,
    fax TEXT,
    email_address TEXT,
    mcs150_date DATE,
    mcs150_mileage BIGINT,
    mcs150_mileage_year INTEGER,
    add_date DATE,
    oic_state TEXT,
    power_unit_count INTEGER,
    driver_total INTEGER,
    recent_mileage BIGINT,
    recent_mileage_year INTEGER,
    vmt_source_id INTEGER,
    private_only BOOLEAN,
    authorized_for_hire BOOLEAN,
    exempt_for_hire BOOLEAN,
    private_property BOOLEAN,
    private_passenger_business BOOLEAN,
    private_passenger_nonbusiness BOOLEAN,
    migrant BOOLEAN,
    us_mail BOOLEAN,
    federal_government BOOLEAN,
    state_government BOOLEAN,
    local_government BOOLEAN,
    indian_tribe BOOLEAN,
    other_operation_description TEXT,
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

CREATE INDEX IF NOT EXISTS idx_motor_carrier_census_records_feed_date
    ON entities.motor_carrier_census_records(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_motor_carrier_census_records_dot_number
    ON entities.motor_carrier_census_records(dot_number);
CREATE INDEX IF NOT EXISTS idx_motor_carrier_census_records_legal_name
    ON entities.motor_carrier_census_records(legal_name);
CREATE INDEX IF NOT EXISTS idx_motor_carrier_census_records_carrier_operation_code
    ON entities.motor_carrier_census_records(carrier_operation_code);

DROP TRIGGER IF EXISTS update_motor_carrier_census_records_updated_at ON entities.motor_carrier_census_records;
CREATE TRIGGER update_motor_carrier_census_records_updated_at
    BEFORE UPDATE ON entities.motor_carrier_census_records
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.motor_carrier_census_records ENABLE ROW LEVEL SECURITY;

COMMIT;
