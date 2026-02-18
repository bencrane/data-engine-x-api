from __future__ import annotations

from typing import Any

import pytest

from app.contracts.company_research import (
    LookupChampionTestimonialsOutput,
    LookupChampionsOutput,
)
from app.providers.revenueinfra.champions import (
    lookup_champion_testimonials,
    lookup_champions,
)
from app.services.research_operations import (
    execute_company_research_lookup_champion_testimonials,
    execute_company_research_lookup_champions,
)


@pytest.fixture(autouse=True)
def _mock_research_settings(monkeypatch):
    class _Settings:
        revenueinfra_api_url = "https://api.revenueinfra.com"

    monkeypatch.setattr(
        "app.services.research_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_lookup_champions_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_lookup_champions(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champions",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [
                    {
                        "full_name": "Daniel Quine",
                        "job_title": "Sales Manager",
                        "company_name": "Ignite",
                        "company_domain": "ignitepromise.org",
                        "company_linkedin_url": "https://www.linkedin.com/company/ignitepromise",
                        "case_study_url": "https://www.hubspot.com/case-studies/ignite",
                    }
                ],
                "champion_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champions",
        _fake_lookup_champions,
    )

    result = await execute_company_research_lookup_champions(
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
    assert result["operation_id"] == "company.research.lookup_champions"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["champion_count"] == 1
    assert result["output"]["champions"][0]["company_domain"] == "ignitepromise.org"


@pytest.mark.asyncio
async def test_lookup_champion_testimonials_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_lookup_champion_testimonials(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champion_testimonials",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [
                    {
                        "full_name": "Jeremy Gall",
                        "job_title": "Founder & CEO",
                        "company_name": "Breezeway",
                        "company_domain": "breezeway.io",
                        "company_linkedin_url": "https://www.linkedin.com/company/breezeway/",
                        "case_study_url": "https://www.hubspot.com/startups/customers/breezeway",
                        "testimonial": "We found that Guesty shared our philosophy...",
                    }
                ],
                "champion_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champion_testimonials",
        _fake_lookup_champion_testimonials,
    )

    result = await execute_company_research_lookup_champion_testimonials(
        input_data={
            "noise": ["ignore_me"],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "hubspot.com",
                    "company_name": "HubSpot",
                },
                "history": [{"step": "prior_enrichment"}],
                "metadata": {"pipeline_run_id": "run_456"},
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_champion_testimonials"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["champion_count"] == 1
    assert result["output"]["champions"][0]["testimonial"] is not None


@pytest.mark.asyncio
async def test_lookup_champions_missing_company_domain_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champions",
        _should_not_be_called,
    )

    result = await execute_company_research_lookup_champions(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "HubSpot",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_champions"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_lookup_champion_testimonials_missing_company_domain_fails_without_provider_call(
    monkeypatch,
):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champion_testimonials",
        _should_not_be_called,
    )

    result = await execute_company_research_lookup_champion_testimonials(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "HubSpot",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.lookup_champion_testimonials"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_lookup_champions_success_validates_contract(monkeypatch):
    async def _fake_lookup_champions(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champions",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [
                    {
                        "full_name": "Daniel Quine",
                        "job_title": "Sales Manager",
                        "company_name": "Ignite",
                        "company_domain": "ignitepromise.org",
                        "company_linkedin_url": "https://www.linkedin.com/company/ignitepromise",
                        "case_study_url": "https://www.hubspot.com/case-studies/ignite",
                    },
                    {
                        "full_name": "Alex Rivers",
                        "job_title": "Revenue Operations Director",
                        "company_name": "Sample Co",
                        "company_domain": "sample.co",
                        "company_linkedin_url": None,
                        "case_study_url": "https://www.hubspot.com/case-studies/sample",
                    },
                ],
                "champion_count": 999,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champions",
        _fake_lookup_champions,
    )

    result = await execute_company_research_lookup_champions(
        input_data={"cumulative_context": {"company_domain": "hubspot.com"}}
    )

    assert result["status"] == "found"
    validated = LookupChampionsOutput.model_validate(result["output"])
    assert len(validated.champions) == 2
    assert validated.champion_count == len(validated.champions)
    assert validated.source_provider == "revenueinfra"


@pytest.mark.asyncio
async def test_lookup_champion_testimonials_success_validates_contract_and_testimonial(monkeypatch):
    async def _fake_lookup_champion_testimonials(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champion_testimonials",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [
                    {
                        "full_name": "Jeremy Gall",
                        "job_title": "Founder & CEO",
                        "company_name": "Breezeway",
                        "company_domain": "breezeway.io",
                        "company_linkedin_url": "https://www.linkedin.com/company/breezeway/",
                        "case_study_url": "https://www.hubspot.com/startups/customers/breezeway",
                        "testimonial": "We found that Guesty shared our philosophy...",
                    }
                ],
                "champion_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champion_testimonials",
        _fake_lookup_champion_testimonials,
    )

    result = await execute_company_research_lookup_champion_testimonials(
        input_data={"cumulative_context": {"company_domain": "hubspot.com"}}
    )

    assert result["status"] == "found"
    validated = LookupChampionTestimonialsOutput.model_validate(result["output"])
    assert validated.champion_count == 1
    assert validated.source_provider == "revenueinfra"
    assert validated.champions[0].testimonial is not None


@pytest.mark.asyncio
async def test_lookup_champions_empty_returns_not_found(monkeypatch):
    async def _fake_lookup_champions(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champions",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [],
                "champion_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champions",
        _fake_lookup_champions,
    )

    result = await execute_company_research_lookup_champions(
        input_data={"cumulative_context": {"company_domain": "hubspot.com"}}
    )

    assert result["status"] == "not_found"
    validated = LookupChampionsOutput.model_validate(result["output"])
    assert validated.champion_count == 0
    assert validated.champions == []


@pytest.mark.asyncio
async def test_lookup_champion_testimonials_empty_returns_not_found(monkeypatch):
    async def _fake_lookup_champion_testimonials(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "hubspot.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_champion_testimonials",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "champions": [],
                "champion_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.lookup_champion_testimonials",
        _fake_lookup_champion_testimonials,
    )

    result = await execute_company_research_lookup_champion_testimonials(
        input_data={"cumulative_context": {"company_domain": "hubspot.com"}}
    )

    assert result["status"] == "not_found"
    validated = LookupChampionTestimonialsOutput.model_validate(result["output"])
    assert validated.champion_count == 0
    assert validated.champions == []


@pytest.mark.asyncio
async def test_lookup_champions_adapter_maps_http_response(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"success":true}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "success": True,
                "domain": "hubspot.com",
                "champion_count": 1,
                "champions": [
                    {
                        "full_name": "Daniel Quine",
                        "job_title": "Sales Manager",
                        "company_name": "Ignite",
                        "company_domain": "ignitepromise.org",
                        "company_linkedin_url": "https://www.linkedin.com/company/ignitepromise",
                        "case_study_url": "https://www.hubspot.com/case-studies/ignite",
                        "source": "extracted.case_study_champions",
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
            assert (
                url
                == "https://api.revenueinfra.com/run/companies/db/case-study-champions/lookup"
            )
            assert json == {"domain": "hubspot.com"}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.champions.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await lookup_champions(
        base_url="https://api.revenueinfra.com",
        domain="hubspot.com",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["champion_count"] == 1
    assert result["mapped"]["champions"][0]["full_name"] == "Daniel Quine"


@pytest.mark.asyncio
async def test_lookup_champion_testimonials_adapter_maps_testimonial(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"success":true}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "success": True,
                "domain": "hubspot.com",
                "champion_count": 1,
                "champions": [
                    {
                        "full_name": "Jeremy Gall",
                        "job_title": "Founder & CEO",
                        "company_name": "Breezeway",
                        "company_domain": "breezeway.io",
                        "company_linkedin_url": "https://www.linkedin.com/company/breezeway/",
                        "case_study_url": "https://www.hubspot.com/startups/customers/breezeway",
                        "source": "extracted.case_study_champions",
                        "testimonial": "We found that Guesty shared our philosophy...",
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
            assert (
                url
                == "https://api.revenueinfra.com/run/companies/db/case-study-champions-detailed/lookup"
            )
            assert json == {"domain": "hubspot.com"}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.champions.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await lookup_champion_testimonials(
        base_url="https://api.revenueinfra.com",
        domain="hubspot.com",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["champion_count"] == 1
    assert result["mapped"]["champions"][0]["testimonial"] is not None
