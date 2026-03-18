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


def upsert_enigma_location_enrichments(
    *,
    org_id: str,
    company_id: str | None = None,
    enigma_brand_id: str,
    brand_name: str | None = None,
    locations: list[dict[str, Any]],
    enriched_by_operation_id: str = "company.enrich.locations",
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    now = _utc_now_iso()

    rows: list[dict[str, Any]] = []
    for location in locations:
        if not isinstance(location, dict):
            continue

        enigma_location_id = _clean_text(location.get("enigma_location_id"))
        if not enigma_location_id:
            continue

        row: dict[str, Any] = {
            "org_id": org_id,
            "enigma_brand_id": enigma_brand_id,
            "enigma_location_id": enigma_location_id,
            "brand_name": _clean_text(brand_name),
            "location_name": _clean_text(location.get("location_name")),
            "full_address": _clean_text(location.get("full_address")),
            "street": _clean_text(location.get("street")),
            "city": _clean_text(location.get("city")),
            "state": _clean_text(location.get("state")),
            "postal_code": _clean_text(location.get("postal_code")),
            "operating_status": _clean_text(location.get("operating_status")),
            "phone": _clean_text(location.get("phone")),
            "website": _clean_text(location.get("website")),
            "enriched_by_operation_id": enriched_by_operation_id,
            "updated_at": now,
        }

        if company_id:
            row["company_id"] = company_id
        if source_submission_id:
            row["source_submission_id"] = source_submission_id
        if source_pipeline_run_id:
            row["source_pipeline_run_id"] = source_pipeline_run_id

        # Card transaction fields (Plus tier)
        for field in (
            "annual_card_revenue",
            "annual_card_revenue_yoy_growth",
            "annual_avg_daily_customers",
            "annual_transaction_count",
        ):
            val = location.get(field)
            if isinstance(val, (int, float)):
                row[field] = val

        # Competitive rank (Plus tier)
        competitive_rank = location.get("competitive_rank")
        if isinstance(competitive_rank, int):
            row["competitive_rank"] = competitive_rank
        competitive_rank_total = location.get("competitive_rank_total")
        if isinstance(competitive_rank_total, int):
            row["competitive_rank_total"] = competitive_rank_total

        # Reviews (Plus tier)
        review_count = location.get("review_count")
        if isinstance(review_count, int):
            row["review_count"] = review_count
        review_avg_rating = location.get("review_avg_rating")
        if isinstance(review_avg_rating, (int, float)):
            row["review_avg_rating"] = review_avg_rating

        # Contacts (Plus tier, stored as JSONB)
        contacts = location.get("contacts")
        if isinstance(contacts, list) and contacts:
            row["contacts"] = json.dumps(contacts)

        rows.append(row)

    if not rows:
        return []

    result = (
        get_supabase_client()
        .schema("entities")
        .table("enigma_location_enrichments")
        .upsert(rows, on_conflict="org_id,enigma_brand_id,enigma_location_id")
        .execute()
    )
    return result.data or []
