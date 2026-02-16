# app/routers/submissions.py — Submit data for processing

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.models.submission import Submission, SubmissionCreate, SubmissionStatus
from app.services.orchestrator import trigger_pipeline

router = APIRouter()


@router.post("/create", response_model=Submission)
async def create_submission(
    submission: SubmissionCreate,
    auth: AuthContext = Depends(get_current_auth),
):
    """
    Submit a batch of data for processing with a specified blueprint.
    Triggers the Trigger.dev pipeline task.
    """
    client = get_supabase_client()

    # Verify company belongs to org
    company_result = (
        client.table("companies")
        .select("id")
        .eq("id", submission.company_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not company_result.data:
        raise HTTPException(status_code=404, detail="Company not found")

    # Load blueprint with steps
    blueprint_result = (
        client.table("blueprints")
        .select("*")
        .eq("id", submission.blueprint_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not blueprint_result.data:
        raise HTTPException(status_code=404, detail="Blueprint not found")

    # Load blueprint steps with step details
    blueprint_steps_result = (
        client.table("blueprint_steps")
        .select("*, steps(*)")
        .eq("blueprint_id", submission.blueprint_id)
        .order("order")
        .execute()
    )

    # Format steps for Trigger.dev
    steps = [
        {
            "stepId": rs["step_id"],
            "slug": rs["steps"]["slug"],
            "order": rs["order"],
            "config": rs.get("config"),
        }
        for rs in blueprint_steps_result.data
    ]

    # Create submission record
    submission_data = submission.model_dump()
    submission_data["org_id"] = auth.org_id
    submission_data["status"] = SubmissionStatus.PENDING.value

    result = client.table("submissions").insert(submission_data).execute()
    submission_record = result.data[0]

    # Trigger pipeline via Trigger.dev
    await trigger_pipeline(
        submission_id=submission_record["id"],
        org_id=auth.org_id,
        data=submission.data,
        steps=steps,
    )

    return submission_record


@router.post("/list", response_model=list[Submission])
async def list_submissions(
    company_id: str | None = None,
    auth: AuthContext = Depends(get_current_auth),
):
    """List submissions for the authenticated org, optionally filtered by company."""
    client = get_supabase_client()
    query = client.table("submissions").select("*").eq("org_id", auth.org_id)

    if company_id:
        query = query.eq("company_id", company_id)

    result = query.order("created_at", desc=True).execute()
    return result.data


@router.post("/get", response_model=Submission)
async def get_submission(
    submission_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """Get a specific submission by ID."""
    client = get_supabase_client()
    result = (
        client.table("submissions")
        .select("*")
        .eq("id", submission_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Submission not found")
    return result.data
