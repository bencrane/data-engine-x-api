from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LinkedInAdsOutput(BaseModel):
    ads: list[dict[str, Any]]
    ads_count: int
    continuation_token: str | None = None
    is_last_page: bool | None = None
    page_id: str | None = None
    total_ads: int | None = None


class MetaAdsOutput(BaseModel):
    results: list[dict[str, Any]]
    results_count: int
    continuation_token: str | None = None
    number_of_ads: int | None = None
    is_result_complete: bool | None = None
    search_type: str | None = None
    endpoint_used: str


class GoogleAdsOutput(BaseModel):
    ads: list[dict[str, Any]]
    ads_count: int
    continuation_token: str | None = None
    country_code: str | None = None
