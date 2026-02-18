from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CompanyProfileOutput(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_linkedin_id: str | None = None
    company_type: str | None = None
    industry_primary: str | None = None
    industry_derived: list[Any] | str | None = None
    employee_count: int | str | None = None
    employee_range: str | None = None
    founded_year: int | None = None
    hq_locality: str | None = None
    hq_country_code: str | None = None
    description_raw: str | None = None
    specialties: list[Any] | str | None = None
    annual_revenue_range: str | None = None
    follower_count: int | str | None = None
    logo_url: str | None = None
    source_company_id: str | int | None = None


class CompanyEnrichProfileOutput(BaseModel):
    company_profile: CompanyProfileOutput | None
    source_providers: list[str]


class TechnologyItem(BaseModel):
    name: str
    category: str | None = None
    website: str | None = None
    icon: str | None = None


class TechnographicsOutput(BaseModel):
    technologies: list[TechnologyItem]
    categories: dict[str, list[str]] | None = None
    technology_count: int
    source_provider: str = "leadmagic"
