from __future__ import annotations

import pytest

from app.contracts.company_research import FindSimilarCompaniesOutput
from app.services.research_operations import (
    execute_company_research_find_similar_companies,
)


@pytest.mark.asyncio
async def test_find_similar_companies_noisy_rich_context_returns_structured_response(
    monkeypatch,
):
    async def _fake_find_similar_companies(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "find_similar_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "similar_companies": [
                    {
                        "company_name": "UXPin",
                        "company_domain": "uxpin.com",
                        "company_linkedin_url": "https://www.linkedin.com/company/uxpin",
                        "similarity_score": 0.9007873,
                    }
                ],
                "similar_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _fake_find_similar_companies,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={
            "noise": ["irrelevant", {"foo": "bar"}],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "figma.com",
                    "company_name": "Figma",
                },
                "timeline": [{"event": "enriched"}],
                "metadata": {"pipeline_run_id": "run_123"},
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.find_similar_companies"
    assert result["status"] == "found"
    assert isinstance(result.get("provider_attempts"), list)
    assert result["output"]["similar_count"] == 1
    assert result["output"]["similar_companies"][0]["company_domain"] == "uxpin.com"


@pytest.mark.asyncio
async def test_find_similar_companies_missing_company_domain_fails_without_provider_call(
    monkeypatch,
):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _should_not_be_called,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "Figma",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.find_similar_companies"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_find_similar_companies_success_validates_contract_and_count(monkeypatch):
    async def _fake_find_similar_companies(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "find_similar_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "similar_companies": [
                    {
                        "company_name": "UXPin",
                        "company_domain": "uxpin.com",
                        "company_linkedin_url": "https://www.linkedin.com/company/uxpin",
                        "similarity_score": 0.9007873,
                    },
                    {
                        "company_name": "Miro",
                        "company_domain": "miro.com",
                        "company_linkedin_url": "https://www.linkedin.com/company/mirohq",
                        "similarity_score": 0.81234,
                    },
                ],
                "similar_count": 999,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _fake_find_similar_companies,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={
            "cumulative_context": {
                "company_domain": "figma.com",
            }
        }
    )

    assert result["status"] == "found"
    validated = FindSimilarCompaniesOutput.model_validate(result["output"])
    assert len(validated.similar_companies) == 2
    assert validated.similar_count == len(validated.similar_companies)
    assert validated.source_provider == "revenueinfra"


@pytest.mark.asyncio
async def test_find_similar_companies_empty_list_returns_not_found(monkeypatch):
    async def _fake_find_similar_companies(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "find_similar_companies",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "similar_companies": [],
                "similar_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _fake_find_similar_companies,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={
            "cumulative_context": {
                "company_domain": "figma.com",
            }
        }
    )

    assert result["status"] == "not_found"
    validated = FindSimilarCompaniesOutput.model_validate(result["output"])
    assert validated.similar_count == 0
    assert validated.similar_companies == []


@pytest.mark.asyncio
async def test_find_similar_companies_null_linkedin_url_is_handled(monkeypatch):
    async def _fake_find_similar_companies(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "find_similar_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "similar_companies": [
                    {
                        "company_name": "Whimsical",
                        "company_domain": "whimsical.com",
                        "company_linkedin_url": None,
                        "similarity_score": 0.77,
                    }
                ],
                "similar_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _fake_find_similar_companies,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={"cumulative_context": {"company_domain": "figma.com"}}
    )

    validated = FindSimilarCompaniesOutput.model_validate(result["output"])
    assert validated.similar_companies[0].company_linkedin_url is None


@pytest.mark.asyncio
async def test_find_similar_companies_similarity_score_is_float(monkeypatch):
    async def _fake_find_similar_companies(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "find_similar_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "similar_companies": [
                    {
                        "company_name": "Sketch",
                        "company_domain": "sketch.com",
                        "company_linkedin_url": "https://www.linkedin.com/company/sketch-bv/",
                        "similarity_score": 1,
                    }
                ],
                "similar_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.find_similar_companies",
        _fake_find_similar_companies,
    )

    result = await execute_company_research_find_similar_companies(
        input_data={"cumulative_context": {"company_domain": "figma.com"}}
    )

    validated = FindSimilarCompaniesOutput.model_validate(result["output"])
    assert isinstance(validated.similar_companies[0].similarity_score, float)
