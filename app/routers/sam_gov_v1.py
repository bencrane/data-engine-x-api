# app/routers/sam_gov_v1.py — SAM.gov entity query endpoints

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.routers._responses import DataEnvelope, ErrorEnvelope

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


# ---------------------------------------------------------------------------
# Pydantic request models
# ---------------------------------------------------------------------------

class SamEntitySearchRequest(BaseModel):
    state: str | None = None
    naics_code: str | None = None
    naics_prefix: str | None = None
    registration_status: str | None = None
    entity_name: str | None = None
    uei: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SamEntityStatsRequest(BaseModel):
    state: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/search",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def search_sam_entities_endpoint(
    payload: SamEntitySearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.sam_gov_query import search_sam_entities

    filters: dict[str, Any] = {}
    for key in ("state", "naics_code", "naics_prefix", "registration_status", "entity_name", "uei"):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    result = search_sam_entities(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.get(
    "/{uei}",
    response_model=DataEnvelope,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_sam_entity_detail_endpoint(
    uei: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.sam_gov_query import get_sam_entity_detail

    result = get_sam_entity_detail(uei=uei)
    if result is None:
        raise HTTPException(status_code=404, detail=f"UEI {uei} not found")
    return DataEnvelope(data=result)


@router.post(
    "/stats",
    response_model=DataEnvelope,
)
async def get_sam_entity_stats_endpoint(
    payload: SamEntityStatsRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.sam_gov_query import get_sam_entity_stats

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state
    result = get_sam_entity_stats(filters=filters)
    return DataEnvelope(data=result)
