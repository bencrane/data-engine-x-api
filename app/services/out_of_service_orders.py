from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_iso_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "out_of_service_orders"


def _build_out_of_service_order_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "dot_number": clean_text(fields.get("DOT_NUMBER")),
        "legal_name": clean_text(fields.get("LEGAL_NAME")),
        "dba_name": clean_text(fields.get("DBA_NAME")),
        "oos_date": parse_iso_date(fields.get("OOS_DATE")),
        "oos_reason": clean_text(fields.get("OOS_REASON")),
        "status": clean_text(fields.get("STATUS")),
        "oos_rescind_date": parse_iso_date(fields.get("OOS_RESCIND_DATE")),
    }


def upsert_out_of_service_orders(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_out_of_service_order_row,
    )
