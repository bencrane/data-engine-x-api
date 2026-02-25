# app/routers/internal.py — Internal pipeline callbacks for Trigger.dev

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.config import get_settings
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.entity_relationships import (
    invalidate_entity_relationship,
    record_entity_relationship,
    record_entity_relationships_batch,
)
from app.services.company_intel_briefings import upsert_company_intel_briefing
from app.services.icp_job_titles import upsert_icp_job_titles
from app.services.person_intel_briefings import upsert_person_intel_briefing
from app.services.entity_state import (
    EntityStateVersionError,
    check_entity_freshness,
    resolve_company_entity_id,
    resolve_job_posting_entity_id,
    resolve_person_entity_id,
    upsert_company_entity,
    upsert_job_posting_entity,
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


def require_internal_context(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict[str, str | None]:
    settings = get_settings()
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    if credentials.credentials != settings.internal_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")

    org_id = request.headers.get("x-internal-org-id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-internal-org-id for internal authorization",
        )

    return {
        "org_id": org_id,
        "company_id": request.headers.get("x-internal-company-id"),
    }


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
    entity_type: Literal["company", "person", "job"]
    cumulative_context: dict[str, Any]
    last_operation_id: str | None = None


class InternalEntityStateFreshnessCheckRequest(BaseModel):
    entity_type: Literal["company", "person", "job"]
    identifiers: dict[str, Any]
    max_age_hours: float


class InternalPipelineRunFanOutRequest(BaseModel):
    parent_pipeline_run_id: str
    submission_id: str
    org_id: str
    company_id: str
    blueprint_snapshot: dict[str, Any]
    fan_out_entities: list[dict[str, Any]]
    start_from_position: int
    parent_cumulative_context: dict[str, Any] | None = None
    fan_out_operation_id: str | None = None
    provider: str | None = None
    provider_attempts: list[dict[str, Any]] | None = None


class InternalRecordStepTimelineEventRequest(BaseModel):
    org_id: str
    company_id: str | None = None
    submission_id: str
    pipeline_run_id: str
    entity_type: Literal["company", "person", "job"]
    cumulative_context: dict[str, Any]
    step_result_id: str
    step_position: int
    operation_id: str
    step_status: Literal["succeeded", "failed", "skipped"]
    skip_reason: str | None = None
    duration_ms: int | None = None
    provider_attempts: list[dict[str, Any]] | None = None
    condition: dict[str, Any] | None = None
    error_message: str | None = None
    error_details: dict[str, Any] | None = None
    operation_result: dict[str, Any] | None = None


class InternalRecordEntityRelationshipRequest(BaseModel):
    source_entity_type: str
    source_identifier: str
    relationship: str
    target_entity_type: str
    target_identifier: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    metadata: dict[str, Any] | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
    source_operation_id: str | None = None


class InternalRecordEntityRelationshipsBatchRequest(BaseModel):
    relationships: list[dict[str, Any]]


class InternalInvalidateEntityRelationshipRequest(BaseModel):
    source_identifier: str
    relationship: str
    target_identifier: str


class InternalUpsertIcpJobTitlesRequest(BaseModel):
    company_domain: str
    company_name: str | None = None
    company_description: str | None = None
    raw_parallel_output: dict[str, Any]
    parallel_run_id: str | None = None
    processor: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None


class InternalUpsertCompanyIntelBriefingsRequest(BaseModel):
    company_domain: str
    company_name: str | None = None
    client_company_name: str | None = None
    client_company_description: str | None = None
    raw_parallel_output: dict[str, Any]
    parallel_run_id: str | None = None
    processor: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None


class InternalUpsertPersonIntelBriefingsRequest(BaseModel):
    person_full_name: str
    person_linkedin_url: str | None = None
    person_current_company_name: str | None = None
    person_current_job_title: str | None = None
    client_company_name: str | None = None
    client_company_description: str | None = None
    customer_company_name: str | None = None
    raw_parallel_output: dict[str, Any]
    parallel_run_id: str | None = None
    processor: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None


def _normalize_timeline_status(status_value: str | None) -> str:
    if status_value in {"found", "not_found", "failed", "skipped"}:
        return status_value
    if status_value == "succeeded":
        return "found"
    return "failed"


def _map_step_status_to_timeline_status(step_status: str) -> str:
    if step_status == "succeeded":
        return "found"
    if step_status == "failed":
        return "failed"
    return "skipped"


def _select_provider_from_attempts(provider_attempts: list[dict[str, Any]] | None) -> str | None:
    if not provider_attempts:
        return None
    for attempt in provider_attempts:
        if attempt.get("status") in {"found", "succeeded"} and attempt.get("provider"):
            return str(attempt["provider"])
    first_provider = provider_attempts[0].get("provider")
    return str(first_provider) if first_provider else None


def _normalize_provider_attempts(provider_attempts: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(provider_attempts, list):
        return []
    normalized: list[dict[str, Any]] = []
    for attempt in provider_attempts:
        if isinstance(attempt, dict):
            normalized.append(attempt)
    return normalized


def _extract_fields_updated_from_operation_result(
    *,
    step_status: str,
    operation_result: dict[str, Any] | None,
) -> list[str] | None:
    if step_status != "succeeded" or not isinstance(operation_result, dict):
        return None
    output_payload = operation_result.get("output")
    if not isinstance(output_payload, dict):
        return None
    return sorted([key for key, value in output_payload.items() if value is not None]) or None


def _build_step_summary(
    *,
    step_position: int,
    operation_id: str,
    step_status: str,
    provider: str | None,
) -> str:
    provider_suffix = f" via {provider}" if provider else ""
    return f"step {step_position} {operation_id} {step_status}{provider_suffix}"


def _resolve_entity_id_for_step_event(
    *,
    org_id: str,
    entity_type: str,
    cumulative_context: dict[str, Any],
) -> str:
    if entity_type == "company":
        return resolve_company_entity_id(
            org_id=org_id,
            canonical_fields=cumulative_context,
            entity_id=cumulative_context.get("entity_id"),
        )
    if entity_type == "job":
        return resolve_job_posting_entity_id(
            org_id=org_id,
            canonical_fields=cumulative_context,
            entity_id=cumulative_context.get("entity_id"),
        )
    return resolve_person_entity_id(
        org_id=org_id,
        canonical_fields=cumulative_context,
        entity_id=cumulative_context.get("entity_id"),
    )


def _extract_company_context_for_timeline(
    *,
    run_blueprint_snapshot: dict[str, Any] | None,
    parent_cumulative_context: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(parent_cumulative_context, dict) and parent_cumulative_context:
        return parent_cumulative_context
    if isinstance(run_blueprint_snapshot, dict):
        entity_data = run_blueprint_snapshot.get("entity")
        if isinstance(entity_data, dict):
            entity_input = entity_data.get("input")
            if isinstance(entity_input, dict):
                return entity_input
    return {}


def _require_internal_org_id(request: Request) -> str:
    org_id = request.headers.get("x-internal-org-id")
    if not org_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing x-internal-org-id for internal authorization",
        )
    return org_id


@router.post("/entity-timeline/record-step-event", response_model=DataEnvelope)
async def internal_record_step_timeline_event(
    payload: InternalRecordStepTimelineEventRequest,
    _: None = Depends(require_internal_key),
):
    normalized_attempts = _normalize_provider_attempts(payload.provider_attempts)
    timeline_status = _map_step_status_to_timeline_status(payload.step_status)
    skip_reason = payload.skip_reason
    if payload.step_status == "skipped" and not skip_reason:
        skip_reason = "skipped"

    metadata: dict[str, Any] = {
        "event_type": "step_execution",
        "step_result_id": payload.step_result_id,
        "step_position": payload.step_position,
        "operation_id": payload.operation_id,
        "step_status": payload.step_status,
        "skip_reason": skip_reason,
        "duration_ms": payload.duration_ms,
        "provider_attempts": normalized_attempts,
        "condition": payload.condition,
        "error_message": payload.error_message,
        "error_details": payload.error_details,
    }

    try:
        entity_id = _resolve_entity_id_for_step_event(
            org_id=payload.org_id,
            entity_type=payload.entity_type,
            cumulative_context=payload.cumulative_context,
        )
        provider = _select_provider_from_attempts(normalized_attempts)
        fields_updated = _extract_fields_updated_from_operation_result(
            step_status=payload.step_status,
            operation_result=payload.operation_result,
        )
        summary = _build_step_summary(
            step_position=payload.step_position,
            operation_id=payload.operation_id,
            step_status=payload.step_status,
            provider=provider,
        )

        event = record_entity_event(
            org_id=payload.org_id,
            company_id=payload.company_id,
            entity_type=payload.entity_type,
            entity_id=entity_id,
            operation_id=payload.operation_id,
            pipeline_run_id=payload.pipeline_run_id,
            submission_id=payload.submission_id,
            provider=provider,
            status=timeline_status,
            fields_updated=fields_updated,
            summary=summary,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        return DataEnvelope(
            data={
                "attempted": True,
                "recorded": False,
                "event_id": None,
                "entity_id": None,
                "error": str(exc),
                "metadata": metadata,
            }
        )

    return DataEnvelope(
        data={
            "attempted": True,
            "recorded": event is not None,
            "event_id": event.get("id") if isinstance(event, dict) else None,
            "entity_id": entity_id,
            "error": None if event is not None else "timeline_write_not_recorded",
            "metadata": metadata,
        }
    )


@router.post("/entity-state/check-freshness", response_model=DataEnvelope)
async def internal_check_entity_state_freshness(
    payload: InternalEntityStateFreshnessCheckRequest,
    internal_context: dict[str, str | None] = Depends(require_internal_context),
):
    if payload.max_age_hours <= 0:
        return DataEnvelope(data={"fresh": False, "entity_id": None})

    freshness = check_entity_freshness(
        org_id=str(internal_context["org_id"]),
        entity_type=payload.entity_type,
        identifiers=payload.identifiers,
        max_age_hours=payload.max_age_hours,
    )
    return DataEnvelope(data=freshness)


@router.post("/entity-relationships/record", response_model=DataEnvelope)
async def internal_record_entity_relationship(
    payload: InternalRecordEntityRelationshipRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    result = record_entity_relationship(
        org_id=org_id,
        source_entity_type=payload.source_entity_type,
        source_identifier=payload.source_identifier,
        relationship=payload.relationship,
        target_entity_type=payload.target_entity_type,
        target_identifier=payload.target_identifier,
        source_entity_id=payload.source_entity_id,
        target_entity_id=payload.target_entity_id,
        metadata=payload.metadata,
        source_submission_id=payload.source_submission_id,
        source_pipeline_run_id=payload.source_pipeline_run_id,
        source_operation_id=payload.source_operation_id,
    )
    return DataEnvelope(data=result)


@router.post("/entity-relationships/record-batch", response_model=DataEnvelope)
async def internal_record_entity_relationships_batch(
    payload: InternalRecordEntityRelationshipsBatchRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    results = record_entity_relationships_batch(
        org_id=org_id,
        relationships=payload.relationships,
    )
    return DataEnvelope(data=results)


@router.post(
    "/entity-relationships/invalidate",
    response_model=DataEnvelope,
    responses={404: {"model": ErrorEnvelope}},
)
async def internal_invalidate_entity_relationship(
    payload: InternalInvalidateEntityRelationshipRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    result = invalidate_entity_relationship(
        org_id=org_id,
        source_identifier=payload.source_identifier,
        relationship=payload.relationship,
        target_identifier=payload.target_identifier,
    )
    if result is None:
        return error_response("Entity relationship not found", 404)
    return DataEnvelope(data=result)


@router.post("/icp-job-titles/upsert", response_model=DataEnvelope)
async def internal_upsert_icp_job_titles(
    payload: InternalUpsertIcpJobTitlesRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    result = upsert_icp_job_titles(
        org_id=org_id,
        company_domain=payload.company_domain,
        company_name=payload.company_name,
        company_description=payload.company_description,
        raw_parallel_output=payload.raw_parallel_output,
        parallel_run_id=payload.parallel_run_id,
        processor=payload.processor,
        source_submission_id=payload.source_submission_id,
        source_pipeline_run_id=payload.source_pipeline_run_id,
    )
    return DataEnvelope(data=result)


@router.post("/company-intel-briefings/upsert", response_model=DataEnvelope)
async def internal_upsert_company_intel_briefings(
    payload: InternalUpsertCompanyIntelBriefingsRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    result = upsert_company_intel_briefing(
        org_id=org_id,
        company_domain=payload.company_domain,
        company_name=payload.company_name,
        client_company_name=payload.client_company_name,
        client_company_description=payload.client_company_description,
        raw_parallel_output=payload.raw_parallel_output,
        parallel_run_id=payload.parallel_run_id,
        processor=payload.processor,
        source_submission_id=payload.source_submission_id,
        source_pipeline_run_id=payload.source_pipeline_run_id,
    )
    return DataEnvelope(data=result)


@router.post("/person-intel-briefings/upsert", response_model=DataEnvelope)
async def internal_upsert_person_intel_briefings(
    payload: InternalUpsertPersonIntelBriefingsRequest,
    request: Request,
    _: None = Depends(require_internal_key),
):
    org_id = _require_internal_org_id(request)
    result = upsert_person_intel_briefing(
        org_id=org_id,
        person_full_name=payload.person_full_name,
        person_linkedin_url=payload.person_linkedin_url,
        person_current_company_name=payload.person_current_company_name,
        person_current_job_title=payload.person_current_job_title,
        client_company_name=payload.client_company_name,
        client_company_description=payload.client_company_description,
        customer_company_name=payload.customer_company_name,
        raw_parallel_output=payload.raw_parallel_output,
        parallel_run_id=payload.parallel_run_id,
        processor=payload.processor,
        source_submission_id=payload.source_submission_id,
        source_pipeline_run_id=payload.source_pipeline_run_id,
    )
    return DataEnvelope(data=result)


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

    # Deliberately query by submission_id only (no parent filter) so status sync
    # always includes root, child, grandchild, and any deeper fan-out runs.
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

    fan_out_result = await create_fan_out_child_pipeline_runs(
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
    child_runs = fan_out_result["child_runs"]

    fan_out_operation_id = payload.fan_out_operation_id or "person.search"
    company_context = _extract_company_context_for_timeline(
        run_blueprint_snapshot=parent_run.get("blueprint_snapshot"),
        parent_cumulative_context=payload.parent_cumulative_context,
    )
    company_entity_id = resolve_company_entity_id(
        org_id=payload.org_id,
        canonical_fields=company_context,
        entity_id=company_context.get("entity_id") if isinstance(company_context, dict) else None,
    )

    record_entity_event(
        org_id=payload.org_id,
        company_id=payload.company_id,
        entity_type="company",
        entity_id=company_entity_id,
        operation_id=fan_out_operation_id,
        pipeline_run_id=payload.parent_pipeline_run_id,
        submission_id=payload.submission_id,
        provider=payload.provider,
        status="found" if child_runs else "not_found",
        fields_updated=["results", "result_count"],
        summary=f"{fan_out_operation_id} found {len(child_runs)} people",
        metadata={
            "event_type": "fan_out_discovery",
            "child_pipeline_run_ids": [row["pipeline_run_id"] for row in child_runs],
            "child_count_created": len(child_runs),
            "child_count_skipped_duplicates": fan_out_result["skipped_duplicates_count"],
            "skipped_duplicate_identifiers": fan_out_result["skipped_duplicate_identifiers"],
            "provider_attempts": payload.provider_attempts or [],
        },
    )

    for index, child in enumerate(child_runs):
        entity_input = child.get("entity_input")
        if not isinstance(entity_input, dict):
            continue
        person_entity_id = resolve_person_entity_id(
            org_id=payload.org_id,
            canonical_fields=entity_input,
            entity_id=entity_input.get("entity_id"),
        )
        record_entity_event(
            org_id=payload.org_id,
            company_id=payload.company_id,
            entity_type="person",
            entity_id=person_entity_id,
            operation_id=fan_out_operation_id,
            pipeline_run_id=child["pipeline_run_id"],
            submission_id=payload.submission_id,
            provider=payload.provider,
            status="found",
            fields_updated=sorted([key for key in entity_input.keys() if entity_input.get(key) is not None]),
            summary=f"{fan_out_operation_id}: discovered person #{index + 1}",
            metadata={
                "event_type": "fan_out_discovery",
                "parent_pipeline_run_id": payload.parent_pipeline_run_id,
                "discovered_from_company_entity_id": company_entity_id,
                "discovered_from_context": company_context,
                "provider_attempts": payload.provider_attempts or [],
            },
        )

    return DataEnvelope(
        data={
            "parent_pipeline_run_id": payload.parent_pipeline_run_id,
            "child_runs": child_runs,
            "child_run_ids": [row["pipeline_run_id"] for row in child_runs],
            "skipped_duplicates_count": fan_out_result["skipped_duplicates_count"],
            "skipped_duplicate_identifiers": fan_out_result["skipped_duplicate_identifiers"],
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
        elif payload.entity_type == "job":
            upserted = upsert_job_posting_entity(
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
