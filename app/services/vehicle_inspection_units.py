from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "vehicle_inspection_units"


def _build_vehicle_inspection_unit_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "inspection_id": clean_text(fields.get("INSPECTION_ID")),
        "inspection_unit_id": clean_text(fields.get("INSP_UNIT_ID")),
        "inspection_unit_type_id": parse_int(fields.get("INSP_UNIT_TYPE_ID")),
        "inspection_unit_number": parse_int(fields.get("INSP_UNIT_NUMBER")),
        "inspection_unit_make": clean_text(fields.get("INSP_UNIT_MAKE")),
        "inspection_unit_company_number": clean_text(fields.get("INSP_UNIT_COMPANY")),
        "inspection_unit_license": clean_text(fields.get("INSP_UNIT_LICENSE")),
        "inspection_unit_license_state": clean_text(fields.get("INSP_UNIT_LICENSE_STATE")),
        "inspection_unit_vin": clean_text(fields.get("INSP_UNIT_VEHICLE_ID_NUMBER")),
        "inspection_unit_decal_flag": clean_text(fields.get("INSP_UNIT_DECAL")),
        "inspection_unit_decal_number": clean_text(fields.get("INSP_UNIT_DECAL_NUMBER")),
    }


def upsert_vehicle_inspection_units(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_vehicle_inspection_unit_row,
    )
