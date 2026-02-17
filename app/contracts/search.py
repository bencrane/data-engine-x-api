from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CompanySearchResultItem(BaseModel):
    company_name: str | None
    company_domain: str | None
    company_website: str | None
    company_linkedin_url: str | None
    industry_primary: str | None
    employee_range: str | None
    founded_year: int | None
    hq_country_code: str | None
    source_company_id: str | None
    source_provider: str
    raw: dict[str, Any]


class CompanySearchOutput(BaseModel):
    results: list[CompanySearchResultItem]
    result_count: int
    provider_order_used: list[str]
    pagination: dict[str, Any]


class PersonSearchResultItem(BaseModel):
    full_name: str | None
    first_name: str | None
    last_name: str | None
    linkedin_url: str | None
    headline: str | None
    current_title: str | None
    current_company_name: str | None
    current_company_domain: str | None
    location_name: str | None
    country_code: str | None
    source_person_id: str | None
    source_provider: str
    raw: dict[str, Any]


class PersonSearchOutput(BaseModel):
    results: list[PersonSearchResultItem]
    result_count: int
    provider_order_used: list[str]
    pagination: dict[str, Any]
