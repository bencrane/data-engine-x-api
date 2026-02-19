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


class TheirStackHiringTeamMember(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    linkedin_url: str | None = None
    role: str | None = None
    image_url: str | None = None


class TheirStackEmbeddedCompany(BaseModel):
    theirstack_company_id: str | None = None
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    country: str | None = None
    employee_count: int | None = None
    employee_count_range: str | None = None
    logo: str | None = None
    linkedin_url: str | None = None
    num_jobs: int | None = None
    num_jobs_last_30_days: int | None = None
    founded_year: int | None = None
    annual_revenue_usd: float | None = None
    total_funding_usd: int | None = None
    last_funding_round_date: str | None = None
    funding_stage: str | None = None
    city: str | None = None
    long_description: str | None = None
    publicly_traded_symbol: str | None = None
    publicly_traded_exchange: str | None = None
    technology_slugs: list[str] | None = None
    technology_names: list[str] | None = None


class TheirStackJobLocation(BaseModel):
    name: str | None = None
    state: str | None = None
    state_code: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    display_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    type: str | None = None


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
    theirstack_job_id: int | None = None
    normalized_title: str | None = None
    final_url: str | None = None
    source_url: str | None = None
    discovered_at: str | None = None
    reposted: bool | None = None
    date_reposted: str | None = None
    short_location: str | None = None
    long_location: str | None = None
    state_code: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    locations: list[TheirStackJobLocation] | None = None
    country: str | None = None
    country_code: str | None = None
    countries: list[str] | None = None
    country_codes: list[str] | None = None
    cities: list[str] | None = None
    remote: bool | None = None
    hybrid: bool | None = None
    employment_statuses: list[str] | None = None
    easy_apply: bool | None = None
    salary_string: str | None = None
    min_annual_salary_usd: float | None = None
    max_annual_salary_usd: float | None = None
    avg_annual_salary_usd: float | None = None
    salary_currency: str | None = None
    description: str | None = None
    technology_slugs: list[str] | None = None
    manager_roles: list[str] | None = None
    hiring_team: list[TheirStackHiringTeamMember] | None = None
    company_object: TheirStackEmbeddedCompany | None = None


class TheirStackJobSearchOutput(BaseModel):
    results: list[TheirStackJobItem]
    result_count: int
    source_provider: str = "theirstack"


class TheirStackJobSearchExtendedOutput(BaseModel):
    results: list[TheirStackJobItem]
    result_count: int
    total_results: int | None = None
    total_companies: int | None = None
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
