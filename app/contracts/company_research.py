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
