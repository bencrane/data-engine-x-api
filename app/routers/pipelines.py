# app/routers/pipelines.py — Pipeline run status, results

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.models.pipeline import PipelineRun, StepResult

router = APIRouter()


@router.post("/get", response_model=PipelineRun)
async def get_pipeline_run(
    pipeline_run_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """Get a pipeline run with all step results."""
    client = get_supabase_client()

    # Get pipeline run
    run_result = (
        client.table("pipeline_runs")
        .select("*")
        .eq("id", pipeline_run_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    # Get step results
    steps_result = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", pipeline_run_id)
        .order("step_order")
        .execute()
    )

    pipeline_run = run_result.data
    pipeline_run["step_results"] = steps_result.data

    return pipeline_run


@router.post("/list", response_model=list[PipelineRun])
async def list_pipeline_runs(
    submission_id: str | None = None,
    auth: AuthContext = Depends(get_current_auth),
):
    """List pipeline runs for the authenticated org."""
    client = get_supabase_client()
    query = client.table("pipeline_runs").select("*").eq("org_id", auth.org_id)

    if submission_id:
        query = query.eq("submission_id", submission_id)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/results", response_model=list[StepResult])
async def get_step_results(
    pipeline_run_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """Get step results for a pipeline run."""
    client = get_supabase_client()

    # Verify access to pipeline run
    run_result = (
        client.table("pipeline_runs")
        .select("id")
        .eq("id", pipeline_run_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not run_result.data:
        raise HTTPException(status_code=404, detail="Pipeline run not found")

    # Get step results
    steps_result = (
        client.table("step_results")
        .select("*")
        .eq("pipeline_run_id", pipeline_run_id)
        .order("step_order")
        .execute()
    )

    return steps_result.data
