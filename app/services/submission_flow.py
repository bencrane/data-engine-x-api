# app/services/submission_flow.py — Shared submission/pipeline creation flow

from datetime import datetime, timezone
import hashlib
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.database import get_supabase_client
from app.services.trigger import trigger_pipeline_run


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except ValueError:
        return False


def _normalize_identity_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text.lower()


def _normalize_domain_identity(value: Any) -> str | None:
    text = _normalize_identity_value(value)
    if not text:
        return None
    candidate = text
    if "://" in candidate:
        candidate = urlparse(candidate).netloc or candidate
    candidate = candidate.split("/")[0].strip()
    if candidate.startswith("www."):
        candidate = candidate[4:]
    return candidate or None


def _extract_fan_out_identity_tokens(entity: dict[str, Any]) -> list[str]:
    entity_type = str(entity.get("entity_type") or "person").strip().lower()
    tokens: list[str] = []

    if entity_type == "company":
        company_domain = _normalize_domain_identity(
            entity.get("company_domain") or entity.get("canonical_domain") or entity.get("domain")
        )
        company_linkedin_url = _normalize_identity_value(
            entity.get("company_linkedin_url") or entity.get("linkedin_url")
        )
        if company_domain:
            tokens.append(f"company:domain:{company_domain}")
        if company_linkedin_url:
            tokens.append(f"company:linkedin:{company_linkedin_url.rstrip('/')}")
        return tokens

    linkedin_url = _normalize_identity_value(entity.get("linkedin_url"))
    work_email = _normalize_identity_value(entity.get("work_email") or entity.get("email"))
    if linkedin_url:
        tokens.append(f"person:linkedin:{linkedin_url.rstrip('/')}")
    if work_email:
        tokens.append(f"person:email:{work_email}")
    return tokens


def _select_fan_out_duplicate_identifier(tokens: list[str]) -> str:
    for prefix in ("person:linkedin:", "person:email:", "company:domain:", "company:linkedin:"):
        for token in tokens:
            if token.startswith(prefix):
                return token
    return tokens[0]


def _blueprint_version_from_snapshot(snapshot: dict[str, Any]) -> int:
    digest = hashlib.sha256(
        str(snapshot).encode("utf-8")
    ).hexdigest()
    # Keep deterministic version within Postgres INT range.
    value = int(digest[:8], 16) % 2_147_483_647
    return value if value > 0 else 1


def _ensure_company_in_org(org_id: str, company_id: str) -> bool:
    client = get_supabase_client()
    result = (
        client.table("companies")
        .select("id")
        .eq("id", company_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _load_blueprint_snapshot(org_id: str, blueprint_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    blueprint_result = (
        client.table("blueprints")
        .select("*")
        .eq("id", blueprint_id)
        .eq("org_id", org_id)
        .eq("is_active", True)
        .limit(1)
        .execute()
    )
    if not blueprint_result.data:
        return None
    blueprint = blueprint_result.data[0]

    steps_result = (
        client.table("blueprint_steps")
        .select("*")
        .eq("blueprint_id", blueprint_id)
        .eq("is_enabled", True)
        .order("position")
        .execute()
    )

    return {
        "blueprint": blueprint,
        "steps": steps_result.data,
    }


def _create_pipeline_run_row(
    *,
    org_id: str,
    company_id: str,
    submission_id: str,
    blueprint_id: str,
    blueprint_snapshot: dict[str, Any],
    attempt: int,
    parent_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
    client = get_supabase_client()
    blueprint_version = _blueprint_version_from_snapshot(blueprint_snapshot)
    run_result = client.table("pipeline_runs").insert(
        {
            "org_id": org_id,
            "company_id": company_id,
            "submission_id": submission_id,
            "blueprint_id": blueprint_id,
            "blueprint_snapshot": blueprint_snapshot,
            "blueprint_version": blueprint_version,
            "status": "queued",
            "attempt": attempt,
            "parent_pipeline_run_id": parent_pipeline_run_id,
        }
    ).execute()
    return run_result.data[0]


def _create_step_result_rows(
    *,
    org_id: str,
    company_id: str,
    submission_id: str,
    pipeline_run_id: str,
    blueprint_steps: list[dict[str, Any]],
    start_from_position: int | None = None,
):
    if not blueprint_steps:
        return
    client = get_supabase_client()
    relevant_steps = (
        [step for step in blueprint_steps if step.get("position", 0) >= start_from_position]
        if start_from_position is not None
        else blueprint_steps
    )
    if not relevant_steps:
        return
    rows = [
        {
            "org_id": org_id,
            "company_id": company_id,
            "submission_id": submission_id,
            "pipeline_run_id": pipeline_run_id,
            "step_id": step.get("step_id"),
            "blueprint_step_id": step["id"],
            "step_position": step["position"],
            "status": "queued",
        }
        for step in relevant_steps
    ]
    client.table("step_results").insert(rows).execute()


async def create_submission_and_trigger_pipeline(
    *,
    org_id: str,
    company_id: str,
    blueprint_id: str,
    input_payload: dict[str, Any] | list[Any],
    source: str | None,
    metadata: dict[str, Any] | None,
    submitted_by_user_id: str | None,
) -> dict[str, Any]:
    """
    Create submission + pipeline run + queued step rows, then trigger Trigger.dev.
    """
    if not _is_uuid(org_id) or not _is_uuid(company_id) or not _is_uuid(blueprint_id):
        raise ValueError("org_id, company_id, and blueprint_id must be valid UUIDs")

    if not _ensure_company_in_org(org_id, company_id):
        raise ValueError("company_id does not belong to org_id")

    snapshot = _load_blueprint_snapshot(org_id, blueprint_id)
    if snapshot is None:
        raise ValueError("blueprint not found or inactive for org")

    client = get_supabase_client()
    submission_result = client.table("submissions").insert(
        {
            "org_id": org_id,
            "company_id": company_id,
            "blueprint_id": blueprint_id,
            "submitted_by_user_id": submitted_by_user_id,
            "input_payload": input_payload,
            "source": source,
            "metadata": metadata or {},
            "status": "received",
        }
    ).execute()
    submission = submission_result.data[0]

    run = _create_pipeline_run_row(
        org_id=org_id,
        company_id=company_id,
        submission_id=submission["id"],
        blueprint_id=blueprint_id,
        blueprint_snapshot=snapshot,
        attempt=1,
    )

    _create_step_result_rows(
        org_id=org_id,
        company_id=company_id,
        submission_id=submission["id"],
        pipeline_run_id=run["id"],
        blueprint_steps=snapshot["steps"],
    )

    client.table("submissions").update({"status": "queued"}).eq("id", submission["id"]).execute()

    try:
        trigger_run_id = await trigger_pipeline_run(
            pipeline_run_id=run["id"],
            org_id=org_id,
            company_id=company_id,
        )
        run_update = (
            client.table("pipeline_runs")
            .update({"trigger_run_id": trigger_run_id})
            .eq("id", run["id"])
            .execute()
        )
        run = run_update.data[0]
    except Exception as exc:  # noqa: BLE001
        failed = (
            client.table("pipeline_runs")
            .update(
                {
                    "status": "failed",
                    "error_message": "Failed to trigger Trigger.dev run",
                    "error_details": {"error": str(exc), "at": _iso_now()},
                }
            )
            .eq("id", run["id"])
            .execute()
        )
        run = failed.data[0]

    return {
        "submission_id": submission["id"],
        "pipeline_run_id": run["id"],
        "pipeline_run_status": run["status"],
        "trigger_run_id": run.get("trigger_run_id"),
    }


async def create_batch_submission_and_trigger_pipeline_runs(
    *,
    org_id: str,
    company_id: str,
    blueprint_id: str,
    entities: list[dict[str, Any]],
    source: str | None,
    metadata: dict[str, Any] | None,
    submitted_by_user_id: str | None,
) -> dict[str, Any]:
    if not _is_uuid(org_id) or not _is_uuid(company_id) or not _is_uuid(blueprint_id):
        raise ValueError("org_id, company_id, and blueprint_id must be valid UUIDs")
    if not entities:
        raise ValueError("entities must contain at least one entity")
    if not _ensure_company_in_org(org_id, company_id):
        raise ValueError("company_id does not belong to org_id")

    snapshot = _load_blueprint_snapshot(org_id, blueprint_id)
    if snapshot is None:
        raise ValueError("blueprint not found or inactive for org")

    client = get_supabase_client()
    submission_result = client.table("submissions").insert(
        {
            "org_id": org_id,
            "company_id": company_id,
            "blueprint_id": blueprint_id,
            "submitted_by_user_id": submitted_by_user_id,
            "input_payload": {"entities": entities},
            "source": source,
            "metadata": metadata or {},
            "status": "received",
        }
    ).execute()
    submission = submission_result.data[0]

    pipeline_runs: list[dict[str, Any]] = []
    for idx, entity in enumerate(entities):
        run_snapshot = {
            **snapshot,
            "entity": {
                "index": idx,
                "entity_type": entity.get("entity_type"),
                "input": entity.get("input") if isinstance(entity.get("input"), dict) else {},
            },
        }
        run = _create_pipeline_run_row(
            org_id=org_id,
            company_id=company_id,
            submission_id=submission["id"],
            blueprint_id=blueprint_id,
            blueprint_snapshot=run_snapshot,
            attempt=1,
        )
        _create_step_result_rows(
            org_id=org_id,
            company_id=company_id,
            submission_id=submission["id"],
            pipeline_run_id=run["id"],
            blueprint_steps=snapshot["steps"],
        )
        try:
            trigger_run_id = await trigger_pipeline_run(
                pipeline_run_id=run["id"],
                org_id=org_id,
                company_id=company_id,
            )
            run_update = (
                client.table("pipeline_runs")
                .update({"trigger_run_id": trigger_run_id, "status": "queued"})
                .eq("id", run["id"])
                .execute()
            )
            run = run_update.data[0]
        except Exception as exc:  # noqa: BLE001
            failed = (
                client.table("pipeline_runs")
                .update(
                    {
                        "status": "failed",
                        "error_message": "Failed to trigger Trigger.dev run",
                        "error_details": {"error": str(exc), "at": _iso_now()},
                    }
                )
                .eq("id", run["id"])
                .execute()
            )
            run = failed.data[0]

        pipeline_runs.append(
            {
                "entity_index": idx,
                "entity_type": entity.get("entity_type"),
                "pipeline_run_id": run["id"],
                "pipeline_run_status": run["status"],
                "trigger_run_id": run.get("trigger_run_id"),
            }
        )

    client.table("submissions").update({"status": "queued"}).eq("id", submission["id"]).execute()
    return {
        "submission_id": submission["id"],
        "pipeline_runs": pipeline_runs,
    }


async def create_fan_out_child_pipeline_runs(
    *,
    org_id: str,
    company_id: str,
    submission_id: str,
    parent_pipeline_run_id: str,
    blueprint_id: str,
    blueprint_snapshot: dict[str, Any],
    fan_out_entities: list[dict[str, Any]],
    start_from_position: int,
    parent_cumulative_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not fan_out_entities:
        return {
            "child_runs": [],
            "skipped_duplicates_count": 0,
            "skipped_duplicate_identifiers": [],
        }

    base_context = parent_cumulative_context if isinstance(parent_cumulative_context, dict) else {}
    steps = blueprint_snapshot.get("steps") if isinstance(blueprint_snapshot, dict) else None
    if not isinstance(steps, list):
        raise ValueError("blueprint_snapshot.steps must be present for fan-out child creation")

    child_runs: list[dict[str, Any]] = []
    skipped_duplicate_identifiers: list[str] = []
    seen_identifiers: set[str] = set()
    client = get_supabase_client()

    for idx, entity in enumerate(fan_out_entities):
        if not isinstance(entity, dict):
            continue
        identity_tokens = _extract_fan_out_identity_tokens(entity)
        duplicate_token = next(
            (token for token in identity_tokens if token in seen_identifiers),
            None,
        )
        if duplicate_token:
            skipped_duplicate_identifiers.append(_select_fan_out_duplicate_identifier(identity_tokens))
            continue
        seen_identifiers.update(identity_tokens)

        entity_input = {**base_context, **entity}
        child_snapshot = {
            **blueprint_snapshot,
            "entity": {
                "index": idx,
                "entity_type": entity.get("entity_type") or "person",
                "input": entity_input,
            },
            "fan_out": {
                "parent_pipeline_run_id": parent_pipeline_run_id,
                "start_from_position": start_from_position,
            },
        }
        run = _create_pipeline_run_row(
            org_id=org_id,
            company_id=company_id,
            submission_id=submission_id,
            blueprint_id=blueprint_id,
            blueprint_snapshot=child_snapshot,
            attempt=1,
            parent_pipeline_run_id=parent_pipeline_run_id,
        )
        _create_step_result_rows(
            org_id=org_id,
            company_id=company_id,
            submission_id=submission_id,
            pipeline_run_id=run["id"],
            blueprint_steps=steps,
            start_from_position=start_from_position,
        )
        try:
            trigger_run_id = await trigger_pipeline_run(
                pipeline_run_id=run["id"],
                org_id=org_id,
                company_id=company_id,
            )
            updated = (
                client.table("pipeline_runs")
                .update({"trigger_run_id": trigger_run_id, "status": "queued"})
                .eq("id", run["id"])
                .execute()
            )
            run = updated.data[0]
        except Exception as exc:  # noqa: BLE001
            failed = (
                client.table("pipeline_runs")
                .update(
                    {
                        "status": "failed",
                        "error_message": "Failed to trigger Trigger.dev run",
                        "error_details": {"error": str(exc), "at": _iso_now()},
                    }
                )
                .eq("id", run["id"])
                .execute()
            )
            run = failed.data[0]

        child_runs.append(
            {
                "pipeline_run_id": run["id"],
                "pipeline_run_status": run["status"],
                "trigger_run_id": run.get("trigger_run_id"),
                "entity_type": child_snapshot["entity"]["entity_type"],
                "entity_input": child_snapshot["entity"]["input"],
            }
        )

    return {
        "child_runs": child_runs,
        "skipped_duplicates_count": len(skipped_duplicate_identifiers),
        "skipped_duplicate_identifiers": skipped_duplicate_identifiers,
    }


async def retry_pipeline_run_for_submission(
    *,
    submission_id: str,
    org_id: str,
) -> dict[str, Any]:
    if not _is_uuid(submission_id) or not _is_uuid(org_id):
        raise ValueError("submission_id and org_id must be valid UUIDs")

    client = get_supabase_client()
    submission_result = (
        client.table("submissions")
        .select("*")
        .eq("id", submission_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    if not submission_result.data:
        raise ValueError("submission not found for org")

    submission = submission_result.data[0]
    snapshot = _load_blueprint_snapshot(org_id, submission["blueprint_id"])
    if snapshot is None:
        raise ValueError("blueprint not found or inactive for org")

    max_attempt_result = (
        client.table("pipeline_runs")
        .select("attempt")
        .eq("submission_id", submission_id)
        .order("attempt", desc=True)
        .limit(1)
        .execute()
    )
    next_attempt = (max_attempt_result.data[0]["attempt"] + 1) if max_attempt_result.data else 1

    run = _create_pipeline_run_row(
        org_id=org_id,
        company_id=submission["company_id"],
        submission_id=submission_id,
        blueprint_id=submission["blueprint_id"],
        blueprint_snapshot=snapshot,
        attempt=next_attempt,
    )

    _create_step_result_rows(
        org_id=org_id,
        company_id=submission["company_id"],
        submission_id=submission_id,
        pipeline_run_id=run["id"],
        blueprint_steps=snapshot["steps"],
    )

    try:
        trigger_run_id = await trigger_pipeline_run(
            pipeline_run_id=run["id"],
            org_id=org_id,
            company_id=submission["company_id"],
        )
        run_update = (
            client.table("pipeline_runs")
            .update({"trigger_run_id": trigger_run_id, "status": "queued"})
            .eq("id", run["id"])
            .execute()
        )
        run = run_update.data[0]
    except Exception as exc:  # noqa: BLE001
        failed = (
            client.table("pipeline_runs")
            .update(
                {
                    "status": "failed",
                    "error_message": "Failed to trigger Trigger.dev run",
                    "error_details": {"error": str(exc), "at": _iso_now()},
                }
            )
            .eq("id", run["id"])
            .execute()
        )
        run = failed.data[0]

    return {
        "submission_id": submission_id,
        "pipeline_run_id": run["id"],
        "pipeline_run_status": run["status"],
        "trigger_run_id": run.get("trigger_run_id"),
    }
