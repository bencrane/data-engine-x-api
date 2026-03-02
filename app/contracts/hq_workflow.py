from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class InferLinkedInUrlOutput(BaseModel):
    company_linkedin_url: str | None = None
    source_provider: str = "revenueinfra"


class GeminiIcpJobTitlesOutput(BaseModel):
    inferred_product: str | None = None
    buyer_persona: str | None = None
    titles: list[Any] | None = None
    champion_titles: list[str] | None = None
    evaluator_titles: list[str] | None = None
    decision_maker_titles: list[str] | None = None
    source_provider: str = "revenueinfra"


class DiscoverCustomersGeminiOutput(BaseModel):
    customers: list[Any] | None = None
    customer_count: int | None = None
    source_provider: str = "revenueinfra"


class IcpCriterionOutput(BaseModel):
    icp_criterion: str | None = None
    source_provider: str = "revenueinfra"


class SalesNavUrlOutput(BaseModel):
    salesnav_url: str | None = None
    source_provider: str = "revenueinfra"


class EvaluateIcpFitOutput(BaseModel):
    icp_fit_verdict: str | None = None
    icp_fit_reasoning: str | None = None
    source_provider: str = "revenueinfra"
