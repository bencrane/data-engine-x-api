# app/routers/super_admin_api.py — Super admin CRUD endpoints

from datetime import datetime, timezone
import secrets
from typing import Any, Literal

import bcrypt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.auth import SuperAdminContext, get_current_super_admin
from app.auth.tokens import hash_api_token
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response

router = APIRouter()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_company_or_none(company_id: str | None) -> dict[str, Any] | None:
    if not company_id:
        return None
    client = get_supabase_client()
    res = client.table("companies").select("id, org_id").eq("id", company_id).limit(1).execute()
    return res.data[0] if res.data else None


def _org_exists(org_id: str) -> bool:
    client = get_supabase_client()
    res = client.table("orgs").select("id").eq("id", org_id).limit(1).execute()
    return bool(res.data)


class OrgCreateRequest(BaseModel):
    name: str
    slug: str


class OrgListRequest(BaseModel):
    pass


class OrgGetRequest(BaseModel):
    id: str


class OrgUpdateRequest(BaseModel):
    id: str
    name: str | None = None
    slug: str | None = None


class CompanyCreateRequest(BaseModel):
    org_id: str
    name: str
    domain: str | None = None
    external_ref: str | None = None


class CompanyListRequest(BaseModel):
    org_id: str | None = None


class CompanyGetRequest(BaseModel):
    id: str


class UserCreateRequest(BaseModel):
    org_id: str
    email: str
    password: str
    role: Literal["org_admin", "company_admin", "member"]
    company_id: str | None = None
    full_name: str | None = None


class UserListRequest(BaseModel):
    org_id: str | None = None
    company_id: str | None = None


class UserGetRequest(BaseModel):
    id: str


class UserDeactivateRequest(BaseModel):
    id: str


class StepRegisterRequest(BaseModel):
    slug: str
    task_id: str = "execute-step"
    name: str
    step_type: Literal["clean", "enrich", "analyze", "extract", "transform"]
    default_config: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    description: str | None = None
    url: str
    method: str = "POST"
    auth_type: Literal["bearer_token", "api_key_header", "none"] | None = None
    auth_config: dict[str, Any] | None = None
    payload_template: dict[str, Any] | list[Any] | None = None
    response_mapping: dict[str, Any] | list[Any] | str | None = None
    timeout_ms: int = 30000
    retry_config: dict[str, Any] | None = None


class StepListRequest(BaseModel):
    step_type: Literal["clean", "enrich", "analyze", "extract", "transform"] | None = None
    is_active: bool | None = None


class StepGetRequest(BaseModel):
    id: str | None = None
    slug: str | None = None


class StepUpdateRequest(BaseModel):
    id: str
    slug: str | None = None
    task_id: str | None = None
    name: str | None = None
    step_type: Literal["clean", "enrich", "analyze", "extract", "transform"] | None = None
    default_config: dict[str, Any] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    description: str | None = None
    is_active: bool | None = None
    url: str | None = None
    method: str | None = None
    auth_type: Literal["bearer_token", "api_key_header", "none"] | None = None
    auth_config: dict[str, Any] | None = None
    payload_template: dict[str, Any] | list[Any] | None = None
    response_mapping: dict[str, Any] | list[Any] | str | None = None
    timeout_ms: int | None = None
    retry_config: dict[str, Any] | None = None


class StepDeactivateRequest(BaseModel):
    id: str


class BlueprintStepInput(BaseModel):
    step_id: str | None = None
    operation_id: str | None = None
    position: int
    config: dict[str, Any] | None = None
    step_config: dict[str, Any] | None = None


class BlueprintCreateRequest(BaseModel):
    org_id: str
    name: str
    description: str | None = None
    steps: list[BlueprintStepInput]


class BlueprintListRequest(BaseModel):
    org_id: str | None = None


class BlueprintGetRequest(BaseModel):
    id: str


class BlueprintUpdateRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    steps: list[BlueprintStepInput] | None = None


class ApiTokenCreateRequest(BaseModel):
    user_id: str
    name: str
    expires_at: str | None = None


class ApiTokenListRequest(BaseModel):
    org_id: str | None = None
    user_id: str | None = None


class ApiTokenRevokeRequest(BaseModel):
    id: str


class ApiTokenCreateResponse(BaseModel):
    id: str
    token: str
    name: str
    org_id: str
    company_id: str | None = None
    role: str
    user_id: str
    created_at: str


class ApiTokenSafeRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    name: str
    org_id: str
    company_id: str | None = None
    role: str
    user_id: str | None = None
    expires_at: str | None = None
    revoked_at: str | None = None
    created_at: str
    last_used_at: str | None = None


@router.post("/orgs/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_org(
    payload: OrgCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = client.table("orgs").insert(payload.model_dump()).execute()
    return DataEnvelope(data=result.data[0])


@router.post("/orgs/list", response_model=DataEnvelope)
async def super_admin_list_orgs(
    _: OrgListRequest,
    __: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = client.table("orgs").select("*").order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/orgs/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_org(
    payload: OrgGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = client.table("orgs").select("*").eq("id", payload.id).limit(1).execute()
    if not result.data:
        return error_response("Org not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/orgs/update", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_update_org(
    payload: OrgUpdateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    update = payload.model_dump(exclude={"id"}, exclude_none=True)
    if not update:
        return error_response("No fields provided for update", 400)
    client = get_supabase_client()
    result = client.table("orgs").update(update).eq("id", payload.id).execute()
    if not result.data:
        return error_response("Org not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/companies/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_company(
    payload: CompanyCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    if not _org_exists(payload.org_id):
        return error_response("org_id does not exist", 400)
    client = get_supabase_client()
    result = client.table("companies").insert(payload.model_dump()).execute()
    return DataEnvelope(data=result.data[0])


@router.post("/companies/list", response_model=DataEnvelope)
async def super_admin_list_companies(
    payload: CompanyListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("companies").select("*")
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/companies/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_company(
    payload: CompanyGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = client.table("companies").select("*").eq("id", payload.id).limit(1).execute()
    if not result.data:
        return error_response("Company not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/users/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_user(
    payload: UserCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    if not _org_exists(payload.org_id):
        return error_response("org_id does not exist", 400)
    company = _get_company_or_none(payload.company_id)
    if payload.company_id and (company is None or company["org_id"] != payload.org_id):
        return error_response("company_id does not belong to org_id", 400)

    password_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    create_data = payload.model_dump(exclude={"password"})
    create_data["email"] = create_data["email"].strip().lower()
    create_data["password_hash"] = password_hash

    client = get_supabase_client()
    result = client.table("users").insert(create_data).execute()
    user = result.data[0]
    user.pop("password_hash", None)
    return DataEnvelope(data=user)


@router.post("/users/list", response_model=DataEnvelope)
async def super_admin_list_users(
    payload: UserListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("users").select("id, org_id, company_id, email, full_name, role, is_active, created_at, updated_at")
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    if payload.company_id:
        query = query.eq("company_id", payload.company_id)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/users/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_user(
    payload: UserGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = (
        client.table("users")
        .select("id, org_id, company_id, email, full_name, role, is_active, created_at, updated_at")
        .eq("id", payload.id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("User not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/users/deactivate", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_deactivate_user(
    payload: UserDeactivateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = (
        client.table("users")
        .update({"is_active": False})
        .eq("id", payload.id)
        .execute()
    )
    if not result.data:
        return error_response("User not found", 404)
    data = result.data[0]
    data.pop("password_hash", None)
    return DataEnvelope(data=data)


@router.post("/steps/register", response_model=DataEnvelope)
async def super_admin_register_step(
    payload: StepRegisterRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    create_data = payload.model_dump()
    create_data["default_config"] = create_data.get("default_config") or {}
    create_data["auth_config"] = create_data.get("auth_config") or {}
    create_data["retry_config"] = create_data.get("retry_config") or {
        "max_attempts": 3,
        "backoff_factor": 2,
    }
    result = client.table("steps").insert(create_data).execute()
    return DataEnvelope(data=result.data[0])


@router.post("/steps/list", response_model=DataEnvelope)
async def super_admin_list_steps(
    payload: StepListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("steps").select("*")
    if payload.step_type:
        query = query.eq("step_type", payload.step_type)
    if payload.is_active is not None:
        query = query.eq("is_active", payload.is_active)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/steps/get", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_get_step(
    payload: StepGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    if not payload.id and not payload.slug:
        return error_response("Provide either id or slug", 400)
    client = get_supabase_client()
    query = client.table("steps").select("*")
    if payload.id:
        query = query.eq("id", payload.id)
    else:
        query = query.eq("slug", payload.slug)
    result = query.limit(1).execute()
    if not result.data:
        return error_response("Step not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/steps/update", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_update_step(
    payload: StepUpdateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    update_data = payload.model_dump(exclude={"id"}, exclude_none=True)
    if not update_data:
        return error_response("No fields provided for update", 400)
    client = get_supabase_client()
    result = client.table("steps").update(update_data).eq("id", payload.id).execute()
    if not result.data:
        return error_response("Step not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/steps/deactivate", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_deactivate_step(
    payload: StepDeactivateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = client.table("steps").update({"is_active": False}).eq("id", payload.id).execute()
    if not result.data:
        return error_response("Step not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/blueprints/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def super_admin_create_blueprint(
    payload: BlueprintCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    if not _org_exists(payload.org_id):
        return error_response("org_id does not exist", 400)

    positions = [step.position for step in payload.steps]
    if len(positions) != len(set(positions)):
        return error_response("Blueprint step positions must be unique", 400)

    client = get_supabase_client()
    blueprint_result = client.table("blueprints").insert(
        {
            "org_id": payload.org_id,
            "name": payload.name,
            "description": payload.description,
        }
    ).execute()
    blueprint = blueprint_result.data[0]

    if payload.steps:
        step_rows = []
        for step in payload.steps:
            row: dict[str, Any] = {
                "blueprint_id": blueprint["id"],
                "position": step.position,
            }
            if step.operation_id:
                row["operation_id"] = step.operation_id
                row["step_config"] = step.step_config or step.config or {}
            if step.step_id:
                row["step_id"] = step.step_id
                row["config"] = step.config or {}
            step_rows.append(row)
        client.table("blueprint_steps").insert(step_rows).execute()

    details = (
        client.table("blueprints")
        .select("*, blueprint_steps(*)")
        .eq("id", blueprint["id"])
        .single()
        .execute()
    )
    return DataEnvelope(data=details.data)


@router.post("/blueprints/list", response_model=DataEnvelope)
async def super_admin_list_blueprints(
    payload: BlueprintListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("blueprints").select("*")
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    result = query.order("created_at", desc=True).execute()
    return DataEnvelope(data=result.data)


@router.post("/blueprints/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_get_blueprint(
    payload: BlueprintGetRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*, steps(*))")
        .eq("id", payload.id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Blueprint not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/blueprints/update", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_update_blueprint(
    payload: BlueprintUpdateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    update_data = payload.model_dump(exclude={"id", "steps"}, exclude_none=True)
    if update_data:
        updated = client.table("blueprints").update(update_data).eq("id", payload.id).execute()
        if not updated.data:
            return error_response("Blueprint not found", 404)
    else:
        exists = client.table("blueprints").select("id").eq("id", payload.id).limit(1).execute()
        if not exists.data:
            return error_response("Blueprint not found", 404)

    if payload.steps is not None:
        positions = [step.position for step in payload.steps]
        if len(positions) != len(set(positions)):
            return error_response("Blueprint step positions must be unique", 400)
        client.table("blueprint_steps").delete().eq("blueprint_id", payload.id).execute()
        if payload.steps:
            step_rows = []
            for step in payload.steps:
                row: dict[str, Any] = {
                    "blueprint_id": payload.id,
                    "position": step.position,
                }
                if step.operation_id:
                    row["operation_id"] = step.operation_id
                    row["step_config"] = step.step_config or step.config or {}
                if step.step_id:
                    row["step_id"] = step.step_id
                    row["config"] = step.config or {}
                step_rows.append(row)
            client.table("blueprint_steps").insert(step_rows).execute()

    result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*, steps(*))")
        .eq("id", payload.id)
        .single()
        .execute()
    )
    return DataEnvelope(data=result.data)


@router.post("/api-tokens/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}})
async def super_admin_create_api_token(
    payload: ApiTokenCreateRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    user_result = (
        client.table("users")
        .select("id, org_id, company_id, role, is_active")
        .eq("id", payload.user_id)
        .limit(1)
        .execute()
    )
    if not user_result.data:
        return error_response("User not found", 404)
    user = user_result.data[0]
    if not user.get("is_active"):
        return error_response("User is inactive", 400)

    raw_token = secrets.token_urlsafe(40)
    token_hash = hash_api_token(raw_token)

    insert_result = client.table("api_tokens").insert(
        {
            "org_id": user["org_id"],
            "company_id": user.get("company_id"),
            "user_id": user["id"],
            "name": payload.name,
            "token_hash": token_hash,
            "role": user["role"],
            "expires_at": payload.expires_at,
        }
    ).execute()
    created = insert_result.data[0]
    response_payload = ApiTokenCreateResponse(
        id=created["id"],
        token=raw_token,
        name=created["name"],
        org_id=created["org_id"],
        company_id=created.get("company_id"),
        role=created["role"],
        user_id=created["user_id"],
        created_at=created["created_at"],
    )
    return DataEnvelope(data=response_payload.model_dump())


@router.post("/api-tokens/list", response_model=DataEnvelope)
async def super_admin_list_api_tokens(
    payload: ApiTokenListRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    query = client.table("api_tokens").select(
        "id, name, org_id, company_id, user_id, role, expires_at, revoked_at, created_at, last_used_at"
    )
    if payload.org_id:
        query = query.eq("org_id", payload.org_id)
    if payload.user_id:
        query = query.eq("user_id", payload.user_id)
    result = query.order("created_at", desc=True).execute()
    safe_records = [ApiTokenSafeRecord(**row).model_dump() for row in result.data]
    return DataEnvelope(data=safe_records)


@router.post("/api-tokens/revoke", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def super_admin_revoke_api_token(
    payload: ApiTokenRevokeRequest,
    _: SuperAdminContext = Depends(get_current_super_admin),
):
    client = get_supabase_client()
    result = (
        client.table("api_tokens")
        .update({"revoked_at": _iso_now()})
        .eq("id", payload.id)
        .execute()
    )
    if not result.data:
        return error_response("API token not found", 404)
    row = result.data[0]
    safe = {
        "id": row["id"],
        "name": row["name"],
        "org_id": row["org_id"],
        "company_id": row.get("company_id"),
        "user_id": row.get("user_id"),
        "role": row["role"],
        "expires_at": row.get("expires_at"),
        "revoked_at": row.get("revoked_at"),
        "created_at": row["created_at"],
        "last_used_at": row.get("last_used_at"),
    }
    return DataEnvelope(data=safe)
