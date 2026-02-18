# app/routers/entities_v1.py — Tenant entity intelligence query endpoints

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()
_security = HTTPBearer(auto_error=False)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned if cleaned else None


async def _resolve_flexible_auth(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_security),
) -> AuthContext | SuperAdminContext:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    try:
        return await get_current_super_admin(credentials)
    except HTTPException:
        pass
    return await get_current_auth(request=request, credentials=credentials)


class CompanyEntitiesListRequest(BaseModel):
    company_id: str | None = None
    canonical_domain: str | None = None
    industry: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)


class PersonEntitiesListRequest(BaseModel):
    company_id: str | None = None
    work_email: str | None = None
    linkedin_url: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)


class EntityTimelineRequest(BaseModel):
    entity_type: str
    entity_id: str
    org_id: str | None = None
    pipeline_run_id: str | None = None
    submission_id: str | None = None
    event_type: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)


@router.post(
    "/companies",
    response_model=DataEnvelope,
    responses={403: {"model": ErrorEnvelope}},
)
async def list_company_entities(
    payload: CompanyEntitiesListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    query = client.table("company_entities").select("*").eq("org_id", auth.org_id)

    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        if payload.company_id and payload.company_id != auth.company_id:
            return error_response("Forbidden company access", 403)
        query = query.eq("company_id", auth.company_id)
    elif payload.company_id:
        query = query.eq("company_id", payload.company_id)

    canonical_domain = _normalize_text(payload.canonical_domain)
    if canonical_domain:
        query = query.eq("canonical_domain", canonical_domain.lower())

    industry = _normalize_text(payload.industry)
    if industry:
        query = query.ilike("industry", f"%{industry}%")

    start = (payload.page - 1) * payload.per_page
    end = start + payload.per_page - 1
    result = query.order("updated_at", desc=True).range(start, end).execute()

    return DataEnvelope(
        data={
            "items": result.data,
            "pagination": {
                "page": payload.page,
                "per_page": payload.per_page,
                "returned": len(result.data),
            },
        }
    )


@router.post(
    "/persons",
    response_model=DataEnvelope,
    responses={403: {"model": ErrorEnvelope}},
)
async def list_person_entities(
    payload: PersonEntitiesListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    query = client.table("person_entities").select("*").eq("org_id", auth.org_id)

    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        if payload.company_id and payload.company_id != auth.company_id:
            return error_response("Forbidden company access", 403)
        query = query.eq("company_id", auth.company_id)
    elif payload.company_id:
        query = query.eq("company_id", payload.company_id)

    work_email = _normalize_text(payload.work_email)
    if work_email:
        query = query.eq("work_email", work_email.lower())

    linkedin_url = _normalize_text(payload.linkedin_url)
    if linkedin_url:
        query = query.eq("linkedin_url", linkedin_url.rstrip("/").lower())

    start = (payload.page - 1) * payload.per_page
    end = start + payload.per_page - 1
    result = query.order("updated_at", desc=True).range(start, end).execute()

    return DataEnvelope(
        data={
            "items": result.data,
            "pagination": {
                "page": payload.page,
                "per_page": payload.per_page,
                "returned": len(result.data),
            },
        }
    )


@router.post(
    "/timeline",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def get_entity_timeline(
    payload: EntityTimelineRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    entity_type = _normalize_text(payload.entity_type)
    if entity_type not in {"company", "person"}:
        return error_response("entity_type must be either 'company' or 'person'", 400)

    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id

    client = get_supabase_client()
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin timeline queries", 400)

    start = (payload.page - 1) * payload.per_page
    end = start + payload.per_page - 1
    query = (
        client.table("entity_timeline")
        .select("*")
        .eq("org_id", org_id)
        .eq("entity_type", entity_type)
        .eq("entity_id", payload.entity_id)
    )
    if payload.pipeline_run_id:
        query = query.eq("pipeline_run_id", payload.pipeline_run_id)
    if payload.submission_id:
        query = query.eq("submission_id", payload.submission_id)
    event_type = _normalize_text(payload.event_type)
    if event_type:
        query = query.eq("metadata->>event_type", event_type)

    if not is_super_admin and auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        query = query.eq("company_id", auth.company_id)

    result = query.order("created_at", desc=True).range(start, end).execute()
    return DataEnvelope(
        data={
            "entity_type": entity_type,
            "entity_id": payload.entity_id,
            "items": result.data,
            "pagination": {
                "page": payload.page,
                "per_page": payload.per_page,
                "returned": len(result.data),
            },
        }
    )
