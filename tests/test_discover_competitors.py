from __future__ import annotations

import pytest

from app.contracts.company_research import DiscoverCompetitorsOutput
from app.services.research_operations import (
    execute_company_research_discover_competitors,
)


@pytest.mark.asyncio
async def test_discover_competitors_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_discover_competitors(
        *,
        base_url: str,
        domain: str,
        company_name: str,
        company_linkedin_url: str | None = None,
    ):
        assert isinstance(base_url, str)
        assert domain == "stripe.com"
        assert company_name == "Stripe"
        assert company_linkedin_url == "https://linkedin.com/company/stripe"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "discover_competitors",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "competitors": [
                    {
                        "name": "Adyen",
                        "domain": "adyen.com",
                        "linkedin_url": "https://linkedin.com/company/adyen",
                    }
                ]
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.discover_competitors",
        _fake_discover_competitors,
    )

    result = await execute_company_research_discover_competitors(
        input_data={
            "noise": ["unrelated", {"value": True}],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "stripe.com",
                    "company_name": "Stripe",
                    "company_linkedin_url": "https://linkedin.com/company/stripe",
                    "industry_primary": "Fintech",
                },
                "timeline": [{"event": "enriched"}],
                "metadata": {"pipeline_run_id": "run_123"},
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.discover_competitors"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["competitor_count"] == 1
    assert result["output"]["source_provider"] == "revenueinfra"
    assert result["output"]["competitors"][0]["name"] == "Adyen"


@pytest.mark.asyncio
async def test_discover_competitors_missing_domain_and_company_name_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when required inputs are missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.discover_competitors",
        _should_not_be_called,
    )

    result = await execute_company_research_discover_competitors(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "industry_primary": "SaaS",
                }
            },
            "extra_context": {"results": [{"source": "search"}]},
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.discover_competitors"
    assert result["status"] == "failed"
    assert set(result.get("missing_inputs") or []) == {"company_domain", "company_name"}
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_discover_competitors_success_validates_contract_shape(monkeypatch):
    async def _fake_discover_competitors(
        *,
        base_url: str,
        domain: str,
        company_name: str,
        company_linkedin_url: str | None = None,
    ):
        assert isinstance(base_url, str)
        assert domain == "stripe.com"
        assert company_name == "Stripe"
        assert company_linkedin_url is None
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "discover_competitors",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "competitors": [
                    {
                        "name": "Adyen",
                        "domain": "adyen.com",
                        "linkedin_url": "https://linkedin.com/company/adyen",
                    },
                    {
                        "name": "Square",
                        "domain": "squareup.com",
                        "linkedin_url": "https://linkedin.com/company/square",
                    },
                ]
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.discover_competitors",
        _fake_discover_competitors,
    )

    result = await execute_company_research_discover_competitors(
        input_data={
            "cumulative_context": {
                "company_domain": "stripe.com",
                "company_name": "Stripe",
            }
        }
    )

    assert result["status"] == "found"
    validated = DiscoverCompetitorsOutput.model_validate(result["output"])
    assert validated.competitor_count == 2
    assert validated.source_provider == "revenueinfra"
    assert len(validated.competitors) == 2
