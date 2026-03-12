from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import AuthContext, get_current_auth
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.services.company_blueprint_configs import (
    create_company_blueprint_config,
    get_company_blueprint_config,
    list_company_blueprint_configs,
    update_company_blueprint_config,
)
from app.services.company_blueprint_schedules import (
    create_company_blueprint_schedule,
    get_company_blueprint_schedule,
    list_company_blueprint_schedules,
    update_company_blueprint_schedule,
)

router = APIRouter()


def _company_scope_forbidden(auth: AuthContext, company_id: str) -> bool:
    return auth.role in {"company_admin", "member"} and auth.company_id != company_id


class TenantConfigCreateRequest(BaseModel):
    company_id: str
    blueprint_id: str
    name: str
    description: str | None = None
    input_payload: dict[str, Any]
    is_active: bool = True


class TenantConfigListRequest(BaseModel):
    company_id: str | None = None
    blueprint_id: str | None = None
    is_active: bool | None = None


class TenantConfigGetRequest(BaseModel):
    id: str


class TenantConfigUpdateRequest(BaseModel):
    id: str
    company_id: str | None = None
    blueprint_id: str | None = None
    name: str | None = None
    description: str | None = None
    input_payload: dict[str, Any] | None = None
    is_active: bool | None = None


class TenantScheduleCreateRequest(BaseModel):
    company_id: str
    config_id: str
    name: str
    timezone: str = "UTC"
    cadence_minutes: int
    next_run_at: str
    is_active: bool = True


class TenantScheduleListRequest(BaseModel):
    company_id: str | None = None
    config_id: str | None = None
    is_active: bool | None = None


class TenantScheduleGetRequest(BaseModel):
    id: str


class TenantScheduleUpdateRequest(BaseModel):
    id: str
    config_id: str | None = None
    name: str | None = None
    timezone: str | None = None
    cadence_minutes: int | None = None
    next_run_at: str | None = None
    is_active: bool | None = None


@router.post(
    "/configs/create",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def tenant_create_config(
    payload: TenantConfigCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if _company_scope_forbidden(auth, payload.company_id):
        return error_response("Forbidden company access", 403)
    try:
        result = create_company_blueprint_config(
            org_id=auth.org_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            name=payload.name,
            description=payload.description,
            input_payload=payload.input_payload,
            is_active=payload.is_active,
            actor_user_id=auth.user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/configs/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}})
async def tenant_list_configs(
    payload: TenantConfigListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        if payload.company_id and payload.company_id != auth.company_id:
            return error_response("Forbidden company access", 403)
        company_id = auth.company_id
    else:
        company_id = payload.company_id
    results = list_company_blueprint_configs(
        org_id=auth.org_id,
        company_id=company_id,
        blueprint_id=payload.blueprint_id,
        is_active=payload.is_active,
    )
    return DataEnvelope(data=results)


@router.post("/configs/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def tenant_get_config(
    payload: TenantConfigGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    config = get_company_blueprint_config(org_id=auth.org_id, config_id=payload.id)
    if config is None:
        return error_response("Config not found", 404)
    if _company_scope_forbidden(auth, config["company_id"]):
        return error_response("Forbidden company access", 403)
    return DataEnvelope(data=config)


@router.post(
    "/configs/update",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def tenant_update_config(
    payload: TenantConfigUpdateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    existing = get_company_blueprint_config(org_id=auth.org_id, config_id=payload.id)
    if existing is None:
        return error_response("Config not found", 404)
    if _company_scope_forbidden(auth, existing["company_id"]):
        return error_response("Forbidden company access", 403)
    if payload.company_id and _company_scope_forbidden(auth, payload.company_id):
        return error_response("Forbidden company access", 403)

    try:
        updated = update_company_blueprint_config(
            org_id=auth.org_id,
            config_id=payload.id,
            actor_user_id=auth.user_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            name=payload.name,
            description=payload.description,
            input_payload=payload.input_payload,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    if updated is None:
        return error_response("Config not found", 404)
    return DataEnvelope(data=updated)


@router.post(
    "/schedules/create",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
)
async def tenant_create_schedule(
    payload: TenantScheduleCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if _company_scope_forbidden(auth, payload.company_id):
        return error_response("Forbidden company access", 403)
    try:
        result = create_company_blueprint_schedule(
            org_id=auth.org_id,
            company_id=payload.company_id,
            config_id=payload.config_id,
            name=payload.name,
            timezone_name=payload.timezone,
            cadence_minutes=payload.cadence_minutes,
            next_run_at=payload.next_run_at,
            is_active=payload.is_active,
            actor_user_id=auth.user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/schedules/list", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}})
async def tenant_list_schedules(
    payload: TenantScheduleListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if auth.role in {"company_admin", "member"}:
        if not auth.company_id:
            return error_response("Company-scoped user missing company_id", 403)
        if payload.company_id and payload.company_id != auth.company_id:
            return error_response("Forbidden company access", 403)
        company_id = auth.company_id
    else:
        company_id = payload.company_id
    results = list_company_blueprint_schedules(
        org_id=auth.org_id,
        company_id=company_id,
        config_id=payload.config_id,
        is_active=payload.is_active,
    )
    return DataEnvelope(data=results)


@router.post("/schedules/get", response_model=DataEnvelope, responses={403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def tenant_get_schedule(
    payload: TenantScheduleGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    schedule = get_company_blueprint_schedule(org_id=auth.org_id, schedule_id=payload.id)
    if schedule is None:
        return error_response("Schedule not found", 404)
    if _company_scope_forbidden(auth, schedule["company_id"]):
        return error_response("Forbidden company access", 403)
    return DataEnvelope(data=schedule)


@router.post(
    "/schedules/update",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def tenant_update_schedule(
    payload: TenantScheduleUpdateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    existing = get_company_blueprint_schedule(org_id=auth.org_id, schedule_id=payload.id)
    if existing is None:
        return error_response("Schedule not found", 404)
    if _company_scope_forbidden(auth, existing["company_id"]):
        return error_response("Forbidden company access", 403)

    try:
        updated = update_company_blueprint_schedule(
            org_id=auth.org_id,
            schedule_id=payload.id,
            actor_user_id=auth.user_id,
            config_id=payload.config_id,
            name=payload.name,
            timezone_name=payload.timezone,
            cadence_minutes=payload.cadence_minutes,
            next_run_at=payload.next_run_at,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    if updated is None:
        return error_response("Schedule not found", 404)
    return DataEnvelope(data=updated)
