from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return value.strip().lower()


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


def upsert_company_intel_briefing(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    client_company_name: str | None = None,
    client_company_domain: str | None = None,
    client_company_description: str | None = None,
    raw_parallel_output: dict[str, Any],
    parallel_run_id: str | None = None,
    processor: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    row: dict[str, Any] = {
        "org_id": org_id,
        "company_domain": _normalize_company_domain(company_domain),
        "raw_parallel_output": raw_parallel_output,
        "parallel_run_id": parallel_run_id,
        "processor": processor,
        "source_submission_id": source_submission_id,
        "source_pipeline_run_id": source_pipeline_run_id,
        "updated_at": now,
    }
    if company_name is not None:
        row["company_name"] = company_name
    if client_company_name is not None:
        row["client_company_name"] = client_company_name
    if client_company_domain is not None:
        row["client_company_domain"] = client_company_domain
    if client_company_description is not None:
        row["client_company_description"] = client_company_description

    result = (
        get_supabase_client()
        .table("company_intel_briefings")
        .upsert(row, on_conflict="org_id,company_domain,client_company_name")
        .execute()
    )
    return result.data[0]


def query_company_intel_briefings(
    *,
    org_id: str,
    company_domain: str | None = None,
    client_company_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("company_intel_briefings").select("*").eq("org_id", org_id)
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))
    if client_company_name:
        query = query.eq("client_company_name", client_company_name)

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
