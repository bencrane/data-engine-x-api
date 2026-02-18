from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.company_enrich import TechnographicsOutput
from app.providers import leadmagic
from app.services import company_operations
from app.services.company_operations import execute_company_enrich_technographics


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _set_leadmagic_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company_operations,
        "get_settings",
        lambda: SimpleNamespace(leadmagic_api_key="test-leadmagic-key"),
    )


@pytest.mark.asyncio
async def test_execute_company_enrich_technographics_noisy_context_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_leadmagic_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        assert url == "https://api.leadmagic.io/v1/companies/company-technographics"
        assert headers["X-API-Key"] == "test-leadmagic-key"
        assert json["company_domain"] == "acme.com"
        return _FakeResponse(
            status_code=200,
            payload={
                "company_domain": "acme.com",
                "message": "Technologies found.",
                "technologies": [
                    {"name": "React", "category": "JavaScript Framework", "website": "react.dev", "icon": "https://cdn/react.svg"},
                ],
                "categories": {"JavaScript Framework": ["React"]},
            },
        )

    monkeypatch.setattr(leadmagic.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_technographics(
        input_data={
            "company_domain": "acme.com",
            "company_profile": {"company_name": "Acme Inc"},
            "irrelevant": {"nested": ["noise"]},
            "results": [{"id": "ignored"}],
        }
    )

    assert result["operation_id"] == "company.enrich.technographics"
    assert result["status"] == "found"
    assert isinstance(result["provider_attempts"], list)
    assert len(result["provider_attempts"]) == 1
    assert isinstance(result.get("output"), dict)


@pytest.mark.asyncio
async def test_execute_company_enrich_technographics_missing_company_domain_failed():
    result = await execute_company_enrich_technographics(
        input_data={"company_profile": {"company_domain": "acme.com"}}
    )

    assert result["operation_id"] == "company.enrich.technographics"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_technographics_success_validates_contract_and_count(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_leadmagic_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={
                "company_domain": "acme.com",
                "message": "Technologies found.",
                "technologies": [
                    {"name": "React", "category": "JavaScript Framework", "website": "react.dev", "icon": "https://cdn/react.svg"},
                    {"name": "HubSpot", "category": "CRM", "website": "hubspot.com", "icon": "https://cdn/hubspot.svg"},
                ],
                "categories": {
                    "JavaScript Framework": ["React"],
                    "CRM": ["HubSpot"],
                },
            },
        )

    monkeypatch.setattr(leadmagic.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_technographics(input_data={"company_domain": "acme.com"})
    validated = TechnographicsOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.technology_count == len(validated.technologies)
    assert validated.source_provider == "leadmagic"


@pytest.mark.asyncio
async def test_execute_company_enrich_technographics_no_technologies_found_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_leadmagic_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={
                "company_domain": "acme.com",
                "message": "No technologies found for this domain.",
                "technologies": [],
                "categories": {},
            },
        )

    monkeypatch.setattr(leadmagic.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_technographics(input_data={"company_domain": "acme.com"})

    assert result["status"] == "not_found"
    assert result["output"]["technology_count"] == 0
    assert result["output"]["technologies"] == []
