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


def upsert_gemini_icp_job_titles(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    company_description: str | None = None,
    inferred_product: str | None = None,
    buyer_persona: str | None = None,
    titles: list[dict[str, Any]] | None = None,
    champion_titles: list[str] | None = None,
    evaluator_titles: list[str] | None = None,
    decision_maker_titles: list[str] | None = None,
    raw_response: dict[str, Any],
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    row: dict[str, Any] = {
        "org_id": org_id,
        "company_domain": _normalize_company_domain(company_domain),
        "raw_response": raw_response,
        "source_submission_id": source_submission_id,
        "source_pipeline_run_id": source_pipeline_run_id,
        "updated_at": now,
    }
    if company_name is not None:
        row["company_name"] = company_name
    if company_description is not None:
        row["company_description"] = company_description
    if inferred_product is not None:
        row["inferred_product"] = inferred_product
    if buyer_persona is not None:
        row["buyer_persona"] = buyer_persona
    if titles is not None:
        row["titles"] = titles
    if champion_titles is not None:
        row["champion_titles"] = champion_titles
    if evaluator_titles is not None:
        row["evaluator_titles"] = evaluator_titles
    if decision_maker_titles is not None:
        row["decision_maker_titles"] = decision_maker_titles

    result = (
        get_supabase_client()
        .table("gemini_icp_job_titles")
        .upsert(row, on_conflict="org_id,company_domain")
        .execute()
    )
    return result.data[0]


def query_gemini_icp_job_titles(
    *,
    org_id: str,
    company_domain: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("gemini_icp_job_titles").select("*").eq("org_id", org_id)
    if company_domain:
        query = query.eq("company_domain", _normalize_company_domain(company_domain))

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
