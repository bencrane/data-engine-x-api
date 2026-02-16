# app/routers/tenant_steps.py — Tenant step read endpoints

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class StepListRequest(BaseModel):
    pass


class StepGetRequest(BaseModel):
    id: str | None = None
    slug: str | None = None


@router.post("/list", response_model=DataEnvelope)
async def list_steps(
    _: StepListRequest,
    __: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("steps")
        .select("*")
        .eq("is_active", True)
        .order("created_at", desc=True)
        .execute()
    )
    return DataEnvelope(data=result.data)


@router.post("/get", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_step(
    payload: StepGetRequest,
    __: AuthContext = Depends(get_current_auth),
):
    if not payload.id and not payload.slug:
        return error_response("Provide either id or slug", 400)

    client = get_supabase_client()
    query = client.table("steps").select("*").eq("is_active", True)
    if payload.id:
        query = query.eq("id", payload.id)
    else:
        query = query.eq("slug", payload.slug)
    result = query.limit(1).execute()
    if not result.data:
        return error_response("Step not found", 404)
    return DataEnvelope(data=result.data[0])
