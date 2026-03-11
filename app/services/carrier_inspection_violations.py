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

TABLE_NAME = "carrier_inspection_violations"


def _build_carrier_inspection_violation_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "inspection_unique_id": clean_text(fields.get("Unique_ID")),
        "inspection_date": parse_fmcsa_date(fields.get("Insp_Date")),
        "dot_number": clean_text(fields.get("DOT_Number")),
        "violation_code": clean_text(fields.get("Viol_Code")),
        "basic_description": clean_text(fields.get("BASIC_Desc")),
        "oos_indicator": parse_bool(fields.get("OOS_Indicator")),
        "oos_weight": parse_int(fields.get("OOS_Weight")),
        "severity_weight": parse_int(fields.get("Severity_Weight")),
        "time_weight": parse_int(fields.get("Time_Weight")),
        "total_severity_weight": parse_int(fields.get("Total_Severity_Wght")),
        "section_description": clean_text(fields.get("Section_Desc")),
        "group_description": clean_text(fields.get("Group_Desc")),
        "violation_unit": clean_text(fields.get("Viol_Unit")),
    }


def _parse_mcmis_oos_indicator(value: Any) -> bool | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    normalized = cleaned.upper()
    if normalized in {"Y", "Z"}:
        return True
    if normalized == "N":
        return False
    return None


def _build_vehicle_inspection_violation_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "inspection_unique_id": clean_text(fields.get("INSPECTION_ID")),
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "inspection_violation_id": clean_text(fields.get("INSP_VIOLATION_ID")),
        "violation_sequence_number": parse_int(fields.get("SEQ_NO")),
        "part_number": clean_text(fields.get("PART_NO")),
        "part_number_section": clean_text(fields.get("PART_NO_SECTION")),
        "violation_unit": clean_text(fields.get("INSP_VIOL_UNIT")),
        "inspection_unit_id": clean_text(fields.get("INSP_UNIT_ID")),
        "violation_category_id": parse_int(fields.get("INSP_VIOLATION_CATEGORY_ID")),
        "oos_indicator": _parse_mcmis_oos_indicator(fields.get("OUT_OF_SERVICE_INDICATOR")),
        "out_of_service_indicator_code": clean_text(fields.get("OUT_OF_SERVICE_INDICATOR")),
        "defect_verification_id": parse_int(fields.get("DEFECT_VERIFICATION_ID")),
        "citation_number": clean_text(fields.get("CITATION_NUMBER")),
    }


def upsert_carrier_inspection_violations(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    row_builder = (
        _build_vehicle_inspection_violation_row
        if source_context["feed_name"] == "Vehicle Inspections and Violations"
        else _build_carrier_inspection_violation_row
    )
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=row_builder,
    )
