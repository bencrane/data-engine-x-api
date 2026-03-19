# app/routers/fmcsa_carriers_v1.py — FMCSA carrier MV-backed query endpoints

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
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

class CarrierSearchRequest(BaseModel):
    state: str | None = None
    city: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    max_unsafe_driving: int | None = None
    max_hos: int | None = None
    max_vehicle_maintenance: int | None = None
    max_driver_fitness: int | None = None
    max_controlled_substances: int | None = None
    has_alerts: bool | None = None
    has_crashes: bool | None = None
    has_email: bool | None = None
    has_phone: bool | None = None
    safety_rating_code: str | None = None
    legal_name_contains: str | None = None
    sort_by: str | None = Field(default="fleet_size", pattern="^(fleet_size|state|safety)$")
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class InsuranceCancellationSearchRequest(BaseModel):
    state: str | None = None
    cancel_date_from: str | None = None
    cancel_date_to: str | None = None
    insurance_type: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    safe_only: bool | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class NewAuthoritySearchRequest(BaseModel):
    state: str | None = None
    served_date_from: str | None = None
    served_date_to: str | None = None
    authority_type: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    safe_only: bool | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SafeCarrierConvenienceRequest(BaseModel):
    state: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class SafeMidMarketRequest(BaseModel):
    state: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CarrierStatsRequest(BaseModel):
    state: str | None = None


class CarrierExportRequest(BaseModel):
    state: str | None = None
    city: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    max_unsafe_driving: int | None = None
    max_hos: int | None = None
    max_vehicle_maintenance: int | None = None
    max_driver_fitness: int | None = None
    max_controlled_substances: int | None = None
    has_alerts: bool | None = None
    has_crashes: bool | None = None
    has_email: bool | None = None
    has_phone: bool | None = None
    safety_rating_code: str | None = None
    legal_name_contains: str | None = None


# ---------------------------------------------------------------------------
# Helper to extract filters from Pydantic model
# ---------------------------------------------------------------------------

def _extract_filters(payload: BaseModel, keys: tuple[str, ...]) -> dict[str, Any]:
    filters: dict[str, Any] = {}
    for key in keys:
        value = getattr(payload, key, None)
        if value is not None:
            filters[key] = value
    return filters


_CARRIER_SEARCH_KEYS = (
    "state", "city", "min_power_units", "max_power_units",
    "max_unsafe_driving", "max_hos", "max_vehicle_maintenance",
    "max_driver_fitness", "max_controlled_substances",
    "has_alerts", "has_crashes", "has_email", "has_phone",
    "safety_rating_code", "legal_name_contains", "sort_by",
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/search",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def search_carriers_endpoint(
    payload: CarrierSearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_carriers

    filters = _extract_filters(payload, _CARRIER_SEARCH_KEYS)
    result = search_carriers(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.post(
    "/insurance-cancellations",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def search_insurance_cancellations_endpoint(
    payload: InsuranceCancellationSearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_insurance_cancellations

    filters = _extract_filters(payload, (
        "state", "cancel_date_from", "cancel_date_to", "insurance_type",
        "min_power_units", "max_power_units", "safe_only",
    ))
    result = search_insurance_cancellations(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.post(
    "/new-authority",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def search_new_authority_endpoint(
    payload: NewAuthoritySearchRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_new_authority

    filters = _extract_filters(payload, (
        "state", "served_date_from", "served_date_to", "authority_type",
        "min_power_units", "max_power_units", "safe_only",
    ))
    result = search_new_authority(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.get(
    "/{dot_number}",
    response_model=DataEnvelope,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_carrier_detail_endpoint(
    dot_number: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_detail import get_carrier_detail

    result = get_carrier_detail(dot_number=dot_number)
    if result is None:
        raise HTTPException(status_code=404, detail=f"DOT number {dot_number} not found")
    return DataEnvelope(data=result)


@router.post(
    "/stats",
    response_model=DataEnvelope,
)
async def get_carrier_stats_endpoint(
    payload: CarrierStatsRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_stats import get_carrier_stats

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state
    result = get_carrier_stats(filters=filters)
    return DataEnvelope(data=result)


@router.post(
    "/export",
)
async def export_carriers_endpoint(
    payload: CarrierExportRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_export import stream_carriers_csv

    filters = _extract_filters(payload, (
        "state", "city", "min_power_units", "max_power_units",
        "max_unsafe_driving", "max_hos", "max_vehicle_maintenance",
        "max_driver_fitness", "max_controlled_substances",
        "has_alerts", "has_crashes", "has_email", "has_phone",
        "safety_rating_code", "legal_name_contains",
    ))

    try:
        gen = stream_carriers_csv(filters=filters, max_rows=100_000)
        first_line = next(gen)

        def csv_with_first():
            yield first_line
            yield from gen

        return StreamingResponse(
            csv_with_first(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fmcsa_carriers_mv_export.csv"},
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post(
    "/safe-losing-coverage",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def safe_losing_coverage_endpoint(
    payload: SafeCarrierConvenienceRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_safe_losing_coverage

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state
    if payload.date_from:
        filters["cancel_date_from"] = payload.date_from
    if payload.date_to:
        filters["cancel_date_to"] = payload.date_to
    if payload.min_power_units is not None:
        filters["min_power_units"] = payload.min_power_units
    if payload.max_power_units is not None:
        filters["max_power_units"] = payload.max_power_units

    result = search_safe_losing_coverage(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.post(
    "/safe-new-entrants",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def safe_new_entrants_endpoint(
    payload: SafeCarrierConvenienceRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_safe_new_entrants

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state
    if payload.date_from:
        filters["served_date_from"] = payload.date_from
    if payload.date_to:
        filters["served_date_to"] = payload.date_to
    if payload.min_power_units is not None:
        filters["min_power_units"] = payload.min_power_units
    if payload.max_power_units is not None:
        filters["max_power_units"] = payload.max_power_units

    result = search_safe_new_entrants(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)


@router.post(
    "/safe-mid-market",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def safe_mid_market_endpoint(
    payload: SafeMidMarketRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_mv_query import search_safe_mid_market

    filters: dict[str, Any] = {}
    if payload.state:
        filters["state"] = payload.state

    result = search_safe_mid_market(filters=filters, limit=payload.limit, offset=payload.offset)
    return DataEnvelope(data=result)
