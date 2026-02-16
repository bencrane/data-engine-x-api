# app/routers/internal.py — Internal pipeline callbacks for Trigger.dev

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

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


class InternalMarkRemainingSkippedRequest(BaseModel):
    pipeline_run_id: str
    from_step_position: int


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
