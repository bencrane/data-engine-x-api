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


class EcommerceAppItem(BaseModel):
    name: str
    categories: list[str] | None = None
    monthly_cost: str | None = None


class EcommerceTechItem(BaseModel):
    name: str
    description: str | None = None


class EcommerceContactItem(BaseModel):
    type: str
    value: str
    source: str | None = None


class EcommerceEnrichOutput(BaseModel):
    merchant_name: str | None = None
    ecommerce_platform: str | None = None
    ecommerce_plan: str | None = None
    estimated_monthly_sales_cents: int | None = None
    employee_count: int | None = None
    product_count: int | None = None
    global_rank: int | None = None
    platform_rank: int | None = None
    monthly_app_spend_cents: int | None = None
    installed_apps: list[EcommerceAppItem] | None = None
    technologies: list[EcommerceTechItem] | None = None
    contact_info: list[EcommerceContactItem] | None = None
    country_code: str | None = None
    city: str | None = None
    domain_state: str | None = None
    description: str | None = None
    store_created_at: str | None = None
    shipping_carriers: list[str] | None = None
    sales_carriers: list[str] | None = None
    features: list[str] | None = None
    source_provider: str = "storeleads"


class CardRevenueOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    location_count: int | None = None
    annual_card_revenue: int | None = None
    card_revenue_period: str | None = None
    card_revenue_period_start: str | None = None
    card_revenue_period_end: str | None = None
    top_location_name: str | None = None
    top_location_address: str | None = None
    top_location_city: str | None = None
    top_location_state: str | None = None
    top_location_rank_position: int | None = None
    top_location_rank_cohort_size: int | None = None
    source_provider: str = "enigma"


class FMCSABasicScore(BaseModel):
    category: str
    percentile: float | None = None
    violation_count: int | None = None
    serious_violation_count: int | None = None
    deficiency: bool | None = None


class FMCSACarrierEnrichOutput(BaseModel):
    dot_number: str
    legal_name: str | None = None
    dba_name: str | None = None
    allow_to_operate: bool | None = None
    out_of_service: bool | None = None
    out_of_service_date: str | None = None
    total_drivers: int | None = None
    total_power_units: int | None = None
    bus_vehicles: int | None = None
    van_vehicles: int | None = None
    passenger_vehicles: int | None = None
    address_street: str | None = None
    address_city: str | None = None
    address_state: str | None = None
    address_zip: str | None = None
    phone: str | None = None
    complaint_count: int | None = None
    basic_scores: list[FMCSABasicScore] | None = None
    authority_status: str | None = None
    authority_grant_date: str | None = None
    source_provider: str = "fmcsa"
