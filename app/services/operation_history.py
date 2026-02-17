from __future__ import annotations

from uuid import UUID

from app.auth.models import AuthContext
from app.database import get_supabase_client


def _to_uuid_or_none(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def persist_operation_execution(
    *,
    auth: AuthContext,
    entity_type: str,
    operation_id: str,
    input_payload: dict,
    result: dict,
):
    client = get_supabase_client()

    run_id = _to_uuid_or_none(result.get("run_id"))
    if not run_id:
        return

    output_payload = result.get("output")
    missing_inputs = result.get("missing_inputs") or []
    status = result.get("status") or "failed"

    run_row = {
        "run_id": run_id,
        "org_id": auth.org_id,
        "company_id": auth.company_id,
        "user_id": auth.user_id,
        "role": auth.role,
        "auth_method": auth.auth_method,
        "operation_id": operation_id,
        "entity_type": entity_type,
        "status": status,
        "missing_inputs": missing_inputs,
        "input_payload": input_payload,
        "output_payload": output_payload,
    }
    client.table("operation_runs").insert(run_row).execute()

    attempts = result.get("provider_attempts") or []
    if not attempts:
        return

    attempt_rows = []
    for attempt in attempts:
        attempt_rows.append(
            {
                "run_id": run_id,
                "provider": attempt.get("provider") or "unknown",
                "action": attempt.get("action") or "unknown",
                "status": attempt.get("status") or "failed",
                "skip_reason": attempt.get("skip_reason"),
                "http_status": attempt.get("http_status"),
                "provider_status": attempt.get("provider_status"),
                "duration_ms": attempt.get("duration_ms"),
                "raw_response": attempt.get("raw_response"),
            }
        )
    client.table("operation_attempts").insert(attempt_rows).execute()

