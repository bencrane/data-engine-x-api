BEGIN;

CREATE SCHEMA IF NOT EXISTS entities;

CREATE TABLE IF NOT EXISTS entities.commercial_vehicle_crashes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    change_date_text TEXT,
    crash_id TEXT,
    report_state TEXT,
    report_number TEXT,
    report_date DATE,
    report_time_text TEXT,
    report_sequence_number INTEGER,
    dot_number TEXT,
    ci_status_code TEXT,
    final_status_date DATE,
    location TEXT,
    city_code TEXT,
    city TEXT,
    state TEXT,
    county_code TEXT,
    truck_bus_indicator TEXT,
    trafficway_id TEXT,
    access_control_id TEXT,
    road_surface_condition_id TEXT,
    cargo_body_type_id TEXT,
    gvw_rating_id TEXT,
    vehicle_identification_number TEXT,
    vehicle_license_number TEXT,
    vehicle_license_state TEXT,
    vehicle_hazmat_placard BOOLEAN,
    weather_condition_id TEXT,
    vehicle_configuration_id TEXT,
    light_condition_id TEXT,
    hazmat_released BOOLEAN,
    agency TEXT,
    vehicles_in_accident INTEGER,
    fatalities INTEGER,
    injuries INTEGER,
    tow_away BOOLEAN,
    federal_recordable BOOLEAN,
    state_recordable BOOLEAN,
    snet_version_number TEXT,
    snet_sequence_id TEXT,
    transaction_code TEXT,
    transaction_date_text TEXT,
    upload_first_byte TEXT,
    upload_dot_number TEXT,
    upload_search_indicator TEXT,
    upload_date_text TEXT,
    add_date_text TEXT,
    crash_carrier_id TEXT,
    crash_carrier_name TEXT,
    crash_carrier_street TEXT,
    crash_carrier_city TEXT,
    crash_carrier_city_code TEXT,
    crash_carrier_state TEXT,
    crash_carrier_zip_code TEXT,
    crash_colonia TEXT,
    docket_number TEXT,
    crash_carrier_interstate_code TEXT,
    no_id_flag TEXT,
    state_number TEXT,
    state_issuing_number TEXT,
    crash_event_sequence_description TEXT,
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

CREATE INDEX IF NOT EXISTS idx_commercial_vehicle_crashes_feed_date
    ON entities.commercial_vehicle_crashes(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_commercial_vehicle_crashes_crash_id
    ON entities.commercial_vehicle_crashes(crash_id);
CREATE INDEX IF NOT EXISTS idx_commercial_vehicle_crashes_dot_number
    ON entities.commercial_vehicle_crashes(dot_number);
CREATE INDEX IF NOT EXISTS idx_commercial_vehicle_crashes_docket_number
    ON entities.commercial_vehicle_crashes(docket_number);
CREATE INDEX IF NOT EXISTS idx_commercial_vehicle_crashes_report_date
    ON entities.commercial_vehicle_crashes(report_date DESC);

DROP TRIGGER IF EXISTS update_commercial_vehicle_crashes_updated_at ON entities.commercial_vehicle_crashes;
CREATE TRIGGER update_commercial_vehicle_crashes_updated_at
    BEFORE UPDATE ON entities.commercial_vehicle_crashes
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.commercial_vehicle_crashes ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.vehicle_inspection_units (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    change_date_text TEXT,
    inspection_id TEXT,
    inspection_unit_id TEXT,
    inspection_unit_type_id INTEGER,
    inspection_unit_number INTEGER,
    inspection_unit_make TEXT,
    inspection_unit_company_number TEXT,
    inspection_unit_license TEXT,
    inspection_unit_license_state TEXT,
    inspection_unit_vin TEXT,
    inspection_unit_decal_flag TEXT,
    inspection_unit_decal_number TEXT,
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

CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_units_feed_date
    ON entities.vehicle_inspection_units(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_units_inspection_id
    ON entities.vehicle_inspection_units(inspection_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_units_inspection_unit_id
    ON entities.vehicle_inspection_units(inspection_unit_id);

DROP TRIGGER IF EXISTS update_vehicle_inspection_units_updated_at ON entities.vehicle_inspection_units;
CREATE TRIGGER update_vehicle_inspection_units_updated_at
    BEFORE UPDATE ON entities.vehicle_inspection_units
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.vehicle_inspection_units ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.vehicle_inspection_special_studies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    change_date_text TEXT,
    inspection_id TEXT,
    inspection_study_id TEXT,
    study TEXT,
    sequence_number INTEGER,
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

CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_special_studies_feed_date
    ON entities.vehicle_inspection_special_studies(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_special_studies_inspection_id
    ON entities.vehicle_inspection_special_studies(inspection_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_special_studies_study_id
    ON entities.vehicle_inspection_special_studies(inspection_study_id);

DROP TRIGGER IF EXISTS update_vehicle_inspection_special_studies_updated_at ON entities.vehicle_inspection_special_studies;
CREATE TRIGGER update_vehicle_inspection_special_studies_updated_at
    BEFORE UPDATE ON entities.vehicle_inspection_special_studies
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.vehicle_inspection_special_studies ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.vehicle_inspection_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    change_date_text TEXT,
    inspection_id TEXT,
    violation_sequence_number INTEGER,
    adjusted_sequence_number INTEGER,
    citation_code TEXT,
    citation_result TEXT,
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

CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_citations_feed_date
    ON entities.vehicle_inspection_citations(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_citations_inspection_id
    ON entities.vehicle_inspection_citations(inspection_id);
CREATE INDEX IF NOT EXISTS idx_vehicle_inspection_citations_violation_sequence
    ON entities.vehicle_inspection_citations(violation_sequence_number);

DROP TRIGGER IF EXISTS update_vehicle_inspection_citations_updated_at ON entities.vehicle_inspection_citations;
CREATE TRIGGER update_vehicle_inspection_citations_updated_at
    BEFORE UPDATE ON entities.vehicle_inspection_citations
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.vehicle_inspection_citations ENABLE ROW LEVEL SECURITY;

CREATE TABLE IF NOT EXISTS entities.out_of_service_orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feed_date DATE NOT NULL,
    row_position INTEGER NOT NULL,
    dot_number TEXT,
    legal_name TEXT,
    dba_name TEXT,
    oos_date DATE,
    oos_reason TEXT,
    status TEXT,
    oos_rescind_date DATE,
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

CREATE INDEX IF NOT EXISTS idx_out_of_service_orders_feed_date
    ON entities.out_of_service_orders(feed_date DESC);
CREATE INDEX IF NOT EXISTS idx_out_of_service_orders_dot_number
    ON entities.out_of_service_orders(dot_number);
CREATE INDEX IF NOT EXISTS idx_out_of_service_orders_oos_date
    ON entities.out_of_service_orders(oos_date DESC);

DROP TRIGGER IF EXISTS update_out_of_service_orders_updated_at ON entities.out_of_service_orders;
CREATE TRIGGER update_out_of_service_orders_updated_at
    BEFORE UPDATE ON entities.out_of_service_orders
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entities.out_of_service_orders ENABLE ROW LEVEL SECURITY;

ALTER TABLE entities.carrier_inspections
    ADD COLUMN IF NOT EXISTS change_date_text TEXT,
    ADD COLUMN IF NOT EXISTS inspection_start_time_text TEXT,
    ADD COLUMN IF NOT EXISTS inspection_end_time_text TEXT,
    ADD COLUMN IF NOT EXISTS registration_date DATE,
    ADD COLUMN IF NOT EXISTS region_code TEXT,
    ADD COLUMN IF NOT EXISTS ci_status_code TEXT,
    ADD COLUMN IF NOT EXISTS location_code TEXT,
    ADD COLUMN IF NOT EXISTS location_description TEXT,
    ADD COLUMN IF NOT EXISTS county_code TEXT,
    ADD COLUMN IF NOT EXISTS service_center TEXT,
    ADD COLUMN IF NOT EXISTS census_source_id INTEGER,
    ADD COLUMN IF NOT EXISTS inspection_facility_code TEXT,
    ADD COLUMN IF NOT EXISTS shipper_name TEXT,
    ADD COLUMN IF NOT EXISTS shipping_paper_number TEXT,
    ADD COLUMN IF NOT EXISTS cargo_tank_code TEXT,
    ADD COLUMN IF NOT EXISTS snet_version_number TEXT,
    ADD COLUMN IF NOT EXISTS snet_search_date_text TEXT,
    ADD COLUMN IF NOT EXISTS alcohol_control_substance_code TEXT,
    ADD COLUMN IF NOT EXISTS drug_interdiction_search_code TEXT,
    ADD COLUMN IF NOT EXISTS drug_interdiction_arrests INTEGER,
    ADD COLUMN IF NOT EXISTS size_weight_enforcement_code TEXT,
    ADD COLUMN IF NOT EXISTS traffic_enforcement_code TEXT,
    ADD COLUMN IF NOT EXISTS local_enforcement_jurisdiction_code TEXT,
    ADD COLUMN IF NOT EXISTS pen_census_match_code TEXT,
    ADD COLUMN IF NOT EXISTS final_status_date_text TEXT,
    ADD COLUMN IF NOT EXISTS post_accident_indicator_code TEXT,
    ADD COLUMN IF NOT EXISTS gross_combination_vehicle_weight_pounds INTEGER,
    ADD COLUMN IF NOT EXISTS total_violation_count INTEGER,
    ADD COLUMN IF NOT EXISTS total_out_of_service_count INTEGER,
    ADD COLUMN IF NOT EXISTS driver_violation_count INTEGER,
    ADD COLUMN IF NOT EXISTS driver_out_of_service_count INTEGER,
    ADD COLUMN IF NOT EXISTS vehicle_violation_count INTEGER,
    ADD COLUMN IF NOT EXISTS vehicle_out_of_service_count INTEGER,
    ADD COLUMN IF NOT EXISTS hazmat_violation_count INTEGER,
    ADD COLUMN IF NOT EXISTS hazmat_out_of_service_count INTEGER,
    ADD COLUMN IF NOT EXISTS snet_sequence_id_text TEXT,
    ADD COLUMN IF NOT EXISTS transaction_code TEXT,
    ADD COLUMN IF NOT EXISTS transaction_date_text TEXT,
    ADD COLUMN IF NOT EXISTS upload_date_text TEXT,
    ADD COLUMN IF NOT EXISTS upload_first_byte TEXT,
    ADD COLUMN IF NOT EXISTS upload_dot_number TEXT,
    ADD COLUMN IF NOT EXISTS upload_search_indicator TEXT,
    ADD COLUMN IF NOT EXISTS census_search_date_text TEXT,
    ADD COLUMN IF NOT EXISTS snet_input_date_text TEXT,
    ADD COLUMN IF NOT EXISTS source_office TEXT,
    ADD COLUMN IF NOT EXISTS mcmis_add_date_text TEXT,
    ADD COLUMN IF NOT EXISTS carrier_name TEXT,
    ADD COLUMN IF NOT EXISTS carrier_street TEXT,
    ADD COLUMN IF NOT EXISTS carrier_city TEXT,
    ADD COLUMN IF NOT EXISTS carrier_state TEXT,
    ADD COLUMN IF NOT EXISTS carrier_zip_code TEXT,
    ADD COLUMN IF NOT EXISTS carrier_colonia TEXT,
    ADD COLUMN IF NOT EXISTS docket_number TEXT,
    ADD COLUMN IF NOT EXISTS interstate_operation_code TEXT,
    ADD COLUMN IF NOT EXISTS carrier_state_id TEXT;

CREATE INDEX IF NOT EXISTS idx_carrier_inspections_docket_number
    ON entities.carrier_inspections(docket_number);

ALTER TABLE entities.carrier_inspection_violations
    ADD COLUMN IF NOT EXISTS change_date_text TEXT,
    ADD COLUMN IF NOT EXISTS inspection_violation_id TEXT,
    ADD COLUMN IF NOT EXISTS violation_sequence_number INTEGER,
    ADD COLUMN IF NOT EXISTS part_number TEXT,
    ADD COLUMN IF NOT EXISTS part_number_section TEXT,
    ADD COLUMN IF NOT EXISTS inspection_unit_id TEXT,
    ADD COLUMN IF NOT EXISTS violation_category_id INTEGER,
    ADD COLUMN IF NOT EXISTS out_of_service_indicator_code TEXT,
    ADD COLUMN IF NOT EXISTS defect_verification_id INTEGER,
    ADD COLUMN IF NOT EXISTS citation_number TEXT;

CREATE INDEX IF NOT EXISTS idx_carrier_inspection_violations_inspection_violation_id
    ON entities.carrier_inspection_violations(inspection_violation_id);

ALTER TABLE entities.motor_carrier_census_records
    ADD COLUMN IF NOT EXISTS status_code TEXT,
    ADD COLUMN IF NOT EXISTS dun_bradstreet_number TEXT,
    ADD COLUMN IF NOT EXISTS physical_omc_region INTEGER,
    ADD COLUMN IF NOT EXISTS safety_investigator_territory_code TEXT,
    ADD COLUMN IF NOT EXISTS business_organization_id TEXT,
    ADD COLUMN IF NOT EXISTS mcs151_mileage BIGINT,
    ADD COLUMN IF NOT EXISTS total_cars INTEGER,
    ADD COLUMN IF NOT EXISTS mcs150_update_code_id TEXT,
    ADD COLUMN IF NOT EXISTS prior_revoke_flag BOOLEAN,
    ADD COLUMN IF NOT EXISTS prior_revoke_dot_number TEXT,
    ADD COLUMN IF NOT EXISTS cell_phone TEXT,
    ADD COLUMN IF NOT EXISTS company_officer_1 TEXT,
    ADD COLUMN IF NOT EXISTS company_officer_2 TEXT,
    ADD COLUMN IF NOT EXISTS business_organization_description TEXT,
    ADD COLUMN IF NOT EXISTS truck_units INTEGER,
    ADD COLUMN IF NOT EXISTS bus_units INTEGER,
    ADD COLUMN IF NOT EXISTS fleet_size_code TEXT,
    ADD COLUMN IF NOT EXISTS review_id TEXT,
    ADD COLUMN IF NOT EXISTS recordable_crash_rate NUMERIC,
    ADD COLUMN IF NOT EXISTS mail_nationality_indicator TEXT,
    ADD COLUMN IF NOT EXISTS physical_nationality_indicator TEXT,
    ADD COLUMN IF NOT EXISTS physical_barrio TEXT,
    ADD COLUMN IF NOT EXISTS mailing_barrio TEXT,
    ADD COLUMN IF NOT EXISTS entity_type_code TEXT,
    ADD COLUMN IF NOT EXISTS docket1_prefix TEXT,
    ADD COLUMN IF NOT EXISTS docket1_number TEXT,
    ADD COLUMN IF NOT EXISTS docket2_prefix TEXT,
    ADD COLUMN IF NOT EXISTS docket2_number TEXT,
    ADD COLUMN IF NOT EXISTS docket3_prefix TEXT,
    ADD COLUMN IF NOT EXISTS docket3_number TEXT,
    ADD COLUMN IF NOT EXISTS point_number TEXT,
    ADD COLUMN IF NOT EXISTS total_intrastate_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS mcsip_step INTEGER,
    ADD COLUMN IF NOT EXISTS mcsip_date DATE,
    ADD COLUMN IF NOT EXISTS interstate_beyond_100_miles_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS interstate_within_100_miles_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS intrastate_beyond_100_miles_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS intrastate_within_100_miles_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS total_cdl_drivers INTEGER,
    ADD COLUMN IF NOT EXISTS average_trip_leased_drivers_per_month INTEGER,
    ADD COLUMN IF NOT EXISTS classdef_text TEXT,
    ADD COLUMN IF NOT EXISTS physical_county_code TEXT,
    ADD COLUMN IF NOT EXISTS mailing_county_code TEXT,
    ADD COLUMN IF NOT EXISTS mailing_undeliverable_date DATE,
    ADD COLUMN IF NOT EXISTS driver_inter_total INTEGER,
    ADD COLUMN IF NOT EXISTS review_type_code TEXT,
    ADD COLUMN IF NOT EXISTS review_date DATE,
    ADD COLUMN IF NOT EXISTS safety_rating_code TEXT,
    ADD COLUMN IF NOT EXISTS safety_rating_date DATE,
    ADD COLUMN IF NOT EXISTS undeliverable_physical_code TEXT,
    ADD COLUMN IF NOT EXISTS cargo_general_freight BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_household_goods BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_metal_sheets_coils_rolls BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_motor_vehicles BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_driveaway_towaway BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_logs_poles_beams_lumber BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_building_materials BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_mobile_homes BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_machinery_large_objects BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_fresh_produce BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_liquids_gases BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_intermodal_containers BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_passengers BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_oilfield_equipment BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_livestock BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_grain_feed_hay BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_coal_coke BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_meat BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_garbage_refuse_trash BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_us_mail BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_chemicals BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_dry_bulk_commodities BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_refrigerated_food BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_beverages BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_paper_products BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_utility BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_farm_supplies BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_construction BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_water_well BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_other BOOLEAN,
    ADD COLUMN IF NOT EXISTS cargo_other_description TEXT,
    ADD COLUMN IF NOT EXISTS owned_truck_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_tractor_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_trailer_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_motor_coach_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_school_bus_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_school_bus_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_school_bus_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_minibus_van_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_minibus_van_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_minibus_van_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_limo_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_limo_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS owned_limo_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_truck_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_tractor_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_trailer_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_motor_coach_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_school_bus_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_school_bus_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_school_bus_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_minibus_van_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_minibus_van_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_minibus_van_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_limo_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_limo_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS term_leased_limo_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_truck_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_tractor_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_trailer_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_motor_coach_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_school_bus_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_school_bus_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_school_bus_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_minibus_van_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_minibus_van_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_minibus_van_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_limo_1_8_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_limo_9_15_units INTEGER,
    ADD COLUMN IF NOT EXISTS trip_leased_limo_16_plus_units INTEGER,
    ADD COLUMN IF NOT EXISTS docket1_status_code TEXT,
    ADD COLUMN IF NOT EXISTS docket2_status_code TEXT,
    ADD COLUMN IF NOT EXISTS docket3_status_code TEXT;

CREATE INDEX IF NOT EXISTS idx_motor_carrier_census_records_status_code
    ON entities.motor_carrier_census_records(status_code);

COMMIT;
