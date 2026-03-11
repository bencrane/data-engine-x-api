from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_int,
    parse_mmddyyyy_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "insurance_filing_rejections"


def _build_insurance_filing_rejection_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "docket_number": clean_text(fields.get("Docket Number")),
        "usdot_number": clean_text(fields.get("USDOT Number")),
        "form_code": clean_text(fields.get("Form Code (Insurance or Cancel)")),
        "insurance_type_description": clean_text(fields.get("Insurance Type Description")),
        "policy_number": clean_text(fields.get("Policy Number")),
        "received_date": parse_mmddyyyy_date(fields.get("Received Date")),
        "insurance_class_code": clean_text(fields.get("Insurance Class Code")),
        "insurance_type_code": clean_text(fields.get("Insurance Type Code")),
        "underlying_limit_amount_thousands_usd": parse_int(fields.get("Underlying Limit Amount")),
        "maximum_coverage_amount_thousands_usd": parse_int(fields.get("Maximum Coverage Amount")),
        "rejected_date": parse_mmddyyyy_date(fields.get("Rejected Date")),
        "insurance_branch": clean_text(fields.get("Insurance Branch")),
        "insurance_company_name": clean_text(fields.get("Company Name")),
        "rejected_reason": clean_text(fields.get("Rejected Reason")),
        "minimum_coverage_amount_thousands_usd": parse_int(fields.get("Minimum Coverage Amount")),
    }


def upsert_insurance_filing_rejections(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_insurance_filing_rejection_row,
    )
