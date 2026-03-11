from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_bool,
    parse_int,
    parse_yyyymmdd_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "commercial_vehicle_crashes"


def _build_commercial_vehicle_crash_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "crash_id": clean_text(fields.get("CRASH_ID")),
        "report_state": clean_text(fields.get("REPORT_STATE")),
        "report_number": clean_text(fields.get("REPORT_NUMBER")),
        "report_date": parse_yyyymmdd_date(fields.get("REPORT_DATE")),
        "report_time_text": clean_text(fields.get("REPORT_TIME")),
        "report_sequence_number": parse_int(fields.get("REPORT_SEQ_NO")),
        "dot_number": clean_text(fields.get("DOT_NUMBER")),
        "ci_status_code": clean_text(fields.get("CI_STATUS_CODE")),
        "final_status_date": parse_yyyymmdd_date(fields.get("FINAL_STATUS_DATE")),
        "location": clean_text(fields.get("LOCATION")),
        "city_code": clean_text(fields.get("CITY_CODE")),
        "city": clean_text(fields.get("CITY")),
        "state": clean_text(fields.get("STATE")),
        "county_code": clean_text(fields.get("COUNTY_CODE")),
        "truck_bus_indicator": clean_text(fields.get("TRUCK_BUS_IND")),
        "trafficway_id": clean_text(fields.get("TRAFFICWAY_ID")),
        "access_control_id": clean_text(fields.get("ACCESS_CONTROL_ID")),
        "road_surface_condition_id": clean_text(fields.get("ROAD_SURFACE_CONDITION_ID")),
        "cargo_body_type_id": clean_text(fields.get("CARGO_BODY_TYPE_ID")),
        "gvw_rating_id": clean_text(fields.get("GVW_RATING_ID")),
        "vehicle_identification_number": clean_text(fields.get("VEHICLE_IDENTIFICATION_NUMBER")),
        "vehicle_license_number": clean_text(fields.get("VEHICLE_LICENSE_NUMBER")),
        "vehicle_license_state": clean_text(fields.get("VEHICLE_LIC_STATE")),
        "vehicle_hazmat_placard": parse_bool(fields.get("VEHICLE_HAZMAT_PLACARD")),
        "weather_condition_id": clean_text(fields.get("WEATHER_CONDITION_ID")),
        "vehicle_configuration_id": clean_text(fields.get("VEHICLE_CONFIGURATION_ID")),
        "light_condition_id": clean_text(fields.get("LIGHT_CONDITION_ID")),
        "hazmat_released": parse_bool(fields.get("HAZMAT_RELEASED")),
        "agency": clean_text(fields.get("AGENCY")),
        "vehicles_in_accident": parse_int(fields.get("VEHICLES_IN_ACCIDENT")),
        "fatalities": parse_int(fields.get("FATALITIES")),
        "injuries": parse_int(fields.get("INJURIES")),
        "tow_away": parse_bool(fields.get("TOW_AWAY")),
        "federal_recordable": parse_bool(fields.get("FEDERAL_RECORDABLE")),
        "state_recordable": parse_bool(fields.get("STATE_RECORDABLE")),
        "snet_version_number": clean_text(fields.get("SNET_VERSION_NUMBER")),
        "snet_sequence_id": clean_text(fields.get("SNET_SEQUENCE_ID")),
        "transaction_code": clean_text(fields.get("TRANSACTION_CODE")),
        "transaction_date_text": clean_text(fields.get("TRANSACTION_DATE")),
        "upload_first_byte": clean_text(fields.get("UPLOAD_FIRST_BYTE")),
        "upload_dot_number": clean_text(fields.get("UPLOAD_DOT_NUMBER")),
        "upload_search_indicator": clean_text(fields.get("UPLOAD_SEARCH_INDICATOR")),
        "upload_date_text": clean_text(fields.get("UPLOAD_DATE")),
        "add_date_text": clean_text(fields.get("ADD_DATE")),
        "crash_carrier_id": clean_text(fields.get("CRASH_CARRIER_ID")),
        "crash_carrier_name": clean_text(fields.get("CRASH_CARRIER_NAME")),
        "crash_carrier_street": clean_text(fields.get("CRASH_CARRIER_STREET")),
        "crash_carrier_city": clean_text(fields.get("CRASH_CARRIER_CITY")),
        "crash_carrier_city_code": clean_text(fields.get("CRASH_CARRIER_CITY_CODE")),
        "crash_carrier_state": clean_text(fields.get("CRASH_CARRIER_STATE")),
        "crash_carrier_zip_code": clean_text(fields.get("CRASH_CARRIER_ZIP_CODE")),
        "crash_colonia": clean_text(fields.get("CRASH_COLONIA")),
        "docket_number": clean_text(fields.get("DOCKET_NUMBER")),
        "crash_carrier_interstate_code": clean_text(fields.get("CRASH_CARRIER_INTERSTATE")),
        "no_id_flag": clean_text(fields.get("NO_ID_FLAG")),
        "state_number": clean_text(fields.get("STATE_NUMBER")),
        "state_issuing_number": clean_text(fields.get("STATE_ISSUING_NUMBER")),
        "crash_event_sequence_description": clean_text(fields.get("CRASH_EVENT_SEQ_ID_DESC")),
    }


def upsert_commercial_vehicle_crashes(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_commercial_vehicle_crash_row,
    )
