from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "vehicle_inspection_citations"


def _build_vehicle_inspection_citation_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "change_date_text": clean_text(fields.get("CHANGE_DATE")),
        "inspection_id": clean_text(fields.get("INSPECTION_ID")),
        "violation_sequence_number": parse_int(fields.get("VIOSEQNUM")),
        "adjusted_sequence_number": parse_int(fields.get("ADJSEQ")),
        "citation_code": clean_text(fields.get("CITATION_CODE")),
        "citation_result": clean_text(fields.get("CITATION_RESULT")),
    }


def upsert_vehicle_inspection_citations(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_vehicle_inspection_citation_row,
    )
