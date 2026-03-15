from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class IntentSearchRequest(BaseModel):
    search_type: Literal["companies", "people"]
    criteria: dict[str, str | list[str]]
    provider: str | None = None
    limit: int = 25
    page: int = 1


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
    pagination: dict[str, Any] | None = None
