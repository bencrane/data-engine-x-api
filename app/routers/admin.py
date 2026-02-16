# app/routers/admin.py — Admin/super-user endpoints (register steps, manage blueprints)

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.models.blueprint import Blueprint, BlueprintCreate, BlueprintUpdate
from app.models.step import Step, StepCreate, StepUpdate

router = APIRouter()


def require_admin(auth: AuthContext = Depends(get_current_auth)) -> AuthContext:
    """Require admin privileges for admin endpoints."""
    if not auth.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return auth


@router.post("/steps/register", response_model=Step)
async def register_step(
    step: StepCreate,
    auth: AuthContext = Depends(require_admin),
):
    """Register a new processing step in the registry."""
    client = get_supabase_client()
    result = client.table("steps").insert(step.model_dump()).execute()
    return result.data[0]


@router.post("/steps/{step_id}/update", response_model=Step)
async def update_step(
    step_id: str,
    step: StepUpdate,
    auth: AuthContext = Depends(require_admin),
):
    """Update a processing step."""
    client = get_supabase_client()
    update_data = step.model_dump(exclude_unset=True)
    result = client.table("steps").update(update_data).eq("id", step_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Step not found")
    return result.data[0]


@router.post("/blueprints/create", response_model=Blueprint)
async def create_blueprint(
    blueprint: BlueprintCreate,
    auth: AuthContext = Depends(require_admin),
):
    """Create a new blueprint (ordered list of steps)."""
    client = get_supabase_client()
    blueprint_data = blueprint.model_dump()
    blueprint_data["org_id"] = auth.org_id
    result = client.table("blueprints").insert(blueprint_data).execute()
    return result.data[0]


@router.post("/blueprints/{blueprint_id}/update", response_model=Blueprint)
async def update_blueprint(
    blueprint_id: str,
    blueprint: BlueprintUpdate,
    auth: AuthContext = Depends(require_admin),
):
    """Update a blueprint."""
    client = get_supabase_client()
    update_data = blueprint.model_dump(exclude_unset=True)
    result = (
        client.table("blueprints")
        .update(update_data)
        .eq("id", blueprint_id)
        .eq("org_id", auth.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Blueprint not found")
    return result.data[0]
