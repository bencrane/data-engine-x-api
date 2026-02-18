from __future__ import annotations

from pydantic import BaseModel


class TheirStackCompanyItem(BaseModel):
    company_name: str | None = None
    domain: str | None = None
    linkedin_url: str | None = None
    industry: str | None = None
    employee_count: int | None = None
    country_code: str | None = None
    num_jobs: int | None = None
    num_jobs_last_30_days: int | None = None
    technology_slugs: list[str] | None = None
    annual_revenue_usd: float | None = None
    total_funding_usd: int | None = None
    funding_stage: str | None = None
    source_provider: str = "theirstack"


class TheirStackCompanySearchOutput(BaseModel):
    results: list[TheirStackCompanyItem]
    result_count: int
    source_provider: str = "theirstack"


class TheirStackJobItem(BaseModel):
    job_id: int | None = None
    job_title: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    url: str | None = None
    date_posted: str | None = None
    location: str | None = None
    seniority: str | None = None
    source_provider: str = "theirstack"


class TheirStackJobSearchOutput(BaseModel):
    results: list[TheirStackJobItem]
    result_count: int
    source_provider: str = "theirstack"


class TheirStackTechItem(BaseModel):
    name: str
    slug: str | None = None
    category: str | None = None
    confidence: str | None = None
    jobs: int | None = None
    jobs_last_30_days: int | None = None
    first_date_found: str | None = None
    last_date_found: str | None = None
    rank_within_category: int | None = None


class TheirStackTechStackOutput(BaseModel):
    technologies: list[TheirStackTechItem]
    technology_count: int
    source_provider: str = "theirstack"


class TheirStackHiringSignalsOutput(BaseModel):
    company_name: str | None = None
    domain: str | None = None
    num_jobs: int | None = None
    num_jobs_last_30_days: int | None = None
    technology_slugs: list[str] | None = None
    recent_job_titles: list[str] | None = None
    source_provider: str = "theirstack"
