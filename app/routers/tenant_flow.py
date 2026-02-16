# app/routers/tenant_flow.py — Tenant submission/pipeline endpoints

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.submission_flow import (
    create_submission_and_trigger_pipeline,
)

router = APIRouter()


def _company_scope_forbidden(auth: AuthContext, company_id: str) -> bool:
    return auth.role in {"company_admin", "member"} and auth.company_id != company_id


class SubmissionCreateRequest(BaseModel):
    company_id: str
    blueprint_id: str
    input_payload: dict[str, Any] | list[Any]
    source: str | None = None
    metadata: dict[str, Any] | None = None


class SubmissionsListRequest(BaseModel):
    company_id: str | None = None
    blueprint_id: str | None = None
    status: str | None = None


class SubmissionGetRequest(BaseModel):
    id: str


class PipelineRunsListRequest(BaseModel):
    submission_id: str | None = None
    status: str | None = None


class PipelineRunGetRequest(BaseModel):
    id: str


class StepResultsListRequest(BaseModel):
    pipeline_run_id: str


@router.post("/submissions/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}})
async def create_submission(
    payload: SubmissionCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if _company_scope_forbidden(auth, payload.company_id):
        return error_response("Forbidden company access", 403)
    try:
        result = await create_submission_and_trigger_pipeline(
            org_id=auth.org_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            input_payload=payload.input_payload,
            source=payload.source,
            metadata=payload.metadata,
            submitted_by_user_id=auth.user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/submissions/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}})
async def list_submissions(
    payload: SubmissionsListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    query = client.table("submissions").select("*").eq("org_id", auth.org_id)

    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        query = query.eq("company_id", auth.company_id)
    elif payload.company_id:
        query = query.eq("company_id", payload.company_id)

    if payload.blueprint_id:
        query = query.eq("blueprint_id", payload.blueprint_id)
    if payload.status:
        query = query.eq("status", payload.status)

    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/submissions/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_submission(
    payload: SubmissionGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("submissions")
        .select("*")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Submission not found", 404)
    submission = result.data[0]

    if auth.role in {"company_admin", "member"} and submission["company_id"] != auth.company_id:
        return error_response("Forbidden submission access", 403)

    runs = (
        client.table("pipeline_runs")
        .select("*")
        .eq("submission_id", payload.id)
        .eq("org_id", auth.org_id)
        .order("created_at", desc=True)
        .execute()
    )
    submission["pipeline_runs"] = runs.data
    return DataEnvelope(data=submission)


@router.post("/pipeline-runs/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}})
async def list_pipeline_runs(
    payload: PipelineRunsListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    query = client.table("pipeline_runs").select("*").eq("org_id", auth.org_id)

    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        query = query.eq("company_id", auth.company_id)

    if payload.submission_id:
        query = query.eq("submission_id", payload.submission_id)
    if payload.status:
        query = query.eq("status", payload.status)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/pipeline-runs/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_pipeline_run(
    payload: PipelineRunGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("pipeline_runs")
        .select("*")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Pipeline run not found", 404)
    run = result.data[0]
    if auth.role in {"company_admin", "member"} and run["company_id"] != auth.company_id:
        return error_response("Forbidden pipeline run access", 403)

    steps = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", payload.id)
        .eq("org_id", auth.org_id)
        .order("step_position")
        .execute()
    )
    run["step_results"] = steps.data
    return DataEnvelope(data=run)


@router.post("/step-results/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def list_step_results(
    payload: StepResultsListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    run = (
        client.table("pipeline_runs")
        .select("id, org_id, company_id")
        .eq("id", payload.pipeline_run_id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not run.data:
        return error_response("Pipeline run not found", 404)
    if auth.role in {"company_admin", "member"} and run.data[0]["company_id"] != auth.company_id:
        return error_response("Forbidden pipeline run access", 403)

    steps = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", payload.pipeline_run_id)
        .eq("org_id", auth.org_id)
        .order("step_position")
        .execute()
    )
    return DataEnvelope(data=steps.data)
