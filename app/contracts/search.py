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


class EcommerceSearchResultItem(BaseModel):
    merchant_name: str | None = None
    domain: str | None = None
    ecommerce_platform: str | None = None
    ecommerce_plan: str | None = None
    estimated_monthly_sales_cents: int | None = None
    global_rank: int | None = None
    country_code: str | None = None
    description: str | None = None
    source_provider: str = "storeleads"


class EcommerceSearchOutput(BaseModel):
    results: list[EcommerceSearchResultItem]
    result_count: int
    page: int
    source_provider: str = "storeleads"


class FMCSACarrierSearchItem(BaseModel):
    dot_number: str | None = None
    legal_name: str | None = None
    dba_name: str | None = None
    allow_to_operate: bool | None = None
    city: str | None = None
    state: str | None = None
    phone: str | None = None
    source_provider: str = "fmcsa"


class FMCSACarrierSearchOutput(BaseModel):
    results: list[FMCSACarrierSearchItem]
    result_count: int
    source_provider: str = "fmcsa"
