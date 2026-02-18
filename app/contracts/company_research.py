from __future__ import annotations

from pydantic import BaseModel


class ResolveG2UrlOutput(BaseModel):
    company_name: str
    company_domain: str | None
    g2_url: str | None
    confidence: float
    provider_used: str | None


class ResolvePricingPageUrlOutput(BaseModel):
    company_name: str
    company_domain: str | None
    pricing_page_url: str | None
    confidence: float
    provider_used: str | None


class CompetitorItem(BaseModel):
    name: str | None = None
    domain: str | None = None
    linkedin_url: str | None = None


class DiscoverCompetitorsOutput(BaseModel):
    competitors: list[CompetitorItem]
    competitor_count: int
    source_provider: str = "revenueinfra"


class CustomerItem(BaseModel):
    customer_name: str | None = None
    customer_domain: str | None = None
    customer_linkedin_url: str | None = None
    origin_company_name: str | None = None
    origin_company_domain: str | None = None


class LookupCustomersOutput(BaseModel):
    customers: list[CustomerItem]
    customer_count: int
    source_provider: str = "revenueinfra"


class ChampionItem(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    company_linkedin_url: str | None = None
    case_study_url: str | None = None


class ChampionTestimonialItem(ChampionItem):
    testimonial: str | None = None


class LookupChampionsOutput(BaseModel):
    champions: list[ChampionItem]
    champion_count: int
    source_provider: str = "revenueinfra"


class LookupChampionTestimonialsOutput(BaseModel):
    champions: list[ChampionTestimonialItem]
    champion_count: int
    source_provider: str = "revenueinfra"


class AlumniItem(BaseModel):
    full_name: str | None = None
    linkedin_url: str | None = None
    current_company_name: str | None = None
    current_company_domain: str | None = None
    current_company_linkedin_url: str | None = None
    current_job_title: str | None = None
    past_company_name: str | None = None
    past_company_domain: str | None = None
    past_job_title: str | None = None


class LookupAlumniOutput(BaseModel):
    alumni: list[AlumniItem]
    alumni_count: int
    source_provider: str = "revenueinfra"
