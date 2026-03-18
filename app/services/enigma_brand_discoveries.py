from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def upsert_enigma_brand_discoveries(
    *,
    org_id: str,
    company_id: str | None = None,
    discovery_prompt: str,
    geography_state: str | None = None,
    geography_city: str | None = None,
    brands: list[dict[str, Any]],
    discovered_by_operation_id: str = "company.search.enigma.brands",
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    now = _utc_now_iso()

    rows: list[dict[str, Any]] = []
    for brand in brands:
        if not isinstance(brand, dict):
            continue

        enigma_brand_id = _clean_text(brand.get("enigma_brand_id"))
        if not enigma_brand_id:
            continue

        industries_raw = brand.get("industries")
        industries = json.dumps(industries_raw) if isinstance(industries_raw, list) else None

        row: dict[str, Any] = {
            "org_id": org_id,
            "discovery_prompt": discovery_prompt,
            "enigma_brand_id": enigma_brand_id,
            "brand_name": _clean_text(brand.get("brand_name")),
            "brand_website": _clean_text(brand.get("brand_website")) or _clean_text(brand.get("website")),
            "location_count": brand.get("location_count") if isinstance(brand.get("location_count"), int) else None,
            "industries": industries,
            "discovered_by_operation_id": discovered_by_operation_id,
            "updated_at": now,
        }

        if company_id:
            row["company_id"] = company_id
        if geography_state:
            row["geography_state"] = geography_state
        if geography_city:
            row["geography_city"] = geography_city
        if source_submission_id:
            row["source_submission_id"] = source_submission_id
        if source_pipeline_run_id:
            row["source_pipeline_run_id"] = source_pipeline_run_id

        # Card revenue fields (populated if enrichment ran)
        for field in (
            "annual_card_revenue",
            "annual_card_revenue_yoy_growth",
            "annual_avg_daily_customers",
            "annual_transaction_count",
        ):
            val = brand.get(field)
            if isinstance(val, (int, float)):
                row[field] = val

        monthly_revenue = brand.get("monthly_revenue")
        if isinstance(monthly_revenue, list):
            row["monthly_revenue"] = json.dumps(monthly_revenue)

        rows.append(row)

    if not rows:
        return []

    result = (
        get_supabase_client()
        .schema("entities")
        .table("enigma_brand_discoveries")
        .upsert(rows, on_conflict="org_id,enigma_brand_id,discovery_prompt")
        .execute()
    )
    return result.data or []
