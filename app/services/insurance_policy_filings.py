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

TABLE_NAME = "insurance_policy_filings"


def _build_insurance_policy_filing_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]
    docket_number = clean_text(fields.get("Docket Number"))
    usdot_number = clean_text(fields.get("USDOT Number"))
    form_code = clean_text(fields.get("Form Code"))
    insurance_type_description = clean_text(fields.get("Insurance Type Description"))
    insurance_company_name = clean_text(fields.get("Insurance Company Name"))
    policy_number = clean_text(fields.get("Policy Number"))
    posted_date = parse_mmddyyyy_date(fields.get("Posted Date"))
    bipd_underlying_limit_thousands_usd = parse_int(fields.get("BI&PD Underlying Limit"))
    bipd_maximum_limit_thousands_usd = parse_int(fields.get("BI&PD Maximum Limit"))
    effective_date = parse_mmddyyyy_date(fields.get("Effective Date"))
    cancel_effective_date = parse_mmddyyyy_date(fields.get("Cancel Effective Date"))

    return {
        "docket_number": docket_number,
        "usdot_number": usdot_number,
        "form_code": form_code,
        "insurance_type_description": insurance_type_description,
        "insurance_company_name": insurance_company_name,
        "policy_number": policy_number,
        "posted_date": posted_date,
        "bipd_underlying_limit_thousands_usd": bipd_underlying_limit_thousands_usd,
        "bipd_maximum_limit_thousands_usd": bipd_maximum_limit_thousands_usd,
        "effective_date": effective_date,
        "cancel_effective_date": cancel_effective_date,
    }


def upsert_insurance_policy_filings(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_insurance_policy_filing_row,
    )
