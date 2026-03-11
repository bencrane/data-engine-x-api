from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_int,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "carrier_registrations"


def _build_carrier_registration_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]

    return {
        "docket_number": clean_text(fields.get("Docket Number")),
        "usdot_number": clean_text(fields.get("USDOT Number")),
        "mx_type": clean_text(fields.get("MX Type")),
        "rfc_number": clean_text(fields.get("RFC Number")),
        "common_authority_status": clean_text(fields.get("Common Authority")),
        "contract_authority_status": clean_text(fields.get("Contract Authority")),
        "broker_authority_status": clean_text(fields.get("Broker Authority")),
        "pending_common_authority": clean_text(fields.get("Pending Common Authority")),
        "pending_contract_authority": clean_text(fields.get("Pending Contract Authority")),
        "pending_broker_authority": clean_text(fields.get("Pending Broker Authority")),
        "common_authority_revocation": clean_text(fields.get("Common Authority Revocation")),
        "contract_authority_revocation": clean_text(fields.get("Contract Authority Revocation")),
        "broker_authority_revocation": clean_text(fields.get("Broker Authority Revocation")),
        "property_authority": clean_text(fields.get("Property")),
        "passenger_authority": clean_text(fields.get("Passenger")),
        "household_goods_authority": clean_text(fields.get("Household Goods")),
        "private_check": clean_text(fields.get("Private Check")),
        "enterprise_check": clean_text(fields.get("Enterprise Check")),
        "bipd_required_thousands_usd": parse_int(fields.get("BIPD Required")),
        "cargo_required": clean_text(fields.get("Cargo Required")),
        "bond_surety_required": clean_text(fields.get("Bond/Surety Required")),
        "bipd_on_file_thousands_usd": parse_int(fields.get("BIPD on File")),
        "cargo_on_file": clean_text(fields.get("Cargo on File")),
        "bond_surety_on_file": clean_text(fields.get("Bond/Surety on File")),
        "address_status": clean_text(fields.get("Address Status")),
        "dba_name": clean_text(fields.get("DBA Name")),
        "legal_name": clean_text(fields.get("Legal Name")),
        "business_address_street": clean_text(fields.get("Business Address - PO Box/Street")),
        "business_address_colonia": clean_text(fields.get("Business Address - Colonia")),
        "business_address_city": clean_text(fields.get("Business Address - City")),
        "business_address_state_code": clean_text(fields.get("Business Address - State Code")),
        "business_address_country_code": clean_text(fields.get("Business Address - Country Code")),
        "business_address_zip_code": clean_text(fields.get("Business Address - Zip Code")),
        "business_address_telephone_number": clean_text(
            fields.get("Business Address - Telephone Number")
        ),
        "business_address_fax_number": clean_text(fields.get("Business Address - Fax Number")),
        "mailing_address_street": clean_text(fields.get("Mailing Address - PO Box/Street")),
        "mailing_address_colonia": clean_text(fields.get("Mailing Address - Colonia")),
        "mailing_address_city": clean_text(fields.get("Mailing Address - City")),
        "mailing_address_state_code": clean_text(fields.get("Mailing Address - State Code")),
        "mailing_address_country_code": clean_text(fields.get("Mailing Address - Country Code")),
        "mailing_address_zip_code": clean_text(fields.get("Mailing Address - Zip Code")),
        "mailing_address_telephone_number": clean_text(
            fields.get("Mailing Address - Telephone Number")
        ),
        "mailing_address_fax_number": clean_text(fields.get("Mailing Address - Fax Number")),
    }


def upsert_carrier_registrations(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_carrier_registration_row,
    )
