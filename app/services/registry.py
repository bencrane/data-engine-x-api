# app/services/registry.py — Step registry logic (available steps, validation)

from app.database import get_supabase_client
from app.models.step import Step


async def get_available_steps() -> list[Step]:
    """Get all active steps from the registry."""
    client = get_supabase_client()
    result = client.table("steps").select("*").eq("is_active", True).execute()
    return [Step(**step) for step in result.data]


async def get_step_by_id(step_id: str) -> Step | None:
    """Get a step by ID."""
    client = get_supabase_client()
    result = client.table("steps").select("*").eq("id", step_id).single().execute()
    if not result.data:
        return None
    return Step(**result.data)


async def get_step_by_slug(slug: str) -> Step | None:
    """Get a step by slug."""
    client = get_supabase_client()
    result = client.table("steps").select("*").eq("slug", slug).single().execute()
    if not result.data:
        return None
    return Step(**result.data)


async def validate_recipe_steps(step_ids: list[str]) -> bool:
    """Validate that all step IDs exist and are active."""
    client = get_supabase_client()
    result = (
        client.table("steps")
        .select("id")
        .in_("id", step_ids)
        .eq("is_active", True)
        .execute()
    )
    return len(result.data) == len(step_ids)
