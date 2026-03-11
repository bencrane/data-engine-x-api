from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "process_agent_filings"


def _build_process_agent_filing_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "docket_number": clean_text(fields.get("Docket Number")),
        "usdot_number": clean_text(fields.get("USDOT Number")),
        "process_agent_company_name": clean_text(fields.get("Company Name")),
        "attention_to_or_title": clean_text(fields.get("Attention to or Title")),
        "street_or_po_box": clean_text(fields.get("Street or PO Box")),
        "city": clean_text(fields.get("City")),
        "state": clean_text(fields.get("State")),
        "country": clean_text(fields.get("Country")),
        "zip_code": clean_text(fields.get("Zip Code")),
    }


def upsert_process_agent_filings(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_process_agent_filing_row,
    )
