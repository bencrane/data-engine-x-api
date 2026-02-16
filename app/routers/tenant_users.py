# app/routers/tenant_users.py — Tenant user endpoints (org_admin only)

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class UserListRequest(BaseModel):
    pass


class UserGetRequest(BaseModel):
    id: str


def _require_org_admin(auth: AuthContext):
    if auth.role != "org_admin":
        return error_response("org_admin role required", 403)
    return None


@router.post("/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}})
async def list_users(
    _: UserListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    denied = _require_org_admin(auth)
    if denied:
        return denied

    client = get_supabase_client()
    result = (
        client.table("users")
        .select("id, org_id, company_id, email, full_name, role, is_active, created_at, updated_at")
        .eq("org_id", auth.org_id)
        .order("created_at", desc=True)
        .execute()
    )
    return DataEnvelope(data=result.data)


@router.post("/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_user(
    payload: UserGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    denied = _require_org_admin(auth)
    if denied:
        return denied

    client = get_supabase_client()
    result = (
        client.table("users")
        .select("id, org_id, company_id, email, full_name, role, is_active, created_at, updated_at")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("User not found", 404)
    return DataEnvelope(data=result.data[0])
