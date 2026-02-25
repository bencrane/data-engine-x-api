from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_linkedin_url(person_linkedin_url: str) -> str:
    return person_linkedin_url.strip().lower().rstrip("/")


def upsert_person_intel_briefing(
    *,
    org_id: str,
    person_full_name: str,
    person_linkedin_url: str | None = None,
    person_current_company_name: str | None = None,
    person_current_company_domain: str | None = None,
    person_current_job_title: str | None = None,
    client_company_name: str | None = None,
    client_company_description: str | None = None,
    customer_company_name: str | None = None,
    customer_company_domain: str | None = None,
    raw_parallel_output: dict[str, Any],
    parallel_run_id: str | None = None,
    processor: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    row: dict[str, Any] = {
        "org_id": org_id,
        "person_full_name": person_full_name,
        "raw_parallel_output": raw_parallel_output,
        "parallel_run_id": parallel_run_id,
        "processor": processor,
        "source_submission_id": source_submission_id,
        "source_pipeline_run_id": source_pipeline_run_id,
        "updated_at": now,
    }
    if person_linkedin_url is not None:
        row["person_linkedin_url"] = _normalize_linkedin_url(person_linkedin_url)
    if person_current_company_name is not None:
        row["person_current_company_name"] = person_current_company_name
    if person_current_company_domain is not None:
        row["person_current_company_domain"] = person_current_company_domain
    if person_current_job_title is not None:
        row["person_current_job_title"] = person_current_job_title
    if client_company_name is not None:
        row["client_company_name"] = client_company_name
    if client_company_description is not None:
        row["client_company_description"] = client_company_description
    if customer_company_name is not None:
        row["customer_company_name"] = customer_company_name
    if customer_company_domain is not None:
        row["customer_company_domain"] = customer_company_domain

    result = (
        get_supabase_client()
        .table("person_intel_briefings")
        .upsert(
            row,
            on_conflict="org_id,person_full_name,person_current_company_name,client_company_name",
        )
        .execute()
    )
    return result.data[0]


def query_person_intel_briefings(
    *,
    org_id: str,
    person_linkedin_url: str | None = None,
    person_current_company_name: str | None = None,
    client_company_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("person_intel_briefings").select("*").eq("org_id", org_id)
    if person_linkedin_url:
        query = query.eq("person_linkedin_url", _normalize_linkedin_url(person_linkedin_url))
    if person_current_company_name:
        query = query.eq("person_current_company_name", person_current_company_name)
    if client_company_name:
        query = query.eq("client_company_name", client_company_name)

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
