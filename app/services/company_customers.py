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


def upsert_company_customers(
    *,
    org_id: str,
    company_entity_id: str,
    company_domain: str,
    customers: list[dict[str, Any]],
    discovered_by_operation_id: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
    normalized_company_domain = _normalize_company_domain(company_domain)
    now = _utc_now_iso()

    rows: list[dict[str, Any]] = []
    for customer in customers:
        if not isinstance(customer, dict):
            continue

        customer_name = _clean_text(customer.get("customer_name"))
        customer_domain_raw = _clean_text(customer.get("customer_domain"))
        customer_domain = (
            _normalize_company_domain(customer_domain_raw)
            if customer_domain_raw is not None
            else None
        )

        if customer_name is None and customer_domain is None:
            continue

        rows.append(
            {
                "org_id": org_id,
                "company_entity_id": company_entity_id,
                "company_domain": normalized_company_domain,
                "customer_name": customer_name,
                "customer_domain": customer_domain,
                "customer_linkedin_url": _clean_text(customer.get("customer_linkedin_url")),
                "customer_org_id": _clean_text(customer.get("customer_org_id")),
                "discovered_by_operation_id": discovered_by_operation_id,
                "source_submission_id": source_submission_id,
                "source_pipeline_run_id": source_pipeline_run_id,
                "updated_at": now,
            }
        )

    if not rows:
        return []

    result = (
        get_supabase_client()
        .table("company_customers")
        .upsert(rows, on_conflict="org_id,company_domain,customer_domain")
        .execute()
    )
    return result.data or []


def query_company_customers(
    *,
    org_id: str,
    company_domain: str | None = None,
    company_entity_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("company_customers").select("*").eq("org_id", org_id)
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))
    if company_entity_id:
        query = query.eq("company_entity_id", company_entity_id)

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
