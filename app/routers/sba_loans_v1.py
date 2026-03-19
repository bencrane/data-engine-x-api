# app/routers/sba_loans_v1.py — SBA loan query endpoints

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

class SbaLoanSearchRequest(BaseModel):
    state: str | None = None
    min_loan_amount: float | None = None
    max_loan_amount: float | None = None
    approval_date_from: str | None = None
    approval_date_to: str | None = None
    borrower_name: str | None = None
    naics_code: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SbaLoanStatsRequest(BaseModel):
    state: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/search",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def search_sba_loans_endpoint(
    payload: SbaLoanSearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.sba_loans_query import search_sba_loans

    filters: dict[str, Any] = {}
    for key in ("state", "min_loan_amount", "max_loan_amount", "approval_date_from", "approval_date_to", "borrower_name", "naics_code"):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    result = search_sba_loans(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.post(
    "/stats",
    response_model=DataEnvelope,
)
async def get_sba_loan_stats_endpoint(
    payload: SbaLoanStatsRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.sba_loans_query import get_sba_loan_stats

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state
    result = get_sba_loan_stats(filters=filters)
    return DataEnvelope(data=result)
