# app/routers/admin.py — Admin/super-user endpoints (register steps, manage recipes)

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import AuthContext, get_current_auth
from app.database import get_supabase_client
from app.models.step import Step, StepCreate, StepUpdate
from app.models.recipe import Recipe, RecipeCreate, RecipeUpdate

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


@router.post("/recipes/create", response_model=Recipe)
async def create_recipe(
    recipe: RecipeCreate,
    auth: AuthContext = Depends(require_admin),
):
    """Create a new recipe (ordered list of steps)."""
    client = get_supabase_client()
    recipe_data = recipe.model_dump()
    recipe_data["org_id"] = auth.org_id
    result = client.table("recipes").insert(recipe_data).execute()
    return result.data[0]


@router.post("/recipes/{recipe_id}/update", response_model=Recipe)
async def update_recipe(
    recipe_id: str,
    recipe: RecipeUpdate,
    auth: AuthContext = Depends(require_admin),
):
    """Update a recipe."""
    client = get_supabase_client()
    update_data = recipe.model_dump(exclude_unset=True)
    result = (
        client.table("recipes")
        .update(update_data)
        .eq("id", recipe_id)
        .eq("org_id", auth.org_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return result.data[0]
