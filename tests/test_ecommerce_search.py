from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.search import EcommerceSearchOutput
from app.providers import storeleads_search
from app.services import search_operations


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _set_storeleads_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        search_operations,
        "get_settings",
        lambda: SimpleNamespace(storeleads_api_key="test-storeleads-key"),
    )


@pytest.mark.asyncio
async def test_execute_company_search_ecommerce_noisy_context_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, params: dict, headers: dict):  # noqa: ANN001
        assert url == "https://storeleads.app/json/api/v1/all/domain"
        assert headers["Authorization"] == "test-storeleads-key"
        assert params["f:p"] == "shopify"
        assert params["f:an"] == "shopify.klaviyo"
        return _FakeResponse(
            status_code=200,
            payload={
                "domains": [
                    {
                        "merchant_name": "Acme Store",
                        "name": "acme.com",
                        "platform": "shopify",
                        "plan": "Shopify Plus",
                        "estimated_sales": 1234500,
                        "rank": 42,
                        "country_code": "US",
                        "description": "Premium home goods.",
                    }
                ]
            },
        )

    monkeypatch.setattr(storeleads_search.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_ecommerce(
        input_data={
            "noise": [{"ignore": True}],
            "results": [{"ignored": "value"}],
            "step_config": {"platform": "shopify", "app_installed": "shopify.klaviyo"},
            "metadata": {"trace": "abc"},
        }
    )

    assert result["operation_id"] == "company.search.ecommerce"
    assert result["status"] == "found"
    assert isinstance(result["output"], dict)
    assert isinstance(result["provider_attempts"], list)
    assert result["output"]["result_count"] == 1


@pytest.mark.asyncio
async def test_execute_company_search_ecommerce_no_filters_fails_with_missing_inputs():
    result = await search_operations.execute_company_search_ecommerce(
        input_data={"step_config": {"rank_min": 10}}
    )

    assert result["operation_id"] == "company.search.ecommerce"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["platform|category|app_installed"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_search_ecommerce_success_validates_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, params: dict, headers: dict):  # noqa: ANN001
        assert url == "https://storeleads.app/json/api/v1/all/domain"
        assert headers["Authorization"] == "test-storeleads-key"
        assert params["f:cc"] == "US"
        assert params["f:ds"] == "Active"
        assert params["page"] == 2
        assert params["page_size"] == 25
        assert params["f:rk:min"] == 1
        assert params["f:rk:max"] == 1000
        return _FakeResponse(
            status_code=200,
            payload={
                "domains": [
                    {
                        "merchant_name": "Store One",
                        "name": "storeone.com",
                        "platform": "shopify",
                        "plan": "Shopify Plus",
                        "estimated_sales": 3300000,
                        "rank": 101,
                        "country_code": "US",
                        "description": "Store one description.",
                    },
                    {
                        "merchant_name": "Store Two",
                        "name": "storetwo.com",
                        "platform": "shopify",
                        "plan": "Shopify",
                        "estimated_sales": 1200000,
                        "rank": 502,
                        "country_code": "US",
                        "description": "Store two description.",
                    },
                ]
            },
        )

    monkeypatch.setattr(storeleads_search.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_ecommerce(
        input_data={
            "platform": "shopify",
            "country_code": "US",
            "rank_min": 1,
            "rank_max": 1000,
            "page": 2,
            "page_size": 25,
        }
    )
    validated = EcommerceSearchOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.result_count == 2
    assert validated.page == 2
    assert validated.source_provider == "storeleads"


@pytest.mark.asyncio
async def test_execute_company_search_ecommerce_empty_results_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_storeleads_key(monkeypatch)

    async def _mock_get(self, url: str, params: dict, headers: dict):  # noqa: ANN001
        _ = (url, params, headers)
        return _FakeResponse(status_code=200, payload={"domains": []})

    monkeypatch.setattr(storeleads_search.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_ecommerce(
        input_data={"category": "/Apparel/"}
    )

    assert result["status"] == "not_found"
    assert result["output"]["result_count"] == 0
    assert result["output"]["results"] == []
