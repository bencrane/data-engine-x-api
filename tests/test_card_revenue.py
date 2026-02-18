from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.company_enrich import CardRevenueOutput
from app.providers import enigma
from app.services import company_operations
from app.services.company_operations import execute_company_enrich_card_revenue


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _set_enigma_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        company_operations,
        "get_settings",
        lambda: SimpleNamespace(enigma_api_key="test-enigma-key"),
    )


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_noisy_context_returns_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        assert url == "https://api.enigma.com/graphql"
        assert headers["x-api-key"] == "test-enigma-key"
        assert json["variables"]["searchInput"]["name"] == "Acme Coffee"
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "brand_123",
                            "names": {"edges": [{"node": {"name": "ACME COFFEE"}}]},
                            "count": 125,
                            "cardTransactions": {
                                "edges": [
                                    {
                                        "node": {
                                            "projectedQuantity": 2216172,
                                            "rawQuantity": 769903,
                                            "quantityType": "card_revenue_amount",
                                            "period": "12m",
                                            "periodStartDate": "2024-07-01",
                                            "periodEndDate": "2025-06-30",
                                        }
                                    }
                                ]
                            },
                            "operatingLocations": {
                                "edges": [
                                    {
                                        "node": {
                                            "names": {"edges": [{"node": {"name": "ACME COFFEE - DOWNTOWN"}}]},
                                            "addresses": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "fullAddress": "123 MAIN ST AUSTIN TX 78701",
                                                            "city": "AUSTIN",
                                                            "state": "TX",
                                                        }
                                                    }
                                                ]
                                            },
                                            "ranks": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "position": 3,
                                                            "cohortSize": 565,
                                                            "rank": "revenue_performance",
                                                            "quantityType": "card_revenue_amount",
                                                            "period": "12m",
                                                        }
                                                    }
                                                ]
                                            },
                                        }
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(
        input_data={
            "company_name": "Acme Coffee",
            "company_profile": {"company_domain": "acmecoffee.com"},
            "results": [{"noise": True}],
            "metadata": {"pipeline": "test"},
        }
    )

    assert result["operation_id"] == "company.enrich.card_revenue"
    assert result["status"] == "found"
    assert isinstance(result["provider_attempts"], list)
    assert len(result["provider_attempts"]) == 1
    assert isinstance(result.get("output"), dict)


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_missing_name_and_domain_failed():
    result = await execute_company_enrich_card_revenue(
        input_data={"company_profile": {"company_name": "ignored-not-top-level"}}
    )

    assert result["operation_id"] == "company.enrich.card_revenue"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name|company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_company_name_only_calls_enigma_name_only_search(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        search_input = json["variables"]["searchInput"]
        assert search_input["name"] == "Acme Name Only"
        assert "website" not in search_input
        return _FakeResponse(status_code=200, payload={"data": {"search": []}})

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(input_data={"company_name": "Acme Name Only"})

    assert result["status"] == "not_found"
    assert len(result["provider_attempts"]) == 1


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_success_validates_contract_and_extracts_nested_fields(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "5f1147ed-8e99-477d-827a-51094b2de153",
                            "enigmaId": "5f1147ed-8e99-477d-827a-51094b2de153",
                            "names": {"edges": [{"node": {"name": "STARBUCKS"}}]},
                            "count": 20153,
                            "cardTransactions": {
                                "edges": [
                                    {
                                        "node": {
                                            "projectedQuantity": 19980525299,
                                            "rawQuantity": 769903,
                                            "quantityType": "card_revenue_amount",
                                            "period": "12m",
                                            "periodStartDate": "2024-07-01",
                                            "periodEndDate": "2025-06-30",
                                        }
                                    }
                                ]
                            },
                            "operatingLocations": {
                                "edges": [
                                    {
                                        "node": {
                                            "names": {"edges": [{"node": {"name": "STARBUCKS"}}]},
                                            "addresses": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "fullAddress": "2401 UTAH AVE S # 8 SEATTLE WA 98134",
                                                            "city": "SEATTLE",
                                                            "state": "WA",
                                                        }
                                                    }
                                                ]
                                            },
                                            "ranks": {
                                                "edges": [
                                                    {
                                                        "node": {
                                                            "position": 1,
                                                            "cohortSize": 565,
                                                            "rank": "revenue_performance",
                                                            "quantityType": "card_revenue_amount",
                                                            "period": "12m",
                                                        }
                                                    }
                                                ]
                                            },
                                        }
                                    }
                                ]
                            },
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(
        input_data={"company_name": "Starbucks", "company_domain": "starbucks.com"}
    )
    validated = CardRevenueOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.enigma_brand_id == "5f1147ed-8e99-477d-827a-51094b2de153"
    assert validated.brand_name == "STARBUCKS"
    assert validated.location_count == 20153
    assert validated.annual_card_revenue == 19980525299
    assert validated.card_revenue_period == "12m"
    assert validated.card_revenue_period_start == "2024-07-01"
    assert validated.card_revenue_period_end == "2025-06-30"
    assert validated.top_location_name == "STARBUCKS"
    assert validated.top_location_address == "2401 UTAH AVE S # 8 SEATTLE WA 98134"
    assert validated.top_location_city == "SEATTLE"
    assert validated.top_location_state == "WA"
    assert validated.top_location_rank_position == 1
    assert validated.top_location_rank_cohort_size == 565
    assert validated.source_provider == "enigma"


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_empty_search_results_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(status_code=200, payload={"data": {"search": []}})

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(input_data={"company_name": "missing brand"})

    assert result["status"] == "not_found"
    assert "output" not in result
    assert len(result["provider_attempts"]) == 1


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_graphql_error_response_failed(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={
                "errors": [{"message": "Something went wrong"}],
                "data": {"search": None},
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(input_data={"company_name": "Acme"})

    assert result["status"] == "failed"
    assert "output" not in result
    assert len(result["provider_attempts"]) == 1
