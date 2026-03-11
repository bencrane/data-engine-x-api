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


def upsert_carrier_inspection_violations(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_carrier_inspection_violation_row,
    )
