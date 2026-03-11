from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_bool,
    parse_fmcsa_date,
    parse_int,
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


def upsert_carrier_inspections(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_carrier_inspection_row,
    )
