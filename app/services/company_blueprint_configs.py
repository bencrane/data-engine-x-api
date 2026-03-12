from __future__ import annotations

from typing import Any

from app.database import get_supabase_client


def _company_in_org(org_id: str, company_id: str) -> bool:
    client = get_supabase_client()
    result = (
        client.table("companies")
        .select("id")
        .eq("id", company_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def _blueprint_in_org(org_id: str, blueprint_id: str) -> bool:
    client = get_supabase_client()
    result = (
        client.table("blueprints")
        .select("id")
        .eq("id", blueprint_id)
        .eq("org_id", org_id)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def create_company_blueprint_config(
    *,
    org_id: str,
    company_id: str,
    blueprint_id: str,
    name: str,
    description: str | None,
    input_payload: dict[str, Any],
    is_active: bool,
    actor_user_id: str | None,
) -> dict[str, Any]:
    if not _company_in_org(org_id, company_id):
        raise ValueError("company_id does not belong to org_id")
    if not _blueprint_in_org(org_id, blueprint_id):
        raise ValueError("blueprint_id does not belong to org_id")

    client = get_supabase_client()
    result = (
        client.table("company_blueprint_configs")
        .insert(
            {
                "org_id": org_id,
                "company_id": company_id,
                "blueprint_id": blueprint_id,
                "name": name,
                "description": description,
                "input_payload": input_payload,
                "is_active": is_active,
                "created_by_user_id": actor_user_id,
                "updated_by_user_id": actor_user_id,
            }
        )
        .execute()
    )
    return result.data[0]


def list_company_blueprint_configs(
    *,
    org_id: str,
    company_id: str | None = None,
    blueprint_id: str | None = None,
    is_active: bool | None = None,
) -> list[dict[str, Any]]:
    client = get_supabase_client()
    query = (
        client.table("company_blueprint_configs")
        .select("*, blueprints(id, name), companies(id, name)")
        .eq("org_id", org_id)
    )
    if company_id:
        query = query.eq("company_id", company_id)
    if blueprint_id:
        query = query.eq("blueprint_id", blueprint_id)
    if is_active is not None:
        query = query.eq("is_active", is_active)
    result = query.order("created_at", desc=True).execute()
    return result.data


def get_company_blueprint_config(
    *,
    org_id: str,
    config_id: str,
) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("company_blueprint_configs")
        .select("*, blueprints(id, name), companies(id, name)")
        .eq("org_id", org_id)
        .eq("id", config_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def update_company_blueprint_config(
    *,
    org_id: str,
    config_id: str,
    actor_user_id: str | None,
    company_id: str | None = None,
    blueprint_id: str | None = None,
    name: str | None = None,
    description: str | None = None,
    input_payload: dict[str, Any] | None = None,
    is_active: bool | None = None,
) -> dict[str, Any] | None:
    existing = get_company_blueprint_config(org_id=org_id, config_id=config_id)
    if existing is None:
        return None

    if company_id and not _company_in_org(org_id, company_id):
        raise ValueError("company_id does not belong to org_id")
    if blueprint_id and not _blueprint_in_org(org_id, blueprint_id):
        raise ValueError("blueprint_id does not belong to org_id")

    update_data: dict[str, Any] = {"updated_by_user_id": actor_user_id}
    if company_id is not None:
        update_data["company_id"] = company_id
    if blueprint_id is not None:
        update_data["blueprint_id"] = blueprint_id
    if name is not None:
        update_data["name"] = name
    if description is not None:
        update_data["description"] = description
    if input_payload is not None:
        update_data["input_payload"] = input_payload
    if is_active is not None:
        update_data["is_active"] = is_active

    client = get_supabase_client()
    result = (
        client.table("company_blueprint_configs")
        .update(update_data)
        .eq("org_id", org_id)
        .eq("id", config_id)
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]
