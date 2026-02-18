from __future__ import annotations

from typing import Any

import pytest

from app.contracts.company_research import LookupAlumniOutput
from app.providers.revenueinfra.alumni import lookup_alumni
from app.services.research_operations import execute_company_research_lookup_alumni


@pytest.fixture(autouse=True)
def _mock_research_settings(monkeypatch):
    class _Settings:
        revenueinfra_api_url = "https://api.revenueinfra.com"

    monkeypatch.setattr(
        "app.services.research_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_lookup_alumni_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_lookup_alumni(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "salesforce.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_alumni",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "alumni": [
                    {
                        "full_name": "Sarah Chen",
                        "linkedin_url": "https://www.linkedin.com/in/sarahchen",
                        "current_company_name": "Stripe",
                        "current_company_domain": "stripe.com",
                        "current_company_linkedin_url": "https://www.linkedin.com/company/stripe",
                        "current_job_title": "VP of Sales",
                        "past_company_name": "Salesforce",
                        "past_company_domain": "salesforce.com",
                        "past_job_title": "Account Executive",
                    }
                ],
                "alumni_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_alumni",
        _fake_lookup_alumni,
    )

    result = await execute_company_research_lookup_alumni(
        input_data={
            "noise": [1, {"unrelated": True}],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "salesforce.com",
                    "company_name": "Salesforce",
                },
                "history": [{"step": "prior_enrichment"}],
                "metadata": {"pipeline_run_id": "run_123"},
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_alumni"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["alumni_count"] == 1
    assert result["output"]["alumni"][0]["current_company_domain"] == "stripe.com"


@pytest.mark.asyncio
async def test_lookup_alumni_missing_company_domain_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_alumni",
        _should_not_be_called,
    )

    result = await execute_company_research_lookup_alumni(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "Salesforce",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_alumni"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_lookup_alumni_success_validates_contract_and_normalizes_count(monkeypatch):
    async def _fake_lookup_alumni(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "salesforce.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_alumni",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "alumni": [
                    {
                        "full_name": "Sarah Chen",
                        "linkedin_url": "https://www.linkedin.com/in/sarahchen",
                        "current_company_name": "Stripe",
                        "current_company_domain": "stripe.com",
                        "current_company_linkedin_url": "https://www.linkedin.com/company/stripe",
                        "current_job_title": "VP of Sales",
                        "past_company_name": "Salesforce",
                        "past_company_domain": "salesforce.com",
                        "past_job_title": None,
                    },
                    {
                        "full_name": "Alice Rivera",
                        "linkedin_url": None,
                        "current_company_name": "Ramp",
                        "current_company_domain": "ramp.com",
                        "current_company_linkedin_url": None,
                        "current_job_title": "Head of Revenue",
                        "past_company_name": "Salesforce",
                        "past_company_domain": "salesforce.com",
                        "past_job_title": "Account Manager",
                    },
                ],
                "alumni_count": 999,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_alumni",
        _fake_lookup_alumni,
    )

    result = await execute_company_research_lookup_alumni(
        input_data={"cumulative_context": {"company_domain": "salesforce.com"}}
    )

    assert result["status"] == "found"
    validated = LookupAlumniOutput.model_validate(result["output"])
    assert len(validated.alumni) == 2
    assert validated.alumni_count == len(validated.alumni)
    assert validated.source_provider == "revenueinfra"
    assert validated.alumni[0].past_job_title is None


@pytest.mark.asyncio
async def test_lookup_alumni_empty_returns_not_found(monkeypatch):
    async def _fake_lookup_alumni(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "salesforce.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_alumni",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "alumni": [],
                "alumni_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_alumni",
        _fake_lookup_alumni,
    )

    result = await execute_company_research_lookup_alumni(
        input_data={"cumulative_context": {"company_domain": "salesforce.com"}}
    )

    assert result["status"] == "not_found"
    validated = LookupAlumniOutput.model_validate(result["output"])
    assert validated.alumni == []
    assert validated.alumni_count == 0


@pytest.mark.asyncio
async def test_lookup_alumni_adapter_maps_http_response_with_null_past_job_title(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"success":true}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "success": True,
                "past_company_domain": "salesforce.com",
                "alumni_count": 1,
                "alumni": [
                    {
                        "full_name": "Sarah Chen",
                        "linkedin_url": "https://www.linkedin.com/in/sarahchen",
                        "current_company_name": "Stripe",
                        "current_company_domain": "stripe.com",
                        "current_company_linkedin_url": "https://www.linkedin.com/company/stripe",
                        "current_job_title": "VP of Sales",
                        "past_company_name": "Salesforce",
                        "past_company_domain": "salesforce.com",
                        "past_job_title": None,
                    }
                ],
            }

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, json: dict[str, Any]):
            assert url == "https://api.revenueinfra.com/run/companies/db/alumni/lookup"
            assert json == {"past_company_domain": "salesforce.com"}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.alumni.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await lookup_alumni(
        base_url="https://api.revenueinfra.com",
        domain="salesforce.com",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["alumni_count"] == 1
    assert result["mapped"]["alumni"][0]["past_job_title"] is None

