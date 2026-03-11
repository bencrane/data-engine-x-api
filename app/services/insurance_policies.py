from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    build_record_fingerprint,
    clean_text,
    is_blank_or_zero,
    parse_int,
    parse_mmddyyyy_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "insurance_policies"

INSURANCE_TYPE_DESCRIPTIONS = {
    "1": "BI&PD",
    "2": "Cargo",
    "3": "Bond",
    "4": "Trust Fund",
}


def _build_insurance_policy_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]
    docket_number = clean_text(fields.get("Docket Number"))

    is_removal_signal = all(
        is_blank_or_zero(fields.get(field_name))
        for field_name in (
            "Insurance Type",
            "BI&PD Class",
            "BI&PD Maximum Dollar Limit",
            "BI&PD Underlying Dollar Limit",
            "Policy Number",
            "Effective Date",
            "Form Code",
            "Insurance Company Name",
        )
    )

    insurance_type_code = clean_text(fields.get("Insurance Type"))
    bipd_class_code = clean_text(fields.get("BI&PD Class"))
    bipd_maximum_dollar_limit_thousands_usd = parse_int(fields.get("BI&PD Maximum Dollar Limit"))
    bipd_underlying_dollar_limit_thousands_usd = parse_int(
        fields.get("BI&PD Underlying Dollar Limit")
    )
    policy_number = clean_text(fields.get("Policy Number"))
    effective_date = parse_mmddyyyy_date(fields.get("Effective Date"))
    form_code = clean_text(fields.get("Form Code"))
    insurance_company_name = clean_text(fields.get("Insurance Company Name"))

    return {
        "record_fingerprint": build_record_fingerprint(
            docket_number=docket_number,
            insurance_type_code=insurance_type_code,
            bipd_class_code=bipd_class_code,
            bipd_maximum_dollar_limit_thousands_usd=bipd_maximum_dollar_limit_thousands_usd,
            bipd_underlying_dollar_limit_thousands_usd=bipd_underlying_dollar_limit_thousands_usd,
            policy_number=policy_number,
            effective_date=effective_date,
            form_code=form_code,
            insurance_company_name=insurance_company_name,
            is_removal_signal=is_removal_signal,
        ),
        "docket_number": docket_number,
        "insurance_type_code": insurance_type_code,
        "insurance_type_description": INSURANCE_TYPE_DESCRIPTIONS.get(insurance_type_code or ""),
        "bipd_class_code": bipd_class_code,
        "bipd_maximum_dollar_limit_thousands_usd": bipd_maximum_dollar_limit_thousands_usd,
        "bipd_underlying_dollar_limit_thousands_usd": bipd_underlying_dollar_limit_thousands_usd,
        "policy_number": policy_number,
        "effective_date": effective_date,
        "form_code": form_code,
        "insurance_company_name": insurance_company_name,
        "is_removal_signal": is_removal_signal,
        "removal_signal_reason": "daily_diff_blank_or_zero_row" if is_removal_signal else None,
    }


def upsert_insurance_policies(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_insurance_policy_row,
    )
