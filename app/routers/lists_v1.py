"""List management v1 endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth import AuthContext, get_current_auth
from app.auth.models import SuperAdminContext
from app.auth.super_admin import get_current_super_admin
from app.contracts.lists import (
    AddListMembersRequest,
    CreateListRequest,
    ListDetail,
    ListExport,
    ListMember,
    ListSummary,
    RemoveListMembersRequest,
)
from app.routers._responses import DataEnvelope
from app.services.list_management import (
    add_list_members,
    create_list,
    delete_list,
    export_list,
    get_list_detail,
    get_lists,
    remove_list_members,
)

router = APIRouter()
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


def _resolve_org_id(
    auth: AuthContext | SuperAdminContext,
    org_id_param: str | None = None,
) -> str:
    if isinstance(auth, SuperAdminContext):
        if not org_id_param:
            raise HTTPException(status_code=400, detail="org_id required for super-admin access")
        return org_id_param
    return auth.org_id


# ---------------------------------------------------------------------------
# POST /lists
# ---------------------------------------------------------------------------

@router.post("/lists")
async def create_list_endpoint(
    body: CreateListRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    user_id = auth.user_id if isinstance(auth, AuthContext) else None

    row = create_list(
        org_id=resolved_org_id,
        name=body.name,
        description=body.description,
        entity_type=body.entity_type,
        created_by_user_id=user_id,
    )
    return DataEnvelope(data=ListSummary(
        id=str(row["id"]),
        name=row["name"],
        description=row.get("description"),
        entity_type=row["entity_type"],
        member_count=row["member_count"],
        created_by_user_id=str(row["created_by_user_id"]) if row.get("created_by_user_id") else None,
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    ).model_dump())


# ---------------------------------------------------------------------------
# GET /lists
# ---------------------------------------------------------------------------

@router.get("/lists")
async def get_lists_endpoint(
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    rows, total_count = get_lists(org_id=resolved_org_id, page=page, per_page=per_page)
    summaries = [
        ListSummary(
            id=str(r["id"]),
            name=r["name"],
            description=r.get("description"),
            entity_type=r["entity_type"],
            member_count=r["member_count"],
            created_by_user_id=str(r["created_by_user_id"]) if r.get("created_by_user_id") else None,
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        ).model_dump()
        for r in rows
    ]
    return DataEnvelope(data={
        "lists": summaries,
        "total_count": total_count,
        "page": page,
        "per_page": per_page,
    })


# ---------------------------------------------------------------------------
# GET /lists/{list_id}
# ---------------------------------------------------------------------------

@router.get("/lists/{list_id}")
async def get_list_detail_endpoint(
    list_id: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    detail = get_list_detail(org_id=resolved_org_id, list_id=list_id, page=page, per_page=per_page)
    if detail is None:
        raise HTTPException(status_code=404, detail="List not found")

    members = [
        ListMember(
            id=str(m["id"]),
            entity_id=str(m["entity_id"]) if m.get("entity_id") else None,
            entity_type=m["entity_type"],
            snapshot_data=m["snapshot_data"],
            added_at=str(m["added_at"]),
        ).model_dump()
        for m in detail.get("members", [])
    ]

    return DataEnvelope(data=ListDetail(
        id=str(detail["id"]),
        name=detail["name"],
        description=detail.get("description"),
        entity_type=detail["entity_type"],
        member_count=detail["member_count"],
        created_by_user_id=str(detail["created_by_user_id"]) if detail.get("created_by_user_id") else None,
        created_at=str(detail["created_at"]),
        updated_at=str(detail["updated_at"]),
        members=members,
        page=detail["page"],
        per_page=detail["per_page"],
    ).model_dump())


# ---------------------------------------------------------------------------
# POST /lists/{list_id}/members
# ---------------------------------------------------------------------------

@router.post("/lists/{list_id}/members")
async def add_members_endpoint(
    list_id: str,
    body: AddListMembersRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    inserted = add_list_members(org_id=resolved_org_id, list_id=list_id, members=body.members)
    if not inserted:
        raise HTTPException(status_code=404, detail="List not found")

    members = [
        ListMember(
            id=str(m["id"]),
            entity_id=str(m["entity_id"]) if m.get("entity_id") else None,
            entity_type=m["entity_type"],
            snapshot_data=m["snapshot_data"],
            added_at=str(m["added_at"]),
        ).model_dump()
        for m in inserted
    ]
    return DataEnvelope(data={"added": len(members), "members": members})


# ---------------------------------------------------------------------------
# DELETE /lists/{list_id}/members
# ---------------------------------------------------------------------------

@router.delete("/lists/{list_id}/members")
async def remove_members_endpoint(
    list_id: str,
    body: RemoveListMembersRequest,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    deleted_count = remove_list_members(org_id=resolved_org_id, list_id=list_id, member_ids=body.member_ids)
    return DataEnvelope(data={"removed": deleted_count})


# ---------------------------------------------------------------------------
# DELETE /lists/{list_id}
# ---------------------------------------------------------------------------

@router.delete("/lists/{list_id}")
async def delete_list_endpoint(
    list_id: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    deleted = delete_list(org_id=resolved_org_id, list_id=list_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="List not found")
    return DataEnvelope(data={"deleted": True})


# ---------------------------------------------------------------------------
# GET /lists/{list_id}/export
# ---------------------------------------------------------------------------

@router.get("/lists/{list_id}/export")
async def export_list_endpoint(
    list_id: str,
    auth: AuthContext | SuperAdminContext = Depends(_resolve_flexible_auth),
    org_id: str | None = Query(default=None),
):
    resolved_org_id = _resolve_org_id(auth, org_id)
    result = export_list(org_id=resolved_org_id, list_id=list_id)
    if result is None:
        raise HTTPException(status_code=404, detail="List not found")
    return DataEnvelope(data=ListExport(**result).model_dump())
