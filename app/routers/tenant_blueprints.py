# app/routers/tenant_blueprints.py — Tenant blueprint CRUD endpoints

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.routers._responses import DataEnvelope, ErrorEnvelope, error_response
from app.routers.execute_v1 import SUPPORTED_OPERATION_IDS

router = APIRouter()


class BlueprintListRequest(BaseModel):
    pass


class BlueprintGetRequest(BaseModel):
    id: str


class BlueprintStepInput(BaseModel):
    position: int = Field(gt=0)
    operation_id: str
    step_config: dict | None = None
    fan_out: bool = False
    is_enabled: bool = True


class BlueprintCreateRequest(BaseModel):
    name: str
    description: str | None = None
    steps: list[BlueprintStepInput]


class BlueprintUpdateRequest(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    steps: list[BlueprintStepInput] | None = None


def _validate_blueprint_steps(steps: list[BlueprintStepInput]) -> str | None:
    positions = [step.position for step in steps]
    if len(positions) != len(set(positions)):
        return "Blueprint step positions must be unique"
    unsupported = [
        step.operation_id
        for step in steps
        if step.operation_id not in SUPPORTED_OPERATION_IDS
    ]
    if unsupported:
        return f"Unsupported operation_id values: {', '.join(sorted(set(unsupported)))}"
    return None


@router.post("/list", response_model=DataEnvelope)
async def list_blueprints(
    _: BlueprintListRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("*")
        .eq("org_id", auth.org_id)
        .order("created_at", desc=True)
        .execute()
    )
    return DataEnvelope(data=result.data)


@router.post("/get", response_model=DataEnvelope, responses={404: {"model": ErrorEnvelope}})
async def get_blueprint(
    payload: BlueprintGetRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*)")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return error_response("Blueprint not found", 404)
    return DataEnvelope(data=result.data[0])


@router.post("/create", response_model=DataEnvelope, responses={400: {"model": ErrorEnvelope}})
async def create_blueprint(
    payload: BlueprintCreateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    validation_error = _validate_blueprint_steps(payload.steps)
    if validation_error:
        return error_response(validation_error, 400)

    client = get_supabase_client()
    blueprint_result = client.table("blueprints").insert(
        {
            "org_id": auth.org_id,
            "name": payload.name,
            "description": payload.description,
            "created_by_user_id": auth.user_id,
        }
    ).execute()
    blueprint = blueprint_result.data[0]

    if payload.steps:
        step_rows = [
            {
                "blueprint_id": blueprint["id"],
                "position": step.position,
                "operation_id": step.operation_id,
                "step_config": step.step_config,
                "fan_out": step.fan_out,
                "is_enabled": step.is_enabled,
                "config": step.step_config or {},
            }
            for step in payload.steps
        ]
        client.table("blueprint_steps").insert(step_rows).execute()

    full_result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*)")
        .eq("id", blueprint["id"])
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    return DataEnvelope(data=full_result.data)


@router.post(
    "/update",
    response_model=DataEnvelope,
    responses={400: {"model": ErrorEnvelope}, 404: {"model": ErrorEnvelope}},
)
async def update_blueprint(
    payload: BlueprintUpdateRequest,
    auth: AuthContext = Depends(get_current_auth),
):
    if payload.steps is not None:
        validation_error = _validate_blueprint_steps(payload.steps)
        if validation_error:
            return error_response(validation_error, 400)

    client = get_supabase_client()
    exists = (
        client.table("blueprints")
        .select("id")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .limit(1)
        .execute()
    )
    if not exists.data:
        return error_response("Blueprint not found", 404)

    update_data = payload.model_dump(exclude={"id", "steps"}, exclude_none=True)
    if update_data:
        client.table("blueprints").update(update_data).eq("id", payload.id).eq(
            "org_id", auth.org_id
        ).execute()

    if payload.steps is not None:
        client.table("blueprint_steps").delete().eq("blueprint_id", payload.id).execute()
        if payload.steps:
            step_rows = [
                {
                    "blueprint_id": payload.id,
                    "position": step.position,
                    "operation_id": step.operation_id,
                    "step_config": step.step_config,
                    "fan_out": step.fan_out,
                    "is_enabled": step.is_enabled,
                    "config": step.step_config or {},
                }
                for step in payload.steps
            ]
            client.table("blueprint_steps").insert(step_rows).execute()

    result = (
        client.table("blueprints")
        .select("*, blueprint_steps(*)")
        .eq("id", payload.id)
        .eq("org_id", auth.org_id)
        .single()
        .execute()
    )
    return DataEnvelope(data=result.data)
