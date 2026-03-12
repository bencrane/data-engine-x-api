from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.database import get_supabase_client
from app.services.company_blueprint_configs import get_company_blueprint_config
from app.services.submission_flow import (
    build_client_automation_submission_metadata,
    create_submission_and_trigger_pipeline,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(parsed)
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _schedule_in_org(org_id: str, schedule_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("company_blueprint_schedules")
        .select("*")
        .eq("org_id", org_id)
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def create_company_blueprint_schedule(
    *,
    org_id: str,
    company_id: str,
    config_id: str,
    name: str,
    timezone_name: str,
    cadence_minutes: int,
    next_run_at: str,
    is_active: bool,
    actor_user_id: str | None,
) -> dict[str, Any]:
    config = get_company_blueprint_config(org_id=org_id, config_id=config_id)
    if config is None:
        raise ValueError("config_id not found")
    if config["company_id"] != company_id:
        raise ValueError("config_id does not belong to company_id")
    if cadence_minutes <= 0:
        raise ValueError("cadence_minutes must be greater than zero")
    if _parse_iso(next_run_at) is None:
        raise ValueError("next_run_at must be a valid ISO-8601 timestamp")

    client = get_supabase_client()
    result = (
        client.table("company_blueprint_schedules")
        .insert(
            {
                "org_id": org_id,
                "company_id": company_id,
                "config_id": config_id,
                "name": name,
                "timezone": timezone_name or "UTC",
                "cadence_minutes": cadence_minutes,
                "next_run_at": next_run_at,
                "is_active": is_active,
                "created_by_user_id": actor_user_id,
                "updated_by_user_id": actor_user_id,
            }
        )
        .execute()
    )
    return result.data[0]


def list_company_blueprint_schedules(
    *,
    org_id: str,
    company_id: str | None = None,
    config_id: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    query = (
        client.table("company_blueprint_schedules")
        .select("*, company_blueprint_configs(id, name, blueprint_id)")
        .eq("org_id", org_id)
    )
    if company_id:
        query = query.eq("company_id", company_id)
    if config_id:
        query = query.eq("config_id", config_id)
    if is_active is not None:
        query = query.eq("is_active", is_active)
    result = query.order("created_at", desc=True).execute()
    return result.data


def get_company_blueprint_schedule(
    *,
    org_id: str,
    schedule_id: str,
) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("company_blueprint_schedules")
        .select("*, company_blueprint_configs(id, name, blueprint_id, input_payload)")
        .eq("org_id", org_id)
        .eq("id", schedule_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_company_blueprint_schedule(
    *,
    org_id: str,
    schedule_id: str,
    actor_user_id: str | None,
    config_id: str | None = None,
    name: str | None = None,
    timezone_name: str | None = None,
    cadence_minutes: int | None = None,
    next_run_at: str | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    existing = _schedule_in_org(org_id, schedule_id)
    if existing is None:
        return None

    if config_id is not None:
        config = get_company_blueprint_config(org_id=org_id, config_id=config_id)
        if config is None:
            raise ValueError("config_id not found")
        if config["company_id"] != existing["company_id"]:
            raise ValueError("config_id does not belong to schedule company")
    if cadence_minutes is not None and cadence_minutes <= 0:
        raise ValueError("cadence_minutes must be greater than zero")
    if next_run_at is not None and _parse_iso(next_run_at) is None:
        raise ValueError("next_run_at must be a valid ISO-8601 timestamp")

    update_data: dict[str, Any] = {"updated_by_user_id": actor_user_id}
    if config_id is not None:
        update_data["config_id"] = config_id
    if name is not None:
        update_data["name"] = name
    if timezone_name is not None:
        update_data["timezone"] = timezone_name
    if cadence_minutes is not None:
        update_data["cadence_minutes"] = cadence_minutes
    if next_run_at is not None:
        update_data["next_run_at"] = next_run_at
    if is_active is not None:
        update_data["is_active"] = is_active

    client = get_supabase_client()
    result = (
        client.table("company_blueprint_schedules")
        .update(update_data)
        .eq("org_id", org_id)
        .eq("id", schedule_id)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


def _claim_due_schedule_runs(
    *,
    now: datetime,
    limit: int,
    scheduler_task_id: str | None,
    scheduler_invoked_at: str,
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    due_schedules = (
        client.table("company_blueprint_schedules")
        .select("*")
        .eq("is_active", True)
        .lte("next_run_at", now.isoformat())
        .order("next_run_at")
        .limit(limit)
        .execute()
    )

    claimed: list[dict[str, Any]] = []
    for schedule in due_schedules.data:
        scheduled_for = schedule.get("next_run_at")
        if not isinstance(scheduled_for, str):
            continue

        try:
            run_insert = (
                client.table("company_blueprint_schedule_runs")
                .insert(
                    {
                        "org_id": schedule["org_id"],
                        "company_id": schedule["company_id"],
                        "config_id": schedule["config_id"],
                        "schedule_id": schedule["id"],
                        "scheduled_for": scheduled_for,
                        "scheduler_task_id": scheduler_task_id,
                        "scheduler_invoked_at": scheduler_invoked_at,
                        "status": "claimed",
                        "metadata": {"claim_source": "internal_scheduler"},
                    }
                )
                .execute()
            )
        except Exception:  # noqa: BLE001
            # Another evaluator already claimed this fire window.
            continue

        if not run_insert.data:
            continue
        run_row = run_insert.data[0]
        if run_row.get("submission_id"):
            continue

        schedule_next = _parse_iso(scheduled_for)
        if schedule_next is None:
            continue
        next_run = schedule_next + timedelta(minutes=int(schedule["cadence_minutes"]))
        schedule_update = (
            client.table("company_blueprint_schedules")
            .update(
                {
                    "next_run_at": next_run.isoformat(),
                    "last_claimed_at": now.isoformat(),
                }
            )
            .eq("id", schedule["id"])
            .eq("org_id", schedule["org_id"])
            .execute()
        )
        if not schedule_update.data:
            continue

        claimed.append(
            {
                "schedule": schedule,
                "schedule_run": run_row,
            }
        )
    return claimed


async def evaluate_and_execute_due_schedules(
    *,
    max_schedules: int = 100,
    scheduler_task_id: str | None = None,
    scheduler_invoked_at: str | None = None,
) -> dict[str, Any]:
    now = _utc_now()
    invoked_at = scheduler_invoked_at or now.isoformat()
    claimed = _claim_due_schedule_runs(
        now=now,
        limit=max_schedules,
        scheduler_task_id=scheduler_task_id,
        scheduler_invoked_at=invoked_at,
    )
    client = get_supabase_client()

    processed: list[dict[str, Any]] = []
    for item in claimed:
        schedule = item["schedule"]
        schedule_run = item["schedule_run"]
        run_id = schedule_run["id"]

        config = get_company_blueprint_config(org_id=schedule["org_id"], config_id=schedule["config_id"])
        if config is None or not config.get("is_active", True):
            client.table("company_blueprint_schedule_runs").update(
                {
                    "status": "skipped",
                    "finished_at": _utc_now().isoformat(),
                    "error_message": "config missing or inactive",
                }
            ).eq("id", run_id).execute()
            processed.append({"schedule_run_id": run_id, "status": "skipped"})
            continue

        client.table("company_blueprint_schedule_runs").update(
            {"status": "running", "started_at": _utc_now().isoformat()}
        ).eq("id", run_id).execute()

        provenance = build_client_automation_submission_metadata(
            config_id=config["id"],
            schedule_id=schedule["id"],
            schedule_run_id=run_id,
            scheduler_invoked_at=invoked_at,
            scheduler_task_id=scheduler_task_id,
            scheduled_for=schedule_run["scheduled_for"],
        )

        try:
            submission_result = await create_submission_and_trigger_pipeline(
                org_id=schedule["org_id"],
                company_id=schedule["company_id"],
                blueprint_id=config["blueprint_id"],
                input_payload=config.get("input_payload") or {},
                source="client_automation_schedule",
                metadata=provenance,
                submitted_by_user_id=None,
            )
            submission_id = submission_result["submission_id"]
            pipeline_run_id = submission_result["pipeline_run_id"]

            client.table("company_blueprint_schedule_runs").update(
                {
                    "status": "succeeded",
                    "submission_id": submission_id,
                    "pipeline_run_id": pipeline_run_id,
                    "finished_at": _utc_now().isoformat(),
                }
            ).eq("id", run_id).execute()
            client.table("company_blueprint_schedules").update(
                {
                    "last_succeeded_at": _utc_now().isoformat(),
                    "last_submission_id": submission_id,
                    "last_error": None,
                }
            ).eq("id", schedule["id"]).eq("org_id", schedule["org_id"]).execute()
            processed.append(
                {
                    "schedule_run_id": run_id,
                    "status": "succeeded",
                    "submission_id": submission_id,
                    "pipeline_run_id": pipeline_run_id,
                }
            )
        except Exception as exc:  # noqa: BLE001
            # Recover from duplicate submission creation if a retry races after partial progress.
            existing_submission = (
                client.table("submissions")
                .select("id")
                .eq("org_id", schedule["org_id"])
                .eq("source", "client_automation_schedule")
                .eq("metadata->>schedule_run_id", run_id)
                .limit(1)
                .execute()
            )
            if existing_submission.data:
                submission_id = existing_submission.data[0]["id"]
                client.table("company_blueprint_schedule_runs").update(
                    {
                        "status": "succeeded",
                        "submission_id": submission_id,
                        "finished_at": _utc_now().isoformat(),
                        "error_message": None,
                        "error_details": None,
                    }
                ).eq("id", run_id).execute()
                client.table("company_blueprint_schedules").update(
                    {
                        "last_succeeded_at": _utc_now().isoformat(),
                        "last_submission_id": submission_id,
                        "last_error": None,
                    }
                ).eq("id", schedule["id"]).eq("org_id", schedule["org_id"]).execute()
                processed.append(
                    {
                        "schedule_run_id": run_id,
                        "status": "succeeded",
                        "submission_id": submission_id,
                        "recovered_from_duplicate": True,
                    }
                )
                continue

            client.table("company_blueprint_schedule_runs").update(
                {
                    "status": "failed",
                    "finished_at": _utc_now().isoformat(),
                    "error_message": str(exc),
                    "error_details": {"error": str(exc)},
                }
            ).eq("id", run_id).execute()
            client.table("company_blueprint_schedules").update(
                {
                    "last_failed_at": _utc_now().isoformat(),
                    "last_error": str(exc),
                }
            ).eq("id", schedule["id"]).eq("org_id", schedule["org_id"]).execute()
            processed.append({"schedule_run_id": run_id, "status": "failed", "error": str(exc)})

    return {
        "scheduler_invoked_at": invoked_at,
        "claimed_count": len(claimed),
        "processed_count": len(processed),
        "results": processed,
    }
