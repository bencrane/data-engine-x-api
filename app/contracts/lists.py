"""Request and response contracts for list management endpoints."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# -- Request models --


class CreateListRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity_type: Literal["companies", "people"]


class AddListMembersRequest(BaseModel):
    members: list[dict[str, Any]] = Field(..., min_length=1, max_length=500)


class RemoveListMembersRequest(BaseModel):
    member_ids: list[str] = Field(..., min_length=1, max_length=500)


# -- Response models --


class ListSummary(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    member_count: int
    created_by_user_id: str | None
    created_at: str
    updated_at: str


class ListMember(BaseModel):
    id: str
    entity_id: str | None
    entity_type: str
    snapshot_data: dict[str, Any]
    added_at: str


class ListDetail(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    member_count: int
    created_by_user_id: str | None
    created_at: str
    updated_at: str
    members: list[ListMember]
    page: int
    per_page: int


class ListExport(BaseModel):
    list_id: str
    list_name: str
    entity_type: str
    member_count: int
    members: list[dict[str, Any]]
