from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_mmddyyyy_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "operating_authority_histories"


def _build_history_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]
    docket_number = clean_text(fields.get("Docket Number"))
    usdot_number = clean_text(fields.get("USDOT Number"))
    sub_number = clean_text(fields.get("Sub Number"))
    operating_authority_type = clean_text(fields.get("Operating Authority Type"))
    original_authority_action_description = clean_text(
        fields.get("Original Authority Action Description")
    )
    original_authority_action_served_date = parse_mmddyyyy_date(
        fields.get("Original Authority Action Served Date")
    )
    final_authority_action_description = clean_text(
        fields.get("Final Authority Action Description")
    )
    final_authority_decision_date = parse_mmddyyyy_date(fields.get("Final Authority Decision Date"))
    final_authority_served_date = parse_mmddyyyy_date(fields.get("Final Authority Served Date"))

    return {
        "docket_number": docket_number,
        "usdot_number": usdot_number,
        "sub_number": sub_number,
        "operating_authority_type": operating_authority_type,
        "original_authority_action_description": original_authority_action_description,
        "original_authority_action_served_date": original_authority_action_served_date,
        "final_authority_action_description": final_authority_action_description,
        "final_authority_decision_date": final_authority_decision_date,
        "final_authority_served_date": final_authority_served_date,
    }


def upsert_operating_authority_histories(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_history_row,
    )
