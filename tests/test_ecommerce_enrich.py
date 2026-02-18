from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.company_enrich import EcommerceEnrichOutput
from app.providers import storeleads_enrich
from app.services import company_operations
from app.services.company_operations import execute_company_enrich_ecommerce


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _set_storeleads_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company_operations,
        "get_settings",
        lambda: SimpleNamespace(storeleads_api_key="test-storeleads-key"),
    )


def _store_response_payload() -> dict:
    return {
        "merchant_name": "Acme Store",
        "platform": "shopify",
        "plan": "Shopify Plus",
        "estimated_sales": 1250000,
        "employee_count": 42,
        "product_count": 312,
        "rank": 1234,
        "platform_rank": 45,
        "monthly_app_spend": 9900,
        "apps": [
            {"name": "Klaviyo", "categories": ["marketing", "email"], "monthly_cost": "$150/month"},
            {"name": "ReCharge", "categories": ["subscriptions"], "monthly_cost": "$99/month"},
        ],
        "technologies": [
            {"name": "Google Analytics", "description": "Web analytics"},
            {"name": "Meta Pixel", "description": "Ads conversion tracking"},
        ],
        "contact_info": [
            {"type": "email", "value": "support@acme.com", "source": "/contact"},
            {"type": "twitter", "value": "https://twitter.com/acme", "source": "/"},
        ],
        "country_code": "US",
        "city": "San Francisco",
        "state": "Active",
        "description": "Premium apparel brand.",
        "created_at": "2019-04-01T00:00:00Z",
        "shipping_carriers": ["USPS", "UPS"],
        "sales_carriers": ["Amazon"],
        "features": ["Tracking Page", "Returns Page"],
    }


@pytest.mark.asyncio
async def test_execute_company_enrich_ecommerce_noisy_context_returns_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, headers: dict):  # noqa: ANN001
        assert url == "https://storeleads.app/json/api/v1/all/domain/acme.com"
        assert headers["Authorization"] == "test-storeleads-key"
        return _FakeResponse(status_code=200, payload=_store_response_payload())

    monkeypatch.setattr(storeleads_enrich.httpx.AsyncClient, "get", _mock_get)

    result = await execute_company_enrich_ecommerce(
        input_data={
            "company_domain": "acme.com",
            "company_profile": {"company_name": "Acme"},
            "results": [{"id": "noise"}],
            "step_config": {"irrelevant": True},
        }
    )

    assert result["operation_id"] == "company.enrich.ecommerce"
    assert result["status"] == "found"
    assert isinstance(result["provider_attempts"], list)
    assert len(result["provider_attempts"]) == 1
    assert isinstance(result.get("output"), dict)


@pytest.mark.asyncio
async def test_execute_company_enrich_ecommerce_missing_domain_failed():
    result = await execute_company_enrich_ecommerce(input_data={"company_profile": {"company_domain": "acme.com"}})

    assert result["operation_id"] == "company.enrich.ecommerce"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_ecommerce_success_validates_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, headers: dict):  # noqa: ANN001
        _ = (url, headers)
        return _FakeResponse(status_code=200, payload=_store_response_payload())

    monkeypatch.setattr(storeleads_enrich.httpx.AsyncClient, "get", _mock_get)

    result = await execute_company_enrich_ecommerce(input_data={"company_domain": "acme.com"})
    validated = EcommerceEnrichOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.merchant_name == "Acme Store"
    assert validated.ecommerce_platform == "shopify"
    assert validated.source_provider == "storeleads"


@pytest.mark.asyncio
async def test_execute_company_enrich_ecommerce_404_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, headers: dict):  # noqa: ANN001
        _ = (url, headers)
        return _FakeResponse(status_code=404, payload={"error": "not found"})

    monkeypatch.setattr(storeleads_enrich.httpx.AsyncClient, "get", _mock_get)

    result = await execute_company_enrich_ecommerce(input_data={"company_domain": "missing.example"})

    assert result["status"] == "not_found"
    assert "output" not in result
    assert len(result["provider_attempts"]) == 1
