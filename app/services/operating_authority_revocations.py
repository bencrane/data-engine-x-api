from __future__ import annotations

from typing import Any

from app.services.fmcsa_daily_diff_common import (
    FmcsaDailyDiffRow,
    FmcsaSourceContext,
    clean_text,
    parse_mmddyyyy_date,
    upsert_fmcsa_daily_diff_rows,
)

TABLE_NAME = "operating_authority_revocations"


def _build_revocation_row(row: FmcsaDailyDiffRow) -> dict[str, Any]:
    fields = row["raw_fields"]
    docket_number = clean_text(fields.get("Docket Number"))
    usdot_number = clean_text(fields.get("USDOT Number"))
    operating_authority_registration_type = clean_text(
        fields.get("Operating Authority Registration Type")
    )
    serve_date = parse_mmddyyyy_date(fields.get("Serve Date"))
    revocation_type = clean_text(fields.get("Revocation Type"))
    effective_date = parse_mmddyyyy_date(fields.get("Effective Date"))

    return {
        "docket_number": docket_number,
        "usdot_number": usdot_number,
        "operating_authority_registration_type": operating_authority_registration_type,
        "serve_date": serve_date,
        "revocation_type": revocation_type,
        "effective_date": effective_date,
    }


def upsert_operating_authority_revocations(
    *,
    source_context: FmcsaSourceContext,
    rows: list[FmcsaDailyDiffRow],
) -> dict[str, Any]:
    return upsert_fmcsa_daily_diff_rows(
        table_name=TABLE_NAME,
        source_context=source_context,
        rows=rows,
        row_builder=_build_revocation_row,
    )
