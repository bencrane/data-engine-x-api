from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "vehicle_inspection_special_studies"


def _build_vehicle_inspection_special_study_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "inspection_id": clean_text(fields.get("INSPECTION_ID")),
        "inspection_study_id": clean_text(fields.get("INSP_STUDY_ID")),
        "study": clean_text(fields.get("STUDY")),
        "sequence_number": parse_int(fields.get("SEQ_NO")),
    }


def upsert_vehicle_inspection_special_studies(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_vehicle_inspection_special_study_row,
    )
