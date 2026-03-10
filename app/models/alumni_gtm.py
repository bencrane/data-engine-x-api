from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field


class AlumniGtmPerson(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    headline: str | None = None
    location: str | None = None


class AlumniGtmFirmographics(BaseModel):
    industry: str | None = None
    employee_count: int | None = None
    size_range: str | None = None
    founded_year: int | None = None
    country: str | None = None
    city: str | None = None
    state: str | None = None
    description: str | None = None


class AlumniGtmStoreleads(BaseModel):
    platform: str | None = None
    estimated_sales_yearly: float | None = None
    product_count: int | None = None
    rank: int | None = None
    technologies: list[str] = Field(default_factory=list)


class AlumniGtmAds(BaseModel):
    meta_ads_count: int = 0
    google_ads_count: int = 0
    latest_meta_ad: dict[str, Any] | None = None
    latest_google_ad: dict[str, Any] | None = None


class AlumniGtmCurrentCompany(BaseModel):
    name: str | None = None
    domain: str | None = None
    linkedin_url: str | None = None
    role: str | None = None
    cleaned_job_title: str | None = None
    firmographics: AlumniGtmFirmographics = Field(default_factory=AlumniGtmFirmographics)
    storeleads: AlumniGtmStoreleads = Field(default_factory=AlumniGtmStoreleads)
    ads: AlumniGtmAds = Field(default_factory=AlumniGtmAds)


class AlumniGtmPriorCompany(BaseModel):
    name: str | None = None
    domain: str | None = None
    linkedin_url: str | None = None
    role: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    gtm_fit: bool | None = None
    gtm_fit_reason: str | None = None


class AlumniGtmLead(BaseModel):
    person: AlumniGtmPerson
    current_company: AlumniGtmCurrentCompany
    prior_company: AlumniGtmPriorCompany


class AlumniGtmPriorCompanySummary(BaseModel):
    name: str | None = None
    domain: str
    lead_count: int


class AlumniGtmLeadsResponse(BaseModel):
    origin_company_domain: str
    total_leads: int
    total_prior_companies: int
    leads: list[AlumniGtmLead]
    prior_companies_summary: list[AlumniGtmPriorCompanySummary]
