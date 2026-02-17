from __future__ import annotations

from pydantic import BaseModel


class PricingIntelligenceOutput(BaseModel):
    pricing_page_url: str | None = None
    free_trial: str | None = None
    pricing_visibility: str | None = None
    sales_motion: str | None = None
    pricing_model: str | None = None
    billing_default: str | None = None
    number_of_tiers: int | str | None = None
    add_ons_offered: str | None = None
    enterprise_tier_exists: str | None = None
    security_compliance_gating: str | None = None
    annual_commitment_required: str | None = None
    plan_naming_style: str | None = None
    custom_pricing_mentioned: str | None = None
    money_back_guarantee: str | None = None
    minimum_seats: str | None = None
    fields_resolved: int = 0
    source_provider: str = "revenueinfra"
