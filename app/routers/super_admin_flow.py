# app/routers/super_admin_flow.py — Super-admin submission/pipeline endpoints

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import SuperAdminContext, get_current_super_admin
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.submission_flow import (
    create_submission_and_trigger_pipeline,
    retry_pipeline_run_for_submission,
)

router = APIRouter()


class SuperAdminSubmissionCreateRequest(BaseModel):
    org_id: str
    company_id: str
    blueprint_id: str
    input_payload: dict[str, Any] | list[Any]
    source: str | None = None
    metadata: dict[str, Any] | None = None


class SuperAdminSubmissionsListRequest(BaseModel):
    org_id: str | None = None
    company_id: str | None = None
    blueprint_id: str | None = None
    status: str | None = None


class SuperAdminSubmissionGetRequest(BaseModel):
    id: str


class SuperAdminPipelineRunsListRequest(BaseModel):
    org_id: str | None = None
    submission_id: str | None = None
    status: str | None = None


class SuperAdminPipelineRunGetRequest(BaseModel):
    id: str


class SuperAdminPipelineRunRetryRequest(BaseModel):
    submission_id: str


class SuperAdminStepResultsListRequest(BaseModel):
    pipeline_run_id: str


@router.post("/submissions/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_submission(
    payload: SuperAdminSubmissionCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    try:
        result = await create_submission_and_trigger_pipeline(
            org_id=payload.org_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            input_payload=payload.input_payload,
            source=payload.source,
            metadata=payload.metadata,
            submitted_by_user_id=None,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/submissions/list", response_model=DataEnvelope)
async def super_admin_list_submissions(
    payload: SuperAdminSubmissionsListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("submissions").select("*")
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    if payload.company_id:
        query = query.eq("company_id", payload.company_id)
    if payload.blueprint_id:
        query = query.eq("blueprint_id", payload.blueprint_id)
    if payload.status:
        query = query.eq("status", payload.status)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/submissions/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_submission(
    payload: SuperAdminSubmissionGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    submission_result = (
        client.table("submissions")
        .select("*")
        .eq("id", payload.id)
        .limit(1)
        .execute()
    )
    if not submission_result.data:
        return error_response("Submission not found", 404)
    submission = submission_result.data[0]
    runs = (
        client.table("pipeline_runs")
        .select("*")
        .eq("submission_id", payload.id)
        .order("created_at", desc=True)
        .execute()
    )
    submission["pipeline_runs"] = runs.data
    return DataEnvelope(data=submission)


@router.post("/pipeline-runs/list", response_model=DataEnvelope)
async def super_admin_list_pipeline_runs(
    payload: SuperAdminPipelineRunsListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("pipeline_runs").select("*")
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    if payload.submission_id:
        query = query.eq("submission_id", payload.submission_id)
    if payload.status:
        query = query.eq("status", payload.status)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/pipeline-runs/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_pipeline_run(
    payload: SuperAdminPipelineRunGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    run_result = (
        client.table("pipeline_runs")
        .select("*")
        .eq("id", payload.id)
        .limit(1)
        .execute()
    )
    if not run_result.data:
        return error_response("Pipeline run not found", 404)
    run = run_result.data[0]
    step_results = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", payload.id)
        .order("step_position")
        .execute()
    )
    run["step_results"] = step_results.data
    return DataEnvelope(data=run)


@router.post("/pipeline-runs/retry", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_retry_pipeline_run(
    payload: SuperAdminPipelineRunRetryRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    sub = (
        client.table("submissions")
        .select("id, org_id")
        .eq("id", payload.submission_id)
        .limit(1)
        .execute()
    )
    if not sub.data:
        return error_response("Submission not found", 400)
    org_id = sub.data[0]["org_id"]
    try:
        result = await retry_pipeline_run_for_submission(
            submission_id=payload.submission_id,
            org_id=org_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/step-results/list", response_model=DataEnvelope)
async def super_admin_list_step_results(
    payload: SuperAdminStepResultsListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", payload.pipeline_run_id)
        .order("step_position")
        .execute()
    )
    return DataEnvelope(data=result.data)
