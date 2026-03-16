from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class IntentSearchRequest(BaseModel):
    search_type: Literal["companies", "people"]
    criteria: dict[str, str | list[str]]
    provider: str | None = None
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    cursor: str | None = None


class EnumResolutionDetail(BaseModel):
    input_value: str
    resolved_value: str | None
    provider_field: str | None
    match_type: str
    confidence: float


class IntentSearchOutput(BaseModel):
    search_type: str
    provider_used: str
    results: list[dict[str, Any]]
    result_count: int
    enum_resolution: dict[str, EnumResolutionDetail]
    unresolved_fields: list[str]
    provider_field_gaps: list[str] = []
    pagination: dict[str, Any] | None = None
    provider_attempts: list[dict[str, Any]] = []
