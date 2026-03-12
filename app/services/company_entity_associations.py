from __future__ import annotations

from typing import Any

from app.database import get_supabase_client


def record_company_entity_association(
    *,
    org_id: str,
    company_id: str,
    entity_type: str,
    entity_id: str,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
    source_step_result_id: str | None = None,
    source_operation_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if entity_type not in {"company", "person", "job"}:
        raise ValueError("entity_type must be one of: company, person, job")

    payload = {
        "org_id": org_id,
        "company_id": company_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "source_submission_id": source_submission_id,
        "source_pipeline_run_id": source_pipeline_run_id,
        "source_step_result_id": source_step_result_id,
        "source_operation_id": source_operation_id,
        "metadata": metadata or {},
    }
    client = get_supabase_client()
    result = (
        client.table("company_entity_associations")
        .upsert(payload, on_conflict="org_id,company_id,entity_type,entity_id")
        .execute()
    )
    return result.data[0]


def list_associated_entity_ids(
    *,
    org_id: str,
    company_id: str,
    entity_type: str,
    limit: int = 5000,
) -> list[str]:
    if entity_type not in {"company", "person", "job"}:
        raise ValueError("entity_type must be one of: company, person, job")

    client = get_supabase_client()
    result = (
        client.table("company_entity_associations")
        .select("entity_id")
        .eq("org_id", org_id)
        .eq("company_id", company_id)
        .eq("entity_type", entity_type)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return [row["entity_id"] for row in result.data]
