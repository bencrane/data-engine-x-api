# app/routers/tenant_companies.py — Tenant company endpoints

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


class CompanyListRequest(BaseModel):
    pass


class CompanyGetRequest(BaseModel):
    id: str


@router.post("/list", response_model=DataEnvelope)
async def list_companies(
    _: CompanyListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    query = client.table("companies").select("*").eq("org_id", auth.org_id)
    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        query = query.eq("id", auth.company_id)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def get_company(
    payload: CompanyGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if auth.role in {"company_admin", "member"} and payload.id != auth.company_id:
        return error_response("Forbidden company access", 403)

    client = get_supabase_client()
    result = (
        client.table("companies")
        .select("*")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Company not found", 404)
    return DataEnvelope(data=result.data[0])
