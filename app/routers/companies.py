# app/routers/companies.py — Company CRUD (scoped to org)

from fastapi import APIRouter, Depends, HTTPException

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.models.company import Company, CompanyCreate

router = APIRouter()


@router.post("/list", response_model=list[Company])
async def list_companies(
    auth: AuthContext = Depends(get_current_auth),
):
    """List all companies for the authenticated org."""
    client = get_supabase_client()
    result = client.table("companies").select("*").eq("org_id", auth.org_id).execute()
    return result.data


@router.post("/get", response_model=Company)
async def get_company(
    company_id: str,
    auth: AuthContext = Depends(get_current_auth),
):
    """Get a specific company by ID."""
    client = get_supabase_client()
    result = (
        client.table("companies")
        .select("*")
        .eq("id", company_id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Company not found")
    return result.data


@router.post("/create", response_model=Company)
async def create_company(
    company: CompanyCreate,
    auth: AuthContext = Depends(get_current_auth),
):
    """Create a new company for the authenticated org."""
    client = get_supabase_client()
    company_data = company.model_dump()
    company_data["org_id"] = auth.org_id
    result = client.table("companies").insert(company_data).execute()
    return result.data[0]
