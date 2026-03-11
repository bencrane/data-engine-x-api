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

TABLE_NAME = "insurance_policy_history_events"


def _build_insurance_policy_history_event_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]
    docket_number = clean_text(fields.get("Docket Number"))
    usdot_number = clean_text(fields.get("USDOT Number"))
    form_code = clean_text(fields.get("Form Code"))
    cancellation_method = clean_text(fields.get("Cancellation Method"))
    cancellation_form_code = clean_text(fields.get("Cancel/Replace/Name Change/Transfer Form"))
    insurance_type_indicator = clean_text(fields.get("Insurance Type Indicator"))
    insurance_type_description = clean_text(fields.get("Insurance Type Description"))
    policy_number = clean_text(fields.get("Policy Number"))
    minimum_coverage_amount_thousands_usd = parse_int(fields.get("Minimum Coverage Amount"))
    insurance_class_code = clean_text(fields.get("Insurance Class Code"))
    effective_date = parse_mmddyyyy_date(fields.get("Effective Date"))
    bipd_underlying_limit_amount_thousands_usd = parse_int(
        fields.get("BI&PD Underlying Limit Amount")
    )
    bipd_max_coverage_amount_thousands_usd = parse_int(fields.get("BI&PD Max Coverage Amount"))
    cancel_effective_date = parse_mmddyyyy_date(fields.get("Cancel Effective Date"))
    specific_cancellation_method = clean_text(fields.get("Specific Cancellation Method"))
    insurance_company_branch = clean_text(fields.get("Insurance Company Branch"))
    insurance_company_name = clean_text(fields.get("Insurance Company Name"))

    return {
        "docket_number": docket_number,
        "usdot_number": usdot_number,
        "form_code": form_code,
        "cancellation_method": cancellation_method,
        "cancellation_form_code": cancellation_form_code,
        "insurance_type_indicator": insurance_type_indicator,
        "insurance_type_description": insurance_type_description,
        "policy_number": policy_number,
        "minimum_coverage_amount_thousands_usd": minimum_coverage_amount_thousands_usd,
        "insurance_class_code": insurance_class_code,
        "effective_date": effective_date,
        "bipd_underlying_limit_amount_thousands_usd": bipd_underlying_limit_amount_thousands_usd,
        "bipd_max_coverage_amount_thousands_usd": bipd_max_coverage_amount_thousands_usd,
        "cancel_effective_date": cancel_effective_date,
        "specific_cancellation_method": specific_cancellation_method,
        "insurance_company_branch": insurance_company_branch,
        "insurance_company_name": insurance_company_name,
    }


def upsert_insurance_policy_history_events(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_insurance_policy_history_event_row,
    )
