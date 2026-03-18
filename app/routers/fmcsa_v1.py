# app/routers/fmcsa_v1.py — FMCSA carrier query endpoints

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.auth import AuthContext
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.auth import get_current_auth
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.fmcsa_carrier_query import query_fmcsa_carriers
from app.services.fmcsa_consolidated_analytics import run_fmcsa_analytics

fmcsa_router = APIRouter()
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


class FmcsaCarrierQueryRequest(BaseModel):
    state: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    carrier_operation: str | None = None
    authorized_for_hire: bool | None = None
    private_only: bool | None = None
    exempt_for_hire: bool | None = None
    private_property: bool | None = None
    hazmat_flag: bool | None = None
    passenger_carrier_flag: bool | None = None
    mcs150_date_from: str | None = None
    mcs150_date_to: str | None = None
    legal_name_contains: str | None = None
    dot_number: str | None = None
    min_drivers: int | None = None
    max_drivers: int | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class FmcsaSafetyRiskQueryRequest(BaseModel):
    state: str | None = None
    min_power_units: int | None = None
    min_unsafe_driving_percentile: int | None = None
    min_hos_percentile: int | None = None
    min_vehicle_maintenance_percentile: int | None = None
    min_driver_fitness_percentile: int | None = None
    min_controlled_substances_percentile: int | None = None
    has_alert_unsafe_driving: bool | None = None
    has_alert_hos: bool | None = None
    has_alert_vehicle_maintenance: bool | None = None
    has_alert_driver_fitness: bool | None = None
    has_alert_controlled_substances: bool | None = None
    min_crash_count_12mo: int | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class FmcsaCarrierExportRequest(BaseModel):
    # Census filters
    state: str | None = None
    min_power_units: int | None = None
    max_power_units: int | None = None
    carrier_operation: str | None = None
    authorized_for_hire: bool | None = None
    private_only: bool | None = None
    exempt_for_hire: bool | None = None
    private_property: bool | None = None
    hazmat_flag: bool | None = None
    passenger_carrier_flag: bool | None = None
    mcs150_date_from: str | None = None
    mcs150_date_to: str | None = None
    legal_name_contains: str | None = None
    dot_number: str | None = None
    min_drivers: int | None = None
    max_drivers: int | None = None
    # Safety filters
    min_unsafe_driving_percentile: int | None = None
    min_hours_of_service_percentile: int | None = None
    min_vehicle_maintenance_percentile: int | None = None
    has_alert_unsafe_driving: bool | None = None
    has_alert_vehicle_maintenance: bool | None = None
    has_alert_driver_fitness: bool | None = None


class FmcsaSignalQueryRequest(BaseModel):
    signal_type: str | None = None
    signal_types: list[str] | None = None
    severity: str | None = None
    min_severity: str | None = None
    dot_number: str | None = None
    state: str | None = None
    feed_date: str | None = None
    feed_date_from: str | None = None
    feed_date_to: str | None = None
    min_power_units: int | None = None
    legal_name_contains: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class FmcsaCrashQueryRequest(BaseModel):
    dot_number: str | None = None
    state: str | None = None
    report_date_from: str | None = None
    report_date_to: str | None = None
    min_fatalities: int | None = None
    min_injuries: int | None = None
    hazmat_released: bool | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


@fmcsa_router.post(
    "/fmcsa-carriers/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_fmcsa_carriers_endpoint(
    payload: FmcsaCarrierQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    filters: dict[str, Any] = {}
    for key in (
        "state", "min_power_units", "max_power_units", "carrier_operation",
        "authorized_for_hire", "private_only", "exempt_for_hire", "private_property",
        "hazmat_flag", "passenger_carrier_flag", "mcs150_date_from", "mcs150_date_to",
        "legal_name_contains", "dot_number", "min_drivers", "max_drivers",
    ):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    results = query_fmcsa_carriers(
        filters=filters,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@fmcsa_router.post(
    "/fmcsa-carriers/stats",
    response_model=DataEnvelope,
)
async def fmcsa_carrier_stats_endpoint(
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_carrier_stats import get_fmcsa_carrier_stats

    stats = get_fmcsa_carrier_stats()
    return DataEnvelope(data=stats)


@fmcsa_router.post(
    "/fmcsa-carriers/safety-risk",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_fmcsa_safety_risk_endpoint(
    payload: FmcsaSafetyRiskQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_safety_risk import query_fmcsa_safety_risk

    filters: dict[str, Any] = {}
    for key in (
        "state", "min_power_units",
        "min_unsafe_driving_percentile", "min_hos_percentile",
        "min_vehicle_maintenance_percentile", "min_driver_fitness_percentile",
        "min_controlled_substances_percentile",
        "has_alert_unsafe_driving", "has_alert_hos",
        "has_alert_vehicle_maintenance", "has_alert_driver_fitness",
        "has_alert_controlled_substances", "min_crash_count_12mo",
    ):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    results = query_fmcsa_safety_risk(
        filters=filters,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@fmcsa_router.post(
    "/fmcsa-carriers/export",
)
async def fmcsa_carriers_export_endpoint(
    payload: FmcsaCarrierExportRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_carrier_export import stream_fmcsa_carriers_csv

    filters: dict[str, Any] = {}
    for key in (
        # Census filters
        "state", "min_power_units", "max_power_units", "carrier_operation",
        "authorized_for_hire", "private_only", "exempt_for_hire", "private_property",
        "hazmat_flag", "passenger_carrier_flag", "mcs150_date_from", "mcs150_date_to",
        "legal_name_contains", "dot_number", "min_drivers", "max_drivers",
        # Safety filters
        "min_unsafe_driving_percentile", "min_hours_of_service_percentile",
        "min_vehicle_maintenance_percentile",
        "has_alert_unsafe_driving", "has_alert_vehicle_maintenance",
        "has_alert_driver_fitness",
    ):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    try:
        gen = stream_fmcsa_carriers_csv(filters=filters, max_rows=100_000)
        first_line = next(gen)

        def csv_with_first():
            yield first_line
            yield from gen

        return StreamingResponse(
            csv_with_first(),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=fmcsa_carriers_export.csv"},
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@fmcsa_router.post(
    "/fmcsa-crashes/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_fmcsa_crashes_endpoint(
    payload: FmcsaCrashQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_crash_query import query_fmcsa_crashes

    filters: dict[str, Any] = {}
    for key in (
        "dot_number", "state", "report_date_from", "report_date_to",
        "min_fatalities", "min_injuries", "hazmat_released",
    ):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    results = query_fmcsa_crashes(
        filters=filters,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@fmcsa_router.get(
    "/fmcsa-carriers/{dot_number}",
    response_model=DataEnvelope,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_fmcsa_carrier_detail_endpoint(
    dot_number: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_carrier_detail import get_fmcsa_carrier_detail

    result = get_fmcsa_carrier_detail(dot_number=dot_number)
    if result is None:
        raise HTTPException(status_code=404, detail=f"DOT number {dot_number} not found")
    return DataEnvelope(data=result)


@fmcsa_router.post(
    "/fmcsa-signals/query",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def query_fmcsa_signals_endpoint(
    payload: FmcsaSignalQueryRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    from app.services.fmcsa_signal_query import query_fmcsa_signals

    filters: dict[str, Any] = {}
    for key in (
        "signal_type", "signal_types", "severity", "min_severity",
        "dot_number", "state", "feed_date", "feed_date_from", "feed_date_to",
        "min_power_units", "legal_name_contains",
    ):
        value = getattr(payload, key)
        if value is not None:
            filters[key] = value

    results = query_fmcsa_signals(
        filters=filters,
        limit=payload.limit,
        offset=payload.offset,
    )
    return DataEnvelope(data=results)


@fmcsa_router.get(
    "/fmcsa-signals/summary",
    response_model=DataEnvelope,
)
async def fmcsa_signal_summary_endpoint(
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    feed_date: str | None = Query(default=None),
    feed_date_from: str | None = Query(default=None),
    feed_date_to: str | None = Query(default=None),
    state: str | None = Query(default=None),
):
    from app.services.fmcsa_signal_query import get_fmcsa_signal_summary

    filters: dict[str, Any] = {}
    if feed_date is not None:
        filters["feed_date"] = feed_date
    if feed_date_from is not None:
        filters["feed_date_from"] = feed_date_from
    if feed_date_to is not None:
        filters["feed_date_to"] = feed_date_to
    if state is not None:
        filters["state"] = state

    results = get_fmcsa_signal_summary(filters=filters)
    return DataEnvelope(data=results)


@fmcsa_router.get(
    "/fmcsa-carriers/{dot_number}/signals",
    response_model=DataEnvelope,
)
async def get_carrier_signals_endpoint(
    dot_number: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    signal_type: str | None = Query(default=None),
    feed_date_from: str | None = Query(default=None),
    feed_date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    from app.services.fmcsa_signal_query import query_carrier_signals

    filters: dict[str, Any] = {}
    if signal_type is not None:
        filters["signal_type"] = signal_type
    if feed_date_from is not None:
        filters["feed_date_from"] = feed_date_from
    if feed_date_to is not None:
        filters["feed_date_to"] = feed_date_to

    results = query_carrier_signals(
        dot_number=dot_number,
        filters=filters,
        limit=limit,
        offset=offset,
    )
    return DataEnvelope(data=results)


class FmcsaConsolidatedAnalyticsRequest(BaseModel):
    query_type: str
    months: int = Field(default=6, ge=1, le=24)
    date_from: str | None = None
    date_to: str | None = None


@fmcsa_router.post(
    "/fmcsa-carriers/analytics",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}},
)
async def fmcsa_consolidated_analytics(
    payload: FmcsaConsolidatedAnalyticsRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
):
    params: dict[str, Any] = {"months": payload.months}
    if payload.date_from is not None:
        params["date_from"] = payload.date_from
    if payload.date_to is not None:
        params["date_to"] = payload.date_to

    try:
        result = run_fmcsa_analytics(query_type=payload.query_type, params=params)
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)
