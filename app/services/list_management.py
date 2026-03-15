"""Service layer for list management CRUD operations."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.database import get_supabase_client


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lists_table():
    return get_supabase_client().schema("ops").table("lists")


def _members_table():
    return get_supabase_client().schema("ops").table("list_members")


def _is_valid_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _extract_entity_id(member: dict[str, Any]) -> str | None:
    for key in ("entity_id", "source_company_id", "source_person_id"):
        val = member.get(key)
        if val and _is_valid_uuid(val):
            return str(val)
    return None


def _entity_type_singular(list_entity_type: str) -> str:
    return "company" if list_entity_type == "companies" else "person"


# ---------------------------------------------------------------------------
# 1. create_list
# ---------------------------------------------------------------------------

def create_list(
    *,
    org_id: str,
    name: str,
    description: str | None,
    entity_type: str,
    created_by_user_id: str | None,
) -> dict[str, Any]:
    row = {
        "org_id": org_id,
        "name": name,
        "description": description,
        "entity_type": entity_type,
        "member_count": 0,
        "created_by_user_id": created_by_user_id,
    }
    result = _lists_table().insert(row).execute()
    return result.data[0]


# ---------------------------------------------------------------------------
# 2. get_lists
# ---------------------------------------------------------------------------

def get_lists(
    *,
    org_id: str,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[dict[str, Any]], int]:
    offset = (page - 1) * per_page

    count_result = (
        _lists_table()
        .select("id", count="exact")
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    total_count = count_result.count or 0

    result = (
        _lists_table()
        .select("*")
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .order("created_at", desc=True)
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return result.data or [], total_count


# ---------------------------------------------------------------------------
# 3. get_list_detail
# ---------------------------------------------------------------------------

def get_list_detail(
    *,
    org_id: str,
    list_id: str,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any] | None:
    list_result = (
        _lists_table()
        .select("*")
        .eq("id", list_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not list_result.data:
        return None

    list_row = list_result.data
    offset = (page - 1) * per_page
    members_result = (
        _members_table()
        .select("*")
        .eq("list_id", list_id)
        .order("added_at", desc=True)
        .range(offset, offset + per_page - 1)
        .execute()
    )
    return {
        **list_row,
        "members": members_result.data or [],
        "page": page,
        "per_page": per_page,
    }


# ---------------------------------------------------------------------------
# 4. add_list_members
# ---------------------------------------------------------------------------

def add_list_members(
    *,
    org_id: str,
    list_id: str,
    members: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    list_result = (
        _lists_table()
        .select("id, entity_type")
        .eq("id", list_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not list_result.data:
        return []

    list_row = list_result.data
    member_type = _entity_type_singular(list_row["entity_type"])

    rows = [
        {
            "list_id": list_id,
            "org_id": org_id,
            "entity_id": _extract_entity_id(m),
            "entity_type": member_type,
            "snapshot_data": m,
        }
        for m in members
    ]

    insert_result = _members_table().insert(rows).execute()

    # Update member_count
    current = (
        _lists_table()
        .select("member_count")
        .eq("id", list_id)
        .maybe_single()
        .execute()
    )
    new_count = (current.data.get("member_count", 0) if current.data else 0) + len(members)
    _lists_table().update({
        "member_count": new_count,
        "updated_at": _utc_now_iso(),
    }).eq("id", list_id).execute()

    return insert_result.data or []


# ---------------------------------------------------------------------------
# 5. remove_list_members
# ---------------------------------------------------------------------------

def remove_list_members(
    *,
    org_id: str,
    list_id: str,
    member_ids: list[str],
) -> int:
    delete_result = (
        _members_table()
        .delete()
        .in_("id", member_ids)
        .eq("list_id", list_id)
        .eq("org_id", org_id)
        .execute()
    )
    deleted_count = len(delete_result.data) if delete_result.data else 0

    if deleted_count > 0:
        current = (
            _lists_table()
            .select("member_count")
            .eq("id", list_id)
            .maybe_single()
            .execute()
        )
        current_count = current.data.get("member_count", 0) if current.data else 0
        new_count = max(0, current_count - deleted_count)
        _lists_table().update({
            "member_count": new_count,
            "updated_at": _utc_now_iso(),
        }).eq("id", list_id).execute()

    return deleted_count


# ---------------------------------------------------------------------------
# 6. delete_list
# ---------------------------------------------------------------------------

def delete_list(
    *,
    org_id: str,
    list_id: str,
) -> bool:
    now = _utc_now_iso()
    result = (
        _lists_table()
        .update({"deleted_at": now, "updated_at": now})
        .eq("id", list_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .execute()
    )
    return bool(result.data)


# ---------------------------------------------------------------------------
# 7. export_list
# ---------------------------------------------------------------------------

def export_list(
    *,
    org_id: str,
    list_id: str,
) -> dict[str, Any] | None:
    list_result = (
        _lists_table()
        .select("*")
        .eq("id", list_id)
        .eq("org_id", org_id)
        .is_("deleted_at", "null")
        .maybe_single()
        .execute()
    )
    if not list_result.data:
        return None

    list_row = list_result.data
    members_result = (
        _members_table()
        .select("snapshot_data")
        .eq("list_id", list_id)
        .order("added_at", desc=True)
        .execute()
    )
    snapshot_dicts = [m["snapshot_data"] for m in (members_result.data or [])]

    return {
        "list_id": list_row["id"],
        "list_name": list_row["name"],
        "entity_type": list_row["entity_type"],
        "member_count": list_row["member_count"],
        "members": snapshot_dicts,
    }
