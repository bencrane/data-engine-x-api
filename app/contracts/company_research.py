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
