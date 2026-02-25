# app/routers/entities_v1.py — Tenant entity intelligence query endpoints

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.company_intel_briefings import query_company_intel_briefings
from app.services.entity_relationships import query_entity_relationships
from app.services.icp_job_titles import query_icp_job_titles
from app.services.person_intel_briefings import query_person_intel_briefings

router = APIRouter()
entity_relationships_router = APIRouter()
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
    title: str | None = None
    seniority: str | None = None
    department: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)


class JobPostingEntitiesListRequest(BaseModel):
    company_id: str | None = None
    company_domain: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    seniority: str | None = None
    country_code: str | None = None
    remote: bool | None = None
    posting_status: str | None = None
    org_id: str | None = None
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


class EntitySnapshotsRequest(BaseModel):
    entity_type: str
    entity_id: str
    limit: int = Field(default=10, ge=1, le=100)
    org_id: str | None = None


class EntityRelationshipQueryRequest(BaseModel):
    source_identifier: str | None = None
    target_identifier: str | None = None
    relationship: str | None = None
    source_entity_type: str | None = None
    target_entity_type: str | None = None
    include_invalidated: bool = False
    limit: int = 100
    offset: int = 0
    org_id: str | None = None


class IcpJobTitlesQueryRequest(BaseModel):
    company_domain: str | None = None
    limit: int = 100
    offset: int = 0
    org_id: str | None = None


class CompanyIntelBriefingsQueryRequest(BaseModel):
    company_domain: str | None = None
    client_company_name: str | None = None
    limit: int = 100
    offset: int = 0
    org_id: str | None = None


class PersonIntelBriefingsQueryRequest(BaseModel):
    person_linkedin_url: str | None = None
    person_current_company_name: str | None = None
    client_company_name: str | None = None
    limit: int = 100
    offset: int = 0
    org_id: str | None = None


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

    title = _normalize_text(payload.title)
    if title:
        query = query.ilike("title", f"%{title}%")

    seniority = _normalize_text(payload.seniority)
    if seniority:
        query = query.eq("seniority", seniority)

    department = _normalize_text(payload.department)
    if department:
        query = query.ilike("department", f"%{department}%")

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
    "/job-postings",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def list_job_posting_entities(
    payload: JobPostingEntitiesListRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin job posting entity queries", 400)

    client = get_supabase_client()
    query = client.table("job_posting_entities").select("*").eq("org_id", org_id)

    if not is_super_admin and auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        if payload.company_id and payload.company_id != auth.company_id:
            return error_response("Forbidden company access", 403)
        query = query.eq("company_id", auth.company_id)
    elif payload.company_id:
        query = query.eq("company_id", payload.company_id)

    company_domain = _normalize_text(payload.company_domain)
    if company_domain:
        query = query.eq("company_domain", company_domain.lower())

    company_name = _normalize_text(payload.company_name)
    if company_name:
        query = query.ilike("company_name", f"%{company_name}%")

    job_title = _normalize_text(payload.job_title)
    if job_title:
        query = query.ilike("job_title", f"%{job_title}%")

    seniority = _normalize_text(payload.seniority)
    if seniority:
        query = query.eq("seniority", seniority)

    country_code = _normalize_text(payload.country_code)
    if country_code:
        query = query.eq("country_code", country_code)

    if payload.remote is not None:
        query = query.eq("remote", payload.remote)

    posting_status = _normalize_text(payload.posting_status)
    if posting_status:
        query = query.eq("posting_status", posting_status)

    start = (payload.page - 1) * payload.per_page
    end = start + payload.per_page - 1
    result = query.order("created_at", desc=True).range(start, end).execute()

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
    if entity_type not in {"company", "person", "job"}:
        return error_response("entity_type must be 'company', 'person', or 'job'", 400)

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


@router.post(
    "/snapshots",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def get_entity_snapshots(
    payload: EntitySnapshotsRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    entity_type = _normalize_text(payload.entity_type)
    if entity_type not in {"company", "person", "job"}:
        return error_response("entity_type must be 'company', 'person', or 'job'", 400)

    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin snapshots queries", 400)

    client = get_supabase_client()
    result = (
        client.table("entity_snapshots")
        .select("*")
        .eq("org_id", org_id)
        .eq("entity_type", entity_type)
        .eq("entity_id", payload.entity_id)
        .order("captured_at", desc=True)
        .limit(payload.limit)
        .execute()
    )

    return DataEnvelope(
        data={
            "entity_type": entity_type,
            "entity_id": payload.entity_id,
            "items": result.data,
            "returned": len(result.data),
        }
    )


@entity_relationships_router.post(
    "/entity-relationships/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_entity_relationship_rows(
    payload: EntityRelationshipQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin entity relationship queries", 400)

    results = query_entity_relationships(
        org_id=org_id,
        source_identifier=payload.source_identifier,
        target_identifier=payload.target_identifier,
        relationship=payload.relationship,
        source_entity_type=payload.source_entity_type,
        target_entity_type=payload.target_entity_type,
        include_invalidated=payload.include_invalidated,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@entity_relationships_router.post(
    "/icp-job-titles/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_icp_job_titles_rows(
    payload: IcpJobTitlesQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin ICP job title queries", 400)

    results = query_icp_job_titles(
        org_id=org_id,
        company_domain=payload.company_domain,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@entity_relationships_router.post(
    "/company-intel-briefings/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_company_intel_briefings_rows(
    payload: CompanyIntelBriefingsQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin company intel briefing queries", 400)

    results = query_company_intel_briefings(
        org_id=org_id,
        company_domain=payload.company_domain,
        client_company_name=payload.client_company_name,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@entity_relationships_router.post(
    "/person-intel-briefings/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_person_intel_briefings_rows(
    payload: PersonIntelBriefingsQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    is_super_admin = isinstance(auth, SuperAdminContext)
    org_id = payload.org_id if is_super_admin and payload.org_id else auth.org_id
    if is_super_admin and not org_id:
        return error_response("org_id is required for super-admin person intel briefing queries", 400)

    results = query_person_intel_briefings(
        org_id=org_id,
        person_linkedin_url=payload.person_linkedin_url,
        person_current_company_name=payload.person_current_company_name,
        client_company_name=payload.client_company_name,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)
