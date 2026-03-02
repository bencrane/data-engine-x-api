from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_company_domain(company_domain: str) -> str:
    candidate = _normalize_text(company_domain)
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    netloc = parsed.netloc or parsed.path
    normalized = netloc.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized.rstrip("/")


def upsert_salesnav_prospects(
    *,
    org_id: str,
    source_company_domain: str,
    source_company_name: str | None = None,
    source_salesnav_url: str | None = None,
    prospects: list[dict[str, Any]],
    discovered_by_operation_id: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    normalized_source_company_domain = _normalize_company_domain(source_company_domain)
    now = _utc_now_iso()

    rows: list[dict[str, Any]] = []
    for prospect in prospects:
        if not isinstance(prospect, dict):
            continue

        linkedin_url = _clean_text(prospect.get("linkedin_url"))
        full_name = _clean_text(prospect.get("full_name"))
        if linkedin_url is None and full_name is None:
            continue

        rows.append(
            {
                "org_id": org_id,
                "full_name": full_name,
                "first_name": _clean_text(prospect.get("first_name")),
                "last_name": _clean_text(prospect.get("last_name")),
                "linkedin_url": linkedin_url,
                "profile_urn": _clean_text(prospect.get("profile_urn")),
                "geo_region": _clean_text(prospect.get("geo_region")),
                "summary": _clean_text(prospect.get("summary")),
                "current_title": _clean_text(prospect.get("current_title")),
                "current_company_name": _clean_text(prospect.get("current_company_name")),
                "current_company_id": _clean_text(prospect.get("current_company_id")),
                "current_company_industry": _clean_text(prospect.get("current_company_industry")),
                "current_company_location": _clean_text(prospect.get("current_company_location")),
                "position_start_month": prospect.get("position_start_month"),
                "position_start_year": prospect.get("position_start_year"),
                "tenure_at_position_years": prospect.get("tenure_at_position_years"),
                "tenure_at_position_months": prospect.get("tenure_at_position_months"),
                "tenure_at_company_years": prospect.get("tenure_at_company_years"),
                "tenure_at_company_months": prospect.get("tenure_at_company_months"),
                "open_link": prospect.get("open_link"),
                "source_company_domain": normalized_source_company_domain,
                "source_company_name": _clean_text(source_company_name),
                "source_salesnav_url": _clean_text(source_salesnav_url),
                "discovered_by_operation_id": discovered_by_operation_id,
                "source_submission_id": source_submission_id,
                "source_pipeline_run_id": source_pipeline_run_id,
                "raw_person": prospect,
                "updated_at": now,
            }
        )

    if not rows:
        return []

    result = (
        get_supabase_client()
        .table("salesnav_prospects")
        .upsert(rows, on_conflict="org_id,source_company_domain,linkedin_url")
        .execute()
    )
    return result.data or []


def query_salesnav_prospects(
    *,
    org_id: str,
    source_company_domain: str | None = None,
    current_title: str | None = None,
    linkedin_url: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("salesnav_prospects").select("*").eq("org_id", org_id)
    if source_company_domain:
        query = query.eq("source_company_domain", _normalize_company_domain(source_company_domain))
    if current_title:
        query = query.ilike("current_title", f"%{current_title.strip()}%")
    if linkedin_url:
        query = query.eq("linkedin_url", linkedin_url.strip())

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
