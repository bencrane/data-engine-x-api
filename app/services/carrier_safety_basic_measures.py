from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_bool,
    parse_float,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "carrier_safety_basic_measures"

CARRIER_SEGMENTS = {
    "SMS AB PassProperty": "interstate_and_intrastate_hazmat_property_or_passenger",
    "SMS C PassProperty": "intrastate_non_hazmat_property_or_passenger",
}


def _build_basic_measure_row(row: FmcsaDailyDiffRow, *, carrier_segment: str) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "carrier_segment": carrier_segment,
        "dot_number": clean_text(fields.get("DOT_NUMBER")),
        "inspection_total": parse_int(fields.get("INSP_TOTAL")),
        "driver_inspection_total": parse_int(fields.get("DRIVER_INSP_TOTAL")),
        "driver_oos_inspection_total": parse_int(fields.get("DRIVER_OOS_INSP_TOTAL")),
        "vehicle_inspection_total": parse_int(fields.get("VEHICLE_INSP_TOTAL")),
        "vehicle_oos_inspection_total": parse_int(fields.get("VEHICLE_OOS_INSP_TOTAL")),
        "unsafe_driving_inspections_with_violations": parse_int(fields.get("UNSAFE_DRIV_INSP_W_VIOL")),
        "unsafe_driving_measure": parse_float(fields.get("UNSAFE_DRIV_MEASURE")),
        "unsafe_driving_acute_critical": parse_bool(fields.get("UNSAFE_DRIV_AC")),
        "hours_of_service_inspections_with_violations": parse_int(fields.get("HOS_DRIV_INSP_W_VIOL")),
        "hours_of_service_measure": parse_float(fields.get("HOS_DRIV_MEASURE")),
        "hours_of_service_acute_critical": parse_bool(fields.get("HOS_DRIV_AC")),
        "driver_fitness_inspections_with_violations": parse_int(fields.get("DRIV_FIT_INSP_W_VIOL")),
        "driver_fitness_measure": parse_float(fields.get("DRIV_FIT_MEASURE")),
        "driver_fitness_acute_critical": parse_bool(fields.get("DRIV_FIT_AC")),
        "controlled_substances_alcohol_inspections_with_violations": parse_int(
            fields.get("CONTR_SUBST_INSP_W_VIOL")
        ),
        "controlled_substances_alcohol_measure": parse_float(fields.get("CONTR_SUBST_MEASURE")),
        "controlled_substances_alcohol_acute_critical": parse_bool(fields.get("CONTR_SUBST_AC")),
        "vehicle_maintenance_inspections_with_violations": parse_int(fields.get("VEH_MAINT_INSP_W_VIOL")),
        "vehicle_maintenance_measure": parse_float(fields.get("VEH_MAINT_MEASURE")),
        "vehicle_maintenance_acute_critical": parse_bool(fields.get("VEH_MAINT_AC")),
    }


def upsert_carrier_safety_basic_measures(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    carrier_segment = CARRIER_SEGMENTS[source_context["feed_name"]]
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=lambda row: _build_basic_measure_row(row, carrier_segment=carrier_segment),
    )
