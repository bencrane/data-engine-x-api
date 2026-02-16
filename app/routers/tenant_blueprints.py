# app/routers/tenant_blueprints.py — Tenant blueprint read endpoints

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class BlueprintListRequest(BaseModel):
    pass


class BlueprintGetRequest(BaseModel):
    id: str


@router.post("/list", response_model=DataEnvelope)
async def list_blueprints(
    _: BlueprintListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("*")
        .eq("org_id", auth.org_id)
        .order("created_at", desc=True)
        .execute()
    )
    return DataEnvelope(data=result.data)


@router.post("/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def get_blueprint(
    payload: BlueprintGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*, steps(*))")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Blueprint not found", 404)
    return DataEnvelope(data=result.data[0])
