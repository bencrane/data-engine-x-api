from __future__ import annotations

import pytest

from app.contracts.company_research import LookupCustomersOutput
from app.services.research_operations import execute_company_research_lookup_customers


@pytest.mark.asyncio
async def test_lookup_customers_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_lookup_customers(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "customers": [
                    {
                        "origin_company_name": "HubSpot",
                        "origin_company_domain": "hubspot.com",
                        "customer_name": "BetterUp",
                        "customer_domain": "betterup.com",
                        "customer_linkedin_url": "https://www.linkedin.com/company/betterup/",
                    }
                ],
                "customer_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_customers",
        _fake_lookup_customers,
    )

    result = await execute_company_research_lookup_customers(
        input_data={
            "noise": [1, {"unrelated": True}],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "hubspot.com",
                    "company_name": "HubSpot",
                },
                "history": [{"step": "prior_enrichment"}],
                "metadata": {"pipeline_run_id": "run_123"},
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_customers"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["customer_count"] == 1
    assert result["output"]["customers"][0]["customer_domain"] == "betterup.com"


@pytest.mark.asyncio
async def test_lookup_customers_missing_company_domain_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_customers",
        _should_not_be_called,
    )

    result = await execute_company_research_lookup_customers(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "HubSpot",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_customers"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_lookup_customers_success_validates_contract_and_count(monkeypatch):
    async def _fake_lookup_customers(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "customers": [
                    {
                        "origin_company_name": "HubSpot",
                        "origin_company_domain": "hubspot.com",
                        "customer_name": "BetterUp",
                        "customer_domain": "betterup.com",
                        "customer_linkedin_url": "https://www.linkedin.com/company/betterup/",
                    },
                    {
                        "origin_company_name": "HubSpot",
                        "origin_company_domain": "hubspot.com",
                        "customer_name": "Asana",
                        "customer_domain": "asana.com",
                        "customer_linkedin_url": None,
                    },
                ],
                "customer_count": 999,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_customers",
        _fake_lookup_customers,
    )

    result = await execute_company_research_lookup_customers(
        input_data={
            "cumulative_context": {
                "company_domain": "hubspot.com",
            }
        }
    )

    assert result["status"] == "found"
    validated = LookupCustomersOutput.model_validate(result["output"])
    assert len(validated.customers) == 2
    assert validated.customer_count == len(validated.customers)
    assert validated.source_provider == "revenueinfra"


@pytest.mark.asyncio
async def test_lookup_customers_empty_customers_returns_not_found(monkeypatch):
    async def _fake_lookup_customers(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "customers": [],
                "customer_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_customers",
        _fake_lookup_customers,
    )

    result = await execute_company_research_lookup_customers(
        input_data={
            "cumulative_context": {
                "company_domain": "hubspot.com",
            }
        }
    )

    assert result["status"] == "not_found"
    validated = LookupCustomersOutput.model_validate(result["output"])
    assert validated.customer_count == 0
    assert validated.customers == []
