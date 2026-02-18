from __future__ import annotations

from typing import Any

import pytest

from app.contracts.company_research import CheckVCFundingOutput
from app.providers.revenueinfra.vc_funding import check_vc_funding
from app.services.research_operations import execute_company_research_check_vc_funding


@pytest.fixture(autouse=True)
def _mock_research_settings(monkeypatch):
    class _Settings:
        revenueinfra_api_url = "https://api.revenueinfra.com"

    monkeypatch.setattr(
        "app.services.research_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_check_vc_funding_noisy_rich_context_returns_structured_response(monkeypatch):
    async def _fake_check_vc_funding(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "check_vc_funding",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "has_raised_vc": True,
                "vc_count": 1,
                "vc_names": ["Sequoia"],
                "vcs": [{"vc_name": "Sequoia", "vc_domain": None}],
                "founded_date": "Oct 2012",
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.check_vc_funding",
        _fake_check_vc_funding,
    )

    result = await execute_company_research_check_vc_funding(
        input_data={
            "noise": [1, {"unrelated": True}],
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "figma.com",
                    "company_name": "Figma",
                },
                "history": [{"step": "prior_enrichment"}],
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.check_vc_funding"
    assert result["status"] == "found"
    assert result["output"]["has_raised_vc"] is True
    assert result["output"]["vc_count"] == 1
    assert result["output"]["founded_date"] == "Oct 2012"


@pytest.mark.asyncio
async def test_check_vc_funding_missing_company_domain_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr(
        "app.providers.revenueinfra.check_vc_funding",
        _should_not_be_called,
    )

    result = await execute_company_research_check_vc_funding(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_name": "Figma",
                }
            }
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.check_vc_funding"
    assert result["status"] == "failed"
    assert result.get("missing_inputs") == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_check_vc_funding_with_vc_validates_contract_and_count(monkeypatch):
    async def _fake_check_vc_funding(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "figma.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "check_vc_funding",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "has_raised_vc": True,
                "vc_count": 999,
                "vc_names": ["Sequoia", "Coatue"],
                "vcs": [
                    {"vc_name": "Sequoia", "vc_domain": None},
                    {"vc_name": "Coatue", "vc_domain": "coatue.com"},
                ],
                "founded_date": "Oct 2012",
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.check_vc_funding",
        _fake_check_vc_funding,
    )

    result = await execute_company_research_check_vc_funding(
        input_data={"cumulative_context": {"company_domain": "figma.com"}}
    )

    assert result["status"] == "found"
    validated = CheckVCFundingOutput.model_validate(result["output"])
    assert validated.has_raised_vc is True
    assert validated.vc_count == len(validated.vc_names)
    assert validated.vc_count == len(validated.vcs)


@pytest.mark.asyncio
async def test_check_vc_funding_without_vc_is_found_not_not_found(monkeypatch):
    async def _fake_check_vc_funding(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "bootstrapped.io"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "check_vc_funding",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "has_raised_vc": False,
                "vc_count": 0,
                "vc_names": [],
                "vcs": [],
                "founded_date": None,
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.check_vc_funding",
        _fake_check_vc_funding,
    )

    result = await execute_company_research_check_vc_funding(
        input_data={"cumulative_context": {"company_domain": "bootstrapped.io"}}
    )

    assert result["status"] == "found"
    assert result["output"]["has_raised_vc"] is False
    assert result["output"]["vc_count"] == 0


@pytest.mark.asyncio
async def test_check_vc_funding_adapter_handles_null_vc_domain(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"success":true}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "success": True,
                "domain": "figma.com",
                "has_raised_vc": True,
                "vc_count": 2,
                "vc_names": ["Sequoia", "Coatue"],
                "vcs": [
                    {"vc_name": "Sequoia", "vc_domain": None},
                    {"vc_name": "Coatue", "vc_domain": "coatue.com"},
                ],
                "founded_date": "Oct 2012",
                "error": None,
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
                == "https://api.revenueinfra.com/run/companies/db/has-raised-vc-status/check"
            )
            assert json == {"domain": "figma.com"}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.vc_funding.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await check_vc_funding(
        base_url="https://api.revenueinfra.com",
        domain="figma.com",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["vc_count"] == 2
    assert result["mapped"]["vcs"][0]["vc_name"] == "Sequoia"
    assert result["mapped"]["vcs"][0]["vc_domain"] is None
