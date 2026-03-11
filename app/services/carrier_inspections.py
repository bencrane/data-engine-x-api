from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_bool,
    parse_fmcsa_date,
    parse_int,
    parse_yyyymmdd_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "carrier_inspections"


def _build_carrier_inspection_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "inspection_unique_id": clean_text(fields.get("Unique_ID")),
        "report_number": clean_text(fields.get("Report_Number")),
        "report_state": clean_text(fields.get("Report_State")),
        "dot_number": clean_text(fields.get("DOT_Number")),
        "inspection_date": parse_fmcsa_date(fields.get("Insp_Date")),
        "inspection_level_id": parse_int(fields.get("Insp_level_ID")),
        "county_code_state": clean_text(fields.get("County_code_State")),
        "time_weight": parse_int(fields.get("Time_Weight")),
        "driver_oos_total": parse_int(fields.get("Driver_OOS_Total")),
        "vehicle_oos_total": parse_int(fields.get("Vehicle_OOS_Total")),
        "total_hazmat_sent": parse_int(fields.get("Total_Hazmat_Sent")),
        "oos_total": parse_int(fields.get("OOS_Total")),
        "hazmat_oos_total": parse_int(fields.get("Hazmat_OOS_Total")),
        "hazmat_placard_required": parse_bool(fields.get("Hazmat_Placard_req")),
        "primary_unit_type_description": clean_text(fields.get("Unit_Type_Desc")),
        "primary_unit_make": clean_text(fields.get("Unit_Make")),
        "primary_unit_license": clean_text(fields.get("Unit_License")),
        "primary_unit_license_state": clean_text(fields.get("Unit_License_State")),
        "primary_unit_vin": clean_text(fields.get("VIN")),
        "primary_unit_decal_number": clean_text(fields.get("Unit_Decal_Number")),
        "secondary_unit_type_description": clean_text(fields.get("Unit_Type_Desc2")),
        "secondary_unit_make": clean_text(fields.get("Unit_Make2")),
        "secondary_unit_license": clean_text(fields.get("Unit_License2")),
        "secondary_unit_license_state": clean_text(fields.get("Unit_License_State2")),
        "secondary_unit_vin": clean_text(fields.get("VIN2")),
        "secondary_unit_decal_number": clean_text(fields.get("Unit_Decal_Number2")),
        "unsafe_driving_inspection": parse_bool(fields.get("Unsafe_Insp")),
        "hours_of_service_inspection": parse_bool(fields.get("Fatigued_Insp")),
        "driver_fitness_inspection": parse_bool(fields.get("Dr_Fitness_Insp")),
        "controlled_substances_alcohol_inspection": parse_bool(fields.get("Subt_Alcohol_Insp")),
        "vehicle_maintenance_inspection": parse_bool(fields.get("Vh_Maint_Insp")),
        "hazmat_inspection": parse_bool(fields.get("HM_Insp")),
        "basic_violation_total": parse_int(fields.get("BASIC_Viol")),
        "unsafe_driving_violation_total": parse_int(fields.get("Unsafe_Viol")),
        "hours_of_service_violation_total": parse_int(fields.get("Fatigued_Viol")),
        "driver_fitness_violation_total": parse_int(fields.get("Dr_Fitness_Viol")),
        "controlled_substances_alcohol_violation_total": parse_int(fields.get("Subt_Alcohol_Viol")),
        "vehicle_maintenance_violation_total": parse_int(fields.get("Vh_Maint_Viol")),
        "hazmat_violation_total": parse_int(fields.get("HM_Viol")),
    }


def _build_vehicle_inspection_file_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "inspection_unique_id": clean_text(fields.get("INSPECTION_ID")),
        "report_number": clean_text(fields.get("REPORT_NUMBER")),
        "report_state": clean_text(fields.get("REPORT_STATE")),
        "dot_number": clean_text(fields.get("DOT_NUMBER")),
        "inspection_date": parse_yyyymmdd_date(fields.get("INSP_DATE")),
        "inspection_level_id": parse_int(fields.get("INSP_LEVEL_ID")),
        "county_code_state": clean_text(fields.get("COUNTY_CODE_STATE")),
        "hazmat_placard_required": parse_bool(fields.get("HAZMAT_PLACARD_REQ")),
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "inspection_start_time_text": clean_text(fields.get("INSP_START_TIME")),
        "inspection_end_time_text": clean_text(fields.get("INSP_END_TIME")),
        "registration_date": parse_yyyymmdd_date(fields.get("REGISTRATION_DATE")),
        "region_code": clean_text(fields.get("REGION")),
        "ci_status_code": clean_text(fields.get("CI_STATUS_CODE")),
        "location_code": clean_text(fields.get("LOCATION")),
        "location_description": clean_text(fields.get("LOCATION_DESC")),
        "county_code": clean_text(fields.get("COUNTY_CODE")),
        "service_center": clean_text(fields.get("SERVICE_CENTER")),
        "census_source_id": parse_int(fields.get("CENSUS_SOURCE_ID")),
        "inspection_facility_code": clean_text(fields.get("INSP_FACILITY")),
        "shipper_name": clean_text(fields.get("SHIPPER_NAME")),
        "shipping_paper_number": clean_text(fields.get("SHIPPING_PAPER_NUMBER")),
        "cargo_tank_code": clean_text(fields.get("CARGO_TANK")),
        "snet_version_number": clean_text(fields.get("SNET_VERSION_NUMBER")),
        "snet_search_date_text": clean_text(fields.get("SNET_SEARCH_DATE")),
        "alcohol_control_substance_code": clean_text(fields.get("ALCOHOL_CONTROL_SUB")),
        "drug_interdiction_search_code": clean_text(fields.get("DRUG_INTRDCTN_SEARCH")),
        "drug_interdiction_arrests": parse_int(fields.get("DRUG_INTRDCTN_ARRESTS")),
        "size_weight_enforcement_code": clean_text(fields.get("SIZE_WEIGHT_ENF")),
        "traffic_enforcement_code": clean_text(fields.get("TRAFFIC_ENF")),
        "local_enforcement_jurisdiction_code": clean_text(fields.get("LOCAL_ENF_JURISDICTION")),
        "pen_census_match_code": clean_text(fields.get("PEN_CEN_MATCH")),
        "final_status_date_text": clean_text(fields.get("FINAL_STATUS_DATE")),
        "post_accident_indicator_code": clean_text(fields.get("POST_ACC_IND")),
        "gross_combination_vehicle_weight_pounds": parse_int(fields.get("GROSS_COMB_VEH_WT")),
        "total_violation_count": parse_int(fields.get("VIOL_TOTAL")),
        "total_out_of_service_count": parse_int(fields.get("OOS_TOTAL")),
        "driver_violation_count": parse_int(fields.get("DRIVER_VIOL_TOTAL")),
        "driver_out_of_service_count": parse_int(fields.get("DRIVER_OOS_TOTAL")),
        "vehicle_violation_count": parse_int(fields.get("VEHICLE_VIOL_TOTAL")),
        "vehicle_out_of_service_count": parse_int(fields.get("VEHICLE_OOS_TOTAL")),
        "hazmat_violation_count": parse_int(fields.get("HAZMAT_VIOL_TOTAL")),
        "hazmat_out_of_service_count": parse_int(fields.get("HAZMAT_OOS_TOTAL")),
        "snet_sequence_id_text": clean_text(fields.get("SNET_SEQUENCE_ID")),
        "transaction_code": clean_text(fields.get("TRANSACTION_CODE")),
        "transaction_date_text": clean_text(fields.get("TRANSACTION_DATE")),
        "upload_date_text": clean_text(fields.get("UPLOAD_DATE")),
        "upload_first_byte": clean_text(fields.get("UPLOAD_FIRST_BYTE")),
        "upload_dot_number": clean_text(fields.get("UPLOAD_DOT_NUMBER")),
        "upload_search_indicator": clean_text(fields.get("UPLOAD_SEARCH_INDICATOR")),
        "census_search_date_text": clean_text(fields.get("CENSUS_SEARCH_DATE")),
        "snet_input_date_text": clean_text(fields.get("SNET_INPUT_DATE")),
        "source_office": clean_text(fields.get("SOURCE_OFFICE")),
        "mcmis_add_date_text": clean_text(fields.get("MCMIS_ADD_DATE")),
        "carrier_name": clean_text(fields.get("INSP_CARRIER_NAME")),
        "carrier_street": clean_text(fields.get("INSP_CARRIER_STREET")),
        "carrier_city": clean_text(fields.get("INSP_CARRIER_CITY")),
        "carrier_state": clean_text(fields.get("INSP_CARRIER_STATE")),
        "carrier_zip_code": clean_text(fields.get("INSP_CARRIER_ZIP_CODE")),
        "carrier_colonia": clean_text(fields.get("INSP_COLONIA")),
        "docket_number": clean_text(fields.get("DOCKET_NUMBER")),
        "interstate_operation_code": clean_text(fields.get("INSP_INTERSTATE")),
        "carrier_state_id": clean_text(fields.get("INSP_CARRIER_STATE_ID")),
    }


def upsert_carrier_inspections(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    row_builder = (
        _build_vehicle_inspection_file_row
        if source_context["feed_name"] == "Vehicle Inspection File"
        else _build_carrier_inspection_row
    )
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=row_builder,
    )
