from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CompanySearchResultItem(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_linkedin_id: str | None = None
    company_type: str | None = None
    industry_primary: str | None = None
    employee_count: int | str | None = None
    employee_range: str | None = None
    founded_year: int | None = None
    hq_locality: str | None = None
    hq_country_code: str | None = None
    description_raw: str | None = None
    specialties: list[Any] | str | None = None
    follower_count: int | str | None = None
    source_provider: str = "blitzapi"


class BlitzAPICompanySearchOutput(BaseModel):
    results: list[CompanySearchResultItem]
    results_count: int
    total_results: int | None = None
    cursor: str | None = None
    source_provider: str = "blitzapi"
