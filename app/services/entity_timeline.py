from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.database import get_supabase_client

logger = logging.getLogger(__name__)

_ALLOWED_STATUSES = {"found", "not_found", "failed", "skipped"}


def _to_uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _normalize_fields_updated(fields_updated: list[str] | None) -> list[str] | None:
    if not fields_updated:
        return None
    deduped: list[str] = []
    for field in fields_updated:
        field_name = str(field).strip()
        if field_name and field_name not in deduped:
            deduped.append(field_name)
    return deduped or None


def record_entity_event(
    *,
    org_id: str,
    company_id: str | None,
    entity_type: str,
    entity_id: str,
    operation_id: str,
    status: str,
    pipeline_run_id: str | None = None,
    submission_id: str | None = None,
    provider: str | None = None,
    fields_updated: list[str] | None = None,
    summary: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Best-effort timeline write. Never raises to callers.
    """
    if status not in _ALLOWED_STATUSES:
        logger.warning("Skipping timeline write due to invalid status", extra={"status": status})
        return None

    org_uuid = _to_uuid_or_none(org_id)
    entity_uuid = _to_uuid_or_none(entity_id)
    if not org_uuid or not entity_uuid:
        logger.warning(
            "Skipping timeline write due to invalid org/entity ids",
            extra={"org_id": org_id, "entity_id": entity_id},
        )
        return None

    if entity_type not in {"company", "person", "job"}:
        logger.warning("Skipping timeline write due to invalid entity_type", extra={"entity_type": entity_type})
        return None

    payload = {
        "org_id": org_uuid,
        "company_id": _to_uuid_or_none(company_id),
        "entity_type": entity_type,
        "entity_id": entity_uuid,
        "operation_id": operation_id,
        "pipeline_run_id": _to_uuid_or_none(pipeline_run_id),
        "submission_id": _to_uuid_or_none(submission_id),
        "provider": provider.strip() if isinstance(provider, str) and provider.strip() else None,
        "status": status,
        "fields_updated": _normalize_fields_updated(fields_updated),
        "summary": summary.strip() if isinstance(summary, str) and summary.strip() else None,
        "metadata": metadata or None,
    }

    try:
        result = get_supabase_client().table("entity_timeline").insert(payload).execute()
        return result.data[0] if result.data else None
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "Failed to write entity timeline event",
            extra={
                "org_id": org_uuid,
                "entity_type": entity_type,
                "entity_id": entity_uuid,
                "operation_id": operation_id,
                "pipeline_run_id": payload["pipeline_run_id"],
                "error": str(exc),
            },
        )
        return None
