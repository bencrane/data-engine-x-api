from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth import SuperAdminContext, get_current_super_admin
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


class SuperAdminConfigCreateRequest(BaseModel):
    org_id: str
    company_id: str
    blueprint_id: str
    name: str
    description: str | None = None
    input_payload: dict[str, Any]
    is_active: bool = True
    actor_user_id: str | None = None


class SuperAdminConfigListRequest(BaseModel):
    org_id: str
    company_id: str | None = None
    blueprint_id: str | None = None
    is_active: bool | None = None


class SuperAdminConfigGetRequest(BaseModel):
    org_id: str
    id: str


class SuperAdminConfigUpdateRequest(BaseModel):
    org_id: str
    id: str
    company_id: str | None = None
    blueprint_id: str | None = None
    name: str | None = None
    description: str | None = None
    input_payload: dict[str, Any] | None = None
    is_active: bool | None = None
    actor_user_id: str | None = None


class SuperAdminScheduleCreateRequest(BaseModel):
    org_id: str
    company_id: str
    config_id: str
    name: str
    timezone: str = "UTC"
    cadence_minutes: int
    next_run_at: str
    is_active: bool = True
    actor_user_id: str | None = None


class SuperAdminScheduleListRequest(BaseModel):
    org_id: str
    company_id: str | None = None
    config_id: str | None = None
    is_active: bool | None = None


class SuperAdminScheduleGetRequest(BaseModel):
    org_id: str
    id: str


class SuperAdminScheduleUpdateRequest(BaseModel):
    org_id: str
    id: str
    config_id: str | None = None
    name: str | None = None
    timezone: str | None = None
    cadence_minutes: int | None = None
    next_run_at: str | None = None
    is_active: bool | None = None
    actor_user_id: str | None = None


@router.post("/configs/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_config(
    payload: SuperAdminConfigCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    try:
        result = create_company_blueprint_config(
            org_id=payload.org_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            name=payload.name,
            description=payload.description,
            input_payload=payload.input_payload,
            is_active=payload.is_active,
            actor_user_id=payload.actor_user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/configs/list", response_model=DataEnvelope)
async def super_admin_list_configs(
    payload: SuperAdminConfigListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    return DataEnvelope(
        data=list_company_blueprint_configs(
            org_id=payload.org_id,
            company_id=payload.company_id,
            blueprint_id=payload.blueprint_id,
            is_active=payload.is_active,
        )
    )


@router.post("/configs/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_config(
    payload: SuperAdminConfigGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    result = get_company_blueprint_config(org_id=payload.org_id, config_id=payload.id)
    if result is None:
        return error_response("Config not found", 404)
    return DataEnvelope(data=result)


@router.post("/configs/update", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_update_config(
    payload: SuperAdminConfigUpdateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    try:
        updated = update_company_blueprint_config(
            org_id=payload.org_id,
            config_id=payload.id,
            actor_user_id=payload.actor_user_id,
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


@router.post("/schedules/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_schedule(
    payload: SuperAdminScheduleCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    try:
        result = create_company_blueprint_schedule(
            org_id=payload.org_id,
            company_id=payload.company_id,
            config_id=payload.config_id,
            name=payload.name,
            timezone_name=payload.timezone,
            cadence_minutes=payload.cadence_minutes,
            next_run_at=payload.next_run_at,
            is_active=payload.is_active,
            actor_user_id=payload.actor_user_id,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    return DataEnvelope(data=result)


@router.post("/schedules/list", response_model=DataEnvelope)
async def super_admin_list_schedules(
    payload: SuperAdminScheduleListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    return DataEnvelope(
        data=list_company_blueprint_schedules(
            org_id=payload.org_id,
            company_id=payload.company_id,
            config_id=payload.config_id,
            is_active=payload.is_active,
        )
    )


@router.post("/schedules/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_schedule(
    payload: SuperAdminScheduleGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    result = get_company_blueprint_schedule(org_id=payload.org_id, schedule_id=payload.id)
    if result is None:
        return error_response("Schedule not found", 404)
    return DataEnvelope(data=result)


@router.post("/schedules/update", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_update_schedule(
    payload: SuperAdminScheduleUpdateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    try:
        result = update_company_blueprint_schedule(
            org_id=payload.org_id,
            schedule_id=payload.id,
            actor_user_id=payload.actor_user_id,
            config_id=payload.config_id,
            name=payload.name,
            timezone_name=payload.timezone,
            cadence_minutes=payload.cadence_minutes,
            next_run_at=payload.next_run_at,
            is_active=payload.is_active,
        )
    except ValueError as exc:
        return error_response(str(exc), 400)
    if result is None:
        return error_response("Schedule not found", 404)
    return DataEnvelope(data=result)
