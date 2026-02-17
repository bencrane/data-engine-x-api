# app/routers/internal.py — Internal pipeline callbacks for Trigger.dev

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.entity_state import (
    EntityStateVersionError,
    upsert_company_entity,
    upsert_person_entity,
)
from app.services.entity_timeline import record_entity_event
from app.services.submission_flow import create_fan_out_child_pipeline_runs

router = APIRouter()
security = HTTPBearer(auto_error=False)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_internal_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> None:
    settings = get_settings()
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    if credentials.credentials != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
    return None


class InternalPipelineRunGetRequest(BaseModel):
    pipeline_run_id: str


class InternalPipelineRunStatusUpdateRequest(BaseModel):
    pipeline_run_id: str
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    trigger_run_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class InternalStepResultUpdateRequest(BaseModel):
    step_result_id: str
    status: Literal["queued", "running", "succeeded", "failed", "skipped", "retrying"]
    input_payload: dict[str, Any] | list[Any] | None = None
    output_payload: dict[str, Any] | list[Any] | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    task_run_id: str | None = None


class InternalSubmissionStatusUpdateRequest(BaseModel):
    submission_id: str
    status: Literal["received", "validated", "queued", "running", "completed", "failed", "canceled"]


class InternalSubmissionSyncStatusRequest(BaseModel):
    submission_id: str


class InternalMarkRemainingSkippedRequest(BaseModel):
    pipeline_run_id: str
    from_step_position: int


class InternalEntityStateUpsertRequest(BaseModel):
    pipeline_run_id: str
    entity_type: Literal["company", "person"]
    cumulative_context: dict[str, Any]
    last_operation_id: str | None = None


class InternalPipelineRunFanOutRequest(BaseModel):
    parent_pipeline_run_id: str
    submission_id: str
    org_id: str
    company_id: str
    blueprint_snapshot: dict[str, Any]
    fan_out_entities: list[dict[str, Any]]
    start_from_position: int
    parent_cumulative_context: dict[str, Any] | None = None


def _normalize_timeline_status(status_value: str | None) -> str:
    if status_value in {"found", "not_found", "failed", "skipped"}:
        return status_value
    if status_value == "succeeded":
        return "found"
    return "failed"


def _select_provider_from_attempts(provider_attempts: list[dict[str, Any]] | None) -> str | None:
    if not provider_attempts:
        return None
    for attempt in provider_attempts:
        if attempt.get("status") in {"found", "succeeded"} and attempt.get("provider"):
            return str(attempt["provider"])
    first_provider = provider_attempts[0].get("provider")
    return str(first_provider) if first_provider else None


@router.post("/pipeline-runs/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def internal_get_pipeline_run(
    payload: InternalPipelineRunGetRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    run_result = (
        client.table("pipeline_runs")
        .select("*, submissions(*)")
        .eq("id", payload.pipeline_run_id)
        .limit(1)
        .execute()
    )
    if not run_result.data:
        return error_response("Pipeline run not found", 404)
    run = run_result.data[0]
    step_results = (
        client.table("step_results")
        .select("*, steps(*)")
        .eq("pipeline_run_id", payload.pipeline_run_id)
        .order("step_position")
        .execute()
    )
    run["step_results"] = step_results.data
    return DataEnvelope(data=run)


@router.post("/pipeline-runs/update-status", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def internal_update_pipeline_run_status(
    payload: InternalPipelineRunStatusUpdateRequest,
    _: None = Depends(require_internal_key),
):
    update_data = payload.model_dump(exclude={"pipeline_run_id"}, exclude_none=True)
    if payload.status == "running" and update_data.get("started_at") is None:
        update_data["started_at"] = _utc_now_iso()
    if payload.status in {"succeeded", "failed", "canceled"} and update_data.get("finished_at") is None:
        update_data["finished_at"] = _utc_now_iso()
    client = get_supabase_client()
    result = (
        client.table("pipeline_runs")
        .update(update_data)
        .eq("id", payload.pipeline_run_id)
        .execute()
    )
    if not result.data:
        return error_response("Pipeline run not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/step-results/update", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def internal_update_step_result(
    payload: InternalStepResultUpdateRequest,
    _: None = Depends(require_internal_key),
):
    update_data = payload.model_dump(exclude={"step_result_id"}, exclude_none=True)
    if payload.status == "running" and update_data.get("started_at") is None:
        update_data["started_at"] = _utc_now_iso()
    if payload.status in {"succeeded", "failed", "skipped"} and update_data.get("finished_at") is None:
        update_data["finished_at"] = _utc_now_iso()
    client = get_supabase_client()
    result = (
        client.table("step_results")
        .update(update_data)
        .eq("id", payload.step_result_id)
        .execute()
    )
    if not result.data:
        return error_response("Step result not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/step-results/mark-remaining-skipped", response_model=DataEnvelope)
async def internal_mark_remaining_skipped(
    payload: InternalMarkRemainingSkippedRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    queued = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", payload.pipeline_run_id)
        .eq("status", "queued")
        .execute()
    )
    updated_rows: list[dict[str, Any]] = []
    for row in queued.data:
        if row["step_position"] > payload.from_step_position:
            update_result = (
                client.table("step_results")
                .update(
                    {
                        "status": "skipped",
                        "finished_at": _utc_now_iso(),
                    }
                )
                .eq("id", row["id"])
                .execute()
            )
            if update_result.data:
                updated_rows.append(update_result.data[0])
    return DataEnvelope(data=updated_rows)


@router.post("/submissions/update-status", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def internal_update_submission_status(
    payload: InternalSubmissionStatusUpdateRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    result = (
        client.table("submissions")
        .update({"status": payload.status})
        .eq("id", payload.submission_id)
        .execute()
    )
    if not result.data:
        return error_response("Submission not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/submissions/sync-status", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def internal_sync_submission_status(
    payload: InternalSubmissionSyncStatusRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    submission_result = (
        client.table("submissions")
        .select("id")
        .eq("id", payload.submission_id)
        .limit(1)
        .execute()
    )
    if not submission_result.data:
        return error_response("Submission not found", 404)

    runs = (
        client.table("pipeline_runs")
        .select("status")
        .eq("submission_id", payload.submission_id)
        .execute()
    )
    statuses = [row.get("status") for row in runs.data]
    if not statuses:
        submission_status = "received"
    elif all(status == "succeeded" for status in statuses):
        submission_status = "completed"
    elif any(status == "failed" for status in statuses):
        submission_status = "failed"
    elif any(status == "running" for status in statuses):
        submission_status = "running"
    elif any(status == "queued" for status in statuses):
        submission_status = "queued"
    else:
        submission_status = "running"

    result = (
        client.table("submissions")
        .update({"status": submission_status})
        .eq("id", payload.submission_id)
        .execute()
    )
    return DataEnvelope(data=result.data[0])


@router.post(
    "/pipeline-runs/fan-out",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def internal_fan_out_pipeline_runs(
    payload: InternalPipelineRunFanOutRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    parent_result = (
        client.table("pipeline_runs")
        .select("id, org_id, company_id, submission_id, blueprint_id, blueprint_snapshot")
        .eq("id", payload.parent_pipeline_run_id)
        .limit(1)
        .execute()
    )
    if not parent_result.data:
        return error_response("Parent pipeline run not found", 404)
    parent_run = parent_result.data[0]

    if (
        parent_run.get("org_id") != payload.org_id
        or parent_run.get("company_id") != payload.company_id
        or parent_run.get("submission_id") != payload.submission_id
    ):
        return error_response("Parent run tenancy/submission mismatch", 400)

    if payload.start_from_position <= 0:
        return error_response("start_from_position must be greater than 0", 400)

    child_runs = await create_fan_out_child_pipeline_runs(
        org_id=payload.org_id,
        company_id=payload.company_id,
        submission_id=payload.submission_id,
        parent_pipeline_run_id=payload.parent_pipeline_run_id,
        blueprint_id=parent_run["blueprint_id"],
        blueprint_snapshot=payload.blueprint_snapshot,
        fan_out_entities=payload.fan_out_entities,
        start_from_position=payload.start_from_position,
        parent_cumulative_context=payload.parent_cumulative_context,
    )

    return DataEnvelope(
        data={
            "parent_pipeline_run_id": payload.parent_pipeline_run_id,
            "child_runs": child_runs,
            "child_run_ids": [row["pipeline_run_id"] for row in child_runs],
        }
    )


@router.post(
    "/entity-state/upsert",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def internal_upsert_entity_state(
    payload: InternalEntityStateUpsertRequest,
    _: None = Depends(require_internal_key),
):
    client = get_supabase_client()
    run_result = (
        client.table("pipeline_runs")
        .select("id, org_id, company_id, submission_id, status")
        .eq("id", payload.pipeline_run_id)
        .limit(1)
        .execute()
    )
    if not run_result.data:
        return error_response("Pipeline run not found", 404)

    run = run_result.data[0]
    if run.get("status") != "succeeded":
        return error_response("Entity state upsert requires a succeeded pipeline run", 400)

    last_step_result = (
        client.table("step_results")
        .select("step_position, output_payload")
        .eq("pipeline_run_id", payload.pipeline_run_id)
        .eq("status", "succeeded")
        .order("step_position", desc=True)
        .limit(1)
        .execute()
    )
    latest_output_payload = last_step_result.data[0].get("output_payload") if last_step_result.data else {}
    operation_result = (
        latest_output_payload.get("operation_result")
        if isinstance(latest_output_payload, dict)
        else {}
    )
    if not isinstance(operation_result, dict):
        operation_result = {}

    try:
        if payload.entity_type == "company":
            upserted = upsert_company_entity(
                org_id=run["org_id"],
                company_id=run.get("company_id"),
                entity_id=payload.cumulative_context.get("entity_id"),
                canonical_fields=payload.cumulative_context,
                last_operation_id=payload.last_operation_id,
                last_run_id=run["id"],
            )
        else:
            upserted = upsert_person_entity(
                org_id=run["org_id"],
                company_id=run.get("company_id"),
                entity_id=payload.cumulative_context.get("entity_id"),
                canonical_fields=payload.cumulative_context,
                last_operation_id=payload.last_operation_id,
                last_run_id=run["id"],
            )
    except EntityStateVersionError as exc:
        return error_response(str(exc), 400)

    operation_id = (
        operation_result.get("operation_id")
        or payload.last_operation_id
        or upserted.get("last_operation_id")
        or "unknown.operation"
    )
    operation_output = operation_result.get("output")
    fields_updated = (
        sorted([key for key in operation_output.keys() if operation_output.get(key) is not None])
        if isinstance(operation_output, dict)
        else None
    )
    provider_attempts = operation_result.get("provider_attempts")
    provider = _select_provider_from_attempts(provider_attempts if isinstance(provider_attempts, list) else None)
    timeline_status = _normalize_timeline_status(operation_result.get("status"))

    summary_provider = provider or "provider"
    summary_fields = fields_updated[:6] if fields_updated else []
    summary_suffix = f"found {', '.join(summary_fields)}" if summary_fields else timeline_status
    summary = f"{summary_provider}: {summary_suffix}"

    record_entity_event(
        org_id=run["org_id"],
        company_id=run.get("company_id"),
        entity_type=payload.entity_type,
        entity_id=upserted["entity_id"],
        operation_id=str(operation_id),
        pipeline_run_id=run["id"],
        submission_id=run.get("submission_id"),
        provider=provider,
        status=timeline_status,
        fields_updated=fields_updated,
        summary=summary,
        metadata={
            "last_operation_id": payload.last_operation_id,
            "provider_attempts": provider_attempts if isinstance(provider_attempts, list) else [],
            "operation_status": operation_result.get("status"),
            "pipeline_entity_type": payload.entity_type,
        },
    )

    return DataEnvelope(data=upserted)
