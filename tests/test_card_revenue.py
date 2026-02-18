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
async def test_execute_company_enrich_card_revenue_match_found_with_analytics_validates_full_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)
    call_count = {"value": 0}

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        assert url == "https://api.enigma.com/graphql"
        assert headers["x-api-key"] == "test-enigma-key"
        call_count["value"] += 1
        if call_count["value"] == 1:
            assert "SearchBrand" in json["query"]
            assert json["variables"]["searchInput"] == {
                "entityType": "BRAND",
                "name": "Starbucks",
                "website": "starbucks.com",
            }
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
                            }
                        ]
                    }
                },
            )

        assert "GetBrandAnalytics" in json["query"]
        assert json["variables"]["searchInput"] == {
            "entityType": "BRAND",
            "id": "5f1147ed-8e99-477d-827a-51094b2de153",
        }
        assert json["variables"]["monthsBack"] == 12
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "5f1147ed-8e99-477d-827a-51094b2de153",
                            "namesConnection": {"edges": [{"node": {"name": "STARBUCKS"}}]},
                            "oneMonthCardRevenueAmountsConnection": {
                                "edges": [
                                    {"node": {"projectedQuantity": 101.25, "periodStartDate": "2025-01-01"}},
                                    {"node": {"projectedQuantity": 102.5, "periodStartDate": "2025-02-01"}},
                                ]
                            },
                            "twelveMonthCardRevenueAmountsConnection": {"edges": [{"node": {"projectedQuantity": 19980525299}}]},
                            "oneMonthCardRevenueYoyGrowthsConnection": {
                                "edges": [{"node": {"projectedQuantity": 0.12, "periodStartDate": "2025-01-01"}}]
                            },
                            "twelveMonthCardRevenueYoyGrowthsConnection": {"edges": [{"node": {"projectedQuantity": 0.15}}]},
                            "oneMonthCardCustomersAverageDailyCountsConnection": {
                                "edges": [{"node": {"projectedQuantity": 530.0, "periodStartDate": "2025-01-01"}}]
                            },
                            "twelveMonthCardCustomersAverageDailyCountsConnection": {"edges": [{"node": {"projectedQuantity": 500.0}}]},
                            "oneMonthCardTransactionsCountsConnection": {
                                "edges": [{"node": {"projectedQuantity": 8800.0, "periodStartDate": "2025-01-01"}}]
                            },
                            "twelveMonthCardTransactionsCountsConnection": {"edges": [{"node": {"projectedQuantity": 100000.0}}]},
                            "oneMonthAvgTransactionSizesConnection": {
                                "edges": [{"node": {"projectedQuantity": 14.22, "periodStartDate": "2025-01-01"}}]
                            },
                            "twelveMonthAvgTransactionSizesConnection": {"edges": [{"node": {"projectedQuantity": 14.75}}]},
                            "oneMonthRefundsAmountsConnection": {
                                "edges": [{"node": {"projectedQuantity": 12.5, "periodStartDate": "2025-01-01"}}]
                            },
                            "twelveMonthRefundsAmountsConnection": {"edges": [{"node": {"projectedQuantity": 150.25}}]},
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(
        input_data={"company_name": "Starbucks", "company_domain": "starbucks.com", "step_config": {"months_back": 12}}
    )
    validated = CardRevenueOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert call_count["value"] == 2
    assert len(result["provider_attempts"]) == 2
    assert result["provider_attempts"][0]["action"] == "match_business"
    assert result["provider_attempts"][1]["action"] == "get_card_analytics"
    assert validated.enigma_brand_id == "5f1147ed-8e99-477d-827a-51094b2de153"
    assert validated.brand_name == "STARBUCKS"
    assert validated.location_count == 20153
    assert validated.annual_card_revenue == 19980525299
    assert validated.annual_card_revenue_yoy_growth == 0.15
    assert validated.monthly_revenue is not None
    assert len(validated.monthly_revenue) == 2
    assert validated.monthly_revenue[0].period_start == "2025-01-01"
    assert validated.monthly_revenue[0].value == 101.25
    assert validated.monthly_refunds is not None
    assert validated.monthly_refunds[0].period_start == "2025-01-01"
    assert validated.monthly_refunds[0].value == 12.5
    assert validated.source_provider == "enigma"


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
async def test_execute_company_enrich_card_revenue_match_not_found_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        assert "SearchBrand" in json["query"]
        assert json["variables"]["searchInput"]["name"] == "missing brand"
        return _FakeResponse(status_code=200, payload={"data": {"search": []}})

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(input_data={"company_name": "missing brand"})
    assert result["status"] == "not_found"
    assert "output" not in result
    assert len(result["provider_attempts"]) == 1


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_match_found_but_analytics_fails_returns_partial_output(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)
    call_count = {"value": 0}

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        call_count["value"] += 1
        if call_count["value"] == 1:
            assert "SearchBrand" in json["query"]
            return _FakeResponse(
                status_code=200,
                payload={
                    "data": {
                        "search": [
                            {
                                "id": "brand_123",
                                "names": {"edges": [{"node": {"name": "ACME COFFEE"}}]},
                                "count": 125,
                            }
                        ]
                    }
                },
            )

        assert "GetBrandAnalytics" in json["query"]
        return _FakeResponse(status_code=200, payload={"errors": [{"message": "bad analytics field"}], "data": {"search": None}})

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(input_data={"company_name": "Acme"})
    validated = CardRevenueOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert call_count["value"] == 2
    assert len(result["provider_attempts"]) == 2
    assert result["provider_attempts"][1]["status"] == "failed"
    assert validated.enigma_brand_id == "brand_123"
    assert validated.brand_name == "ACME COFFEE"
    assert validated.location_count == 125
    assert validated.annual_card_revenue is None
    assert validated.monthly_revenue is None


@pytest.mark.asyncio
async def test_execute_company_enrich_card_revenue_noisy_input_returns_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_enigma_key(monkeypatch)
    call_count = {"value": 0}

    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers)
        call_count["value"] += 1
        if call_count["value"] == 1:
            assert "SearchBrand" in json["query"]
            assert json["variables"]["searchInput"]["website"] == "acmecoffee.com"
            return _FakeResponse(
                status_code=200,
                payload={
                    "data": {
                        "search": [
                            {
                                "id": "brand_999",
                                "names": {"edges": [{"node": {"name": "ACME COFFEE"}}]},
                                "count": 5,
                            }
                        ]
                    }
                },
            )
        return _FakeResponse(
            status_code=200,
            payload={
                "data": {
                    "search": [
                        {
                            "id": "brand_999",
                            "namesConnection": {"edges": [{"node": {"name": "ACME COFFEE"}}]},
                            "oneMonthCardRevenueAmountsConnection": {"edges": []},
                            "twelveMonthCardRevenueAmountsConnection": {"edges": [{"node": {"projectedQuantity": 1000}}]},
                            "oneMonthCardRevenueYoyGrowthsConnection": {"edges": []},
                            "twelveMonthCardRevenueYoyGrowthsConnection": {"edges": []},
                            "oneMonthCardCustomersAverageDailyCountsConnection": {"edges": []},
                            "twelveMonthCardCustomersAverageDailyCountsConnection": {"edges": []},
                            "oneMonthCardTransactionsCountsConnection": {"edges": []},
                            "twelveMonthCardTransactionsCountsConnection": {"edges": []},
                            "oneMonthAvgTransactionSizesConnection": {"edges": []},
                            "twelveMonthAvgTransactionSizesConnection": {"edges": []},
                            "oneMonthRefundsAmountsConnection": {"edges": []},
                            "twelveMonthRefundsAmountsConnection": {"edges": []},
                        }
                    ]
                }
            },
        )

    monkeypatch.setattr(enigma.httpx.AsyncClient, "post", _mock_post)

    result = await execute_company_enrich_card_revenue(
        input_data={
            "company_name": "Acme Coffee",
            "company_website": "https://www.acmecoffee.com/some/path",
            "results": [{"noise": True}],
            "metadata": {"pipeline": "test"},
            "step_config": {"months_back": "6"},
        }
    )

    assert result["operation_id"] == "company.enrich.card_revenue"
    assert result["status"] == "found"
    assert call_count["value"] == 2
    assert len(result["provider_attempts"]) == 2
    assert isinstance(result.get("output"), dict)
    assert result["output"]["enigma_brand_id"] == "brand_999"
    assert result["output"]["annual_card_revenue"] == 1000.0
