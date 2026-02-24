from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(value: str) -> str:
    return value.strip().lower()


def _normalize_domain(identifier: str) -> str:
    candidate = _normalize_text(identifier)
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    netloc = parsed.netloc or parsed.path
    normalized = netloc.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized.rstrip("/")


def _normalize_linkedin_url(identifier: str) -> str:
    normalized = _normalize_text(identifier).rstrip("/")
    if normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    elif normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized


def _normalize_identifier(identifier: str) -> str:
    normalized = _normalize_text(identifier)
    if "linkedin.com/" in normalized:
        return _normalize_linkedin_url(normalized)
    if "." in normalized:
        return _normalize_domain(normalized)
    return normalized


def record_entity_relationship(
    *,
    org_id: str,
    source_entity_type: str,
    source_identifier: str,
    relationship: str,
    target_entity_type: str,
    target_identifier: str,
    source_entity_id: str | None = None,
    target_entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
    source_operation_id: str | None = None,
) -> dict[str, Any]:
    now = _utc_now_iso()
    normalized_source_identifier = _normalize_identifier(source_identifier)
    normalized_target_identifier = _normalize_identifier(target_identifier)

    row: dict[str, Any] = {
        "org_id": org_id,
        "source_entity_type": source_entity_type,
        "source_entity_id": source_entity_id,
        "source_identifier": normalized_source_identifier,
        "relationship": relationship,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "target_identifier": normalized_target_identifier,
        "source_submission_id": source_submission_id,
        "source_pipeline_run_id": source_pipeline_run_id,
        "source_operation_id": source_operation_id,
        "valid_as_of": now,
        "invalidated_at": None,
        "updated_at": now,
    }
    if metadata is not None:
        row["metadata"] = metadata

    result = (
        get_supabase_client()
        .table("entity_relationships")
        .upsert(
            row,
            on_conflict="org_id,source_identifier,relationship,target_identifier",
        )
        .execute()
    )
    return result.data[0]


def record_entity_relationships_batch(
    *,
    org_id: str,
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for relationship_input in relationships:
        try:
            row = record_entity_relationship(org_id=org_id, **relationship_input)
            rows.append(row)
        except Exception:  # noqa: BLE001
            logger.exception(
                "Failed to record entity relationship in batch",
                extra={"org_id": org_id, "relationship_input": relationship_input},
            )
    return rows


def invalidate_entity_relationship(
    *,
    org_id: str,
    source_identifier: str,
    relationship: str,
    target_identifier: str,
) -> dict[str, Any] | None:
    now = _utc_now_iso()
    result = (
        get_supabase_client()
        .table("entity_relationships")
        .update(
            {
                "invalidated_at": now,
                "updated_at": now,
            }
        )
        .eq("org_id", org_id)
        .eq("source_identifier", _normalize_identifier(source_identifier))
        .eq("relationship", relationship)
        .eq("target_identifier", _normalize_identifier(target_identifier))
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def query_entity_relationships(
    *,
    org_id: str,
    source_identifier: str | None = None,
    target_identifier: str | None = None,
    relationship: str | None = None,
    source_entity_type: str | None = None,
    target_entity_type: str | None = None,
    include_invalidated: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)

    query = get_supabase_client().table("entity_relationships").select("*").eq("org_id", org_id)
    if source_identifier:
        query = query.eq("source_identifier", _normalize_identifier(source_identifier))
    if target_identifier:
        query = query.eq("target_identifier", _normalize_identifier(target_identifier))
    if relationship:
        query = query.eq("relationship", relationship)
    if source_entity_type:
        query = query.eq("source_entity_type", source_entity_type)
    if target_entity_type:
        query = query.eq("target_entity_type", target_entity_type)
    if not include_invalidated:
        query = query.is_("invalidated_at", "null")

    result = (
        query.order("created_at", desc=True)
        .range(safe_offset, safe_offset + safe_limit - 1)
        .execute()
    )
    return result.data or []
