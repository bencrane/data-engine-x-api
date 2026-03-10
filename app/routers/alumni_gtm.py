from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.models.alumni_gtm import AlumniGtmLeadsResponse
from app.services.alumni_gtm_service import get_alumni_gtm_leads

router = APIRouter()
_security = HTTPBearer(auto_error=False)


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


@router.get(
    "/leads",
    response_model=AlumniGtmLeadsResponse,
)
async def list_alumni_gtm_leads(
    origin_company_domain: str = Query(..., min_length=1, description="Client domain, e.g. nostra.ai"),
    gtm_fit: bool | None = Query(default=None, description="Optional GTM fit filter"),
    prior_company_domain: str | None = Query(default=None, description="Optional prior company domain"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    _auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
) -> AlumniGtmLeadsResponse:
    return get_alumni_gtm_leads(
        origin_company_domain=origin_company_domain,
        gtm_fit=gtm_fit,
        prior_company_domain=prior_company_domain,
        limit=limit,
        offset=offset,
    )
