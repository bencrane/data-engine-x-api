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


def upsert_icp_job_titles(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    company_description: str | None = None,
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
    if company_description is not None:
        row["company_description"] = company_description

    result = (
        get_supabase_client()
        .table("icp_job_titles")
        .upsert(row, on_conflict="org_id,company_domain")
        .execute()
    )
    return result.data[0]


def query_icp_job_titles(
    *,
    org_id: str,
    company_domain: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("icp_job_titles").select("*").eq("org_id", org_id)
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []


def update_icp_extracted_titles(
    *,
    org_id: str,
    company_domain: str,
    extracted_titles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_domain = _normalize_company_domain(company_domain)
    result = (
        get_supabase_client()
        .table("icp_job_titles")
        .update(
            {
                "extracted_titles": extracted_titles,
                "updated_at": _utc_now_iso(),
            }
        )
        .eq("org_id", org_id)
        .eq("company_domain", normalized_domain)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def upsert_icp_title_details_batch(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None,
    titles: list[dict[str, Any]],
    source_icp_job_titles_id: str | None = None,
) -> list[dict[str, Any]]:
    normalized_domain = _normalize_company_domain(company_domain)
    rows: list[dict[str, Any]] = []
    for item in titles:
        if not isinstance(item, dict):
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            continue
        rows.append(
            {
                "org_id": org_id,
                "company_domain": normalized_domain,
                "company_name": company_name,
                "title": title.strip(),
                "buyer_role": item.get("buyer_role"),
                "reasoning": item.get("reasoning"),
                "source_icp_job_titles_id": source_icp_job_titles_id,
                "updated_at": _utc_now_iso(),
            }
        )

    if not rows:
        return []

    result = (
        get_supabase_client()
        .table("extracted_icp_job_title_details")
        .upsert(rows, on_conflict="org_id,company_domain,title_normalized")
        .execute()
    )
    return result.data or []


def query_icp_title_details(
    *,
    org_id: str,
    company_domain: str | None = None,
    buyer_role: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = (
        get_supabase_client()
        .table("extracted_icp_job_title_details")
        .select("*")
        .eq("org_id", org_id)
    )
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))
    if isinstance(buyer_role, str) and buyer_role.strip():
        query = query.eq("buyer_role", buyer_role.strip())

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []


