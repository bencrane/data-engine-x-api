from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_bool,
    parse_fmcsa_date,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "motor_carrier_census_records"


def _build_motor_carrier_census_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "dot_number": clean_text(fields.get("DOT_NUMBER")),
        "legal_name": clean_text(fields.get("LEGAL_NAME")),
        "dba_name": clean_text(fields.get("DBA_NAME")),
        "carrier_operation_code": clean_text(fields.get("CARRIER_OPERATION")),
        "hazmat_flag": parse_bool(fields.get("HM_FLAG")),
        "passenger_carrier_flag": parse_bool(fields.get("PC_FLAG")),
        "physical_street": clean_text(fields.get("PHY_STREET")),
        "physical_city": clean_text(fields.get("PHY_CITY")),
        "physical_state": clean_text(fields.get("PHY_STATE")),
        "physical_zip": clean_text(fields.get("PHY_ZIP")),
        "physical_country": clean_text(fields.get("PHY_COUNTRY")),
        "mailing_street": clean_text(fields.get("MAILING_STREET")),
        "mailing_city": clean_text(fields.get("MAILING_CITY")),
        "mailing_state": clean_text(fields.get("MAILING_STATE")),
        "mailing_zip": clean_text(fields.get("MAILING_ZIP")),
        "mailing_country": clean_text(fields.get("MAILING_COUNTRY")),
        "telephone": clean_text(fields.get("TELEPHONE")),
        "fax": clean_text(fields.get("FAX")),
        "email_address": clean_text(fields.get("EMAIL_ADDRESS")),
        "mcs150_date": parse_fmcsa_date(fields.get("MCS150_DATE")),
        "mcs150_mileage": parse_int(fields.get("MCS150_MILEAGE")),
        "mcs150_mileage_year": parse_int(fields.get("MCS150_MILEAGE_YEAR")),
        "add_date": parse_fmcsa_date(fields.get("ADD_DATE")),
        "oic_state": clean_text(fields.get("OIC_STATE")),
        "power_unit_count": parse_int(fields.get("NBR_POWER_UNIT")),
        "driver_total": parse_int(fields.get("DRIVER_TOTAL")),
        "recent_mileage": parse_int(fields.get("RECENT_MILEAGE")),
        "recent_mileage_year": parse_int(fields.get("RECENT_MILEAGE_YEAR")),
        "vmt_source_id": parse_int(fields.get("VMT_SOURCE_ID")),
        "private_only": parse_bool(fields.get("PRIVATE_ONLY")),
        "authorized_for_hire": parse_bool(fields.get("AUTHORIZED_FOR_HIRE")),
        "exempt_for_hire": parse_bool(fields.get("EXEMPT_FOR_HIRE")),
        "private_property": parse_bool(fields.get("PRIVATE_PROPERTY")),
        "private_passenger_business": parse_bool(fields.get("PRIVATE_PASSENGER_BUSINESS")),
        "private_passenger_nonbusiness": parse_bool(fields.get("PRIVATE_PASSENGER_NONBUSINESS")),
        "migrant": parse_bool(fields.get("MIGRANT")),
        "us_mail": parse_bool(fields.get("US_MAIL")),
        "federal_government": parse_bool(fields.get("FEDERAL_GOVERNMENT")),
        "state_government": parse_bool(fields.get("STATE_GOVERNMENT")),
        "local_government": parse_bool(fields.get("LOCAL_GOVERNMENT")),
        "indian_tribe": parse_bool(fields.get("INDIAN_TRIBE")),
        "other_operation_description": clean_text(fields.get("OP_OTHER")),
    }


def upsert_motor_carrier_census_records(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_motor_carrier_census_row,
    )
