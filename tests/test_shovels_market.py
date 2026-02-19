from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.shovels import (
    ShovelsAddressSearchOutput,
    ShovelsGeoDetailOutput,
    ShovelsGeoSearchOutput,
    ShovelsMetricsCurrentOutput,
    ShovelsMetricsMonthlyOutput,
)
from app.services import shovels_operations
from app.services.shovels_operations import (
    execute_address_search,
    execute_market_geo_detail,
    execute_market_metrics_current,
    execute_market_metrics_monthly,
    execute_market_search_cities,
)


def _set_shovels_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shovels_operations,
        "get_settings",
        lambda: SimpleNamespace(shovels_api_key="test-shovels-key"),
    )


@pytest.mark.asyncio
async def test_execute_market_search_cities_missing_state_failed():
    result = await execute_market_search_cities(
        input_data={
            "step_config": {"name_contains": "san"},
            "noise": {"irrelevant": True},
        }
    )

    assert result["operation_id"] == "market.search.cities"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["state"]


@pytest.mark.asyncio
async def test_execute_market_search_cities_success_validates_geo_output(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_search_cities(
        *,
        api_key: str | None,
        state: str | None,
        name_contains: str | None = None,
        size: int | None = None,
    ):
        assert api_key == "test-shovels-key"
        assert state == "CA"
        assert name_contains == "san"
        assert size == 25
        return {
            "attempt": {
                "provider": "shovels",
                "action": "market_search_cities_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {"geo_id": "city_1", "name": "SAN FRANCISCO, CA", "state": "CA"},
                    {"geo_id": "city_2", "name": "SAN DIEGO, CA", "state": "CA"},
                ],
                "result_count": 2,
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_cities", _fake_search_cities)

    result = await execute_market_search_cities(
        input_data={
            "step_config": {"state": "CA", "name_contains": "san", "size": 25},
            "cumulative_context": {"noise": {"path": ["a", "b"]}},
        }
    )

    validated = ShovelsGeoSearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 2
    assert validated.results[0].geo_id == "city_1"


@pytest.mark.asyncio
async def test_execute_market_metrics_monthly_missing_geo_id_failed():
    result = await execute_market_metrics_monthly(
        input_data={
            "step_config": {
                "geo_type": "city",
                "metric": "permit_count",
                "start_date": "2025-01-01",
                "end_date": "2025-03-01",
            }
        }
    )

    assert result["operation_id"] == "market.enrich.metrics_monthly"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert "geo_id" in result["missing_inputs"]


@pytest.mark.asyncio
async def test_execute_market_metrics_monthly_success_validates_data_points(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_city_metrics_monthly(
        *,
        api_key: str | None,
        geo_id: str | None,
        metric: str | None,
        start_date: str | None,
        end_date: str | None,
    ):
        assert api_key == "test-shovels-key"
        assert geo_id == "city_1"
        assert metric == "permit_count"
        assert start_date == "2025-01-01"
        assert end_date == "2025-03-01"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "market_city_metrics_monthly_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "geo_id": "city_1",
                "metric": "permit_count",
                "data_points": [
                    {"month": "2025-01-01", "value": 42},
                    {"month": "2025-02-01", "value": 55},
                ],
            },
        }

    monkeypatch.setattr(
        shovels_operations.shovels,
        "get_city_metrics_monthly",
        _fake_city_metrics_monthly,
    )

    result = await execute_market_metrics_monthly(
        input_data={
            "step_config": {
                "geo_type": "city",
                "metric": "permit_count",
                "start_date": "2025-01-01",
                "end_date": "2025-03-01",
            },
            "cumulative_context": {"results": [{"geo_id": "city_1"}], "noise": {"x": 1}},
        }
    )

    validated = ShovelsMetricsMonthlyOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.geo_id == "city_1"
    assert len(validated.data_points) == 2
    assert validated.data_points[0].value == 42


@pytest.mark.asyncio
async def test_execute_market_metrics_current_success_validates_current_output(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_county_metrics_current(*, api_key: str | None, geo_id: str | None):
        assert api_key == "test-shovels-key"
        assert geo_id == "county_1"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "market_county_metrics_current_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "geo_id": "county_1",
                "metrics": {
                    "permit_count": 210,
                    "contractor_count": 85,
                    "avg_approval_duration": 12,
                },
            },
        }

    monkeypatch.setattr(
        shovels_operations.shovels,
        "get_county_metrics_current",
        _fake_county_metrics_current,
    )

    result = await execute_market_metrics_current(
        input_data={
            "step_config": {"geo_type": "county"},
            "cumulative_context": {"output": {"geo_id": "county_1"}},
        }
    )

    validated = ShovelsMetricsCurrentOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.geo_id == "county_1"
    assert validated.metrics["permit_count"] == 210


@pytest.mark.asyncio
async def test_execute_market_geo_detail_success_validates_detail_output(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_jurisdiction_detail(*, api_key: str | None, geo_id: str | None):
        assert api_key == "test-shovels-key"
        assert geo_id == "jur_1"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "market_jurisdiction_detail_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "geo_id": "jur_1",
                "name": "SAN FRANCISCO, CA",
                "state": "CA",
                "details": {
                    "cities": {"SAN FRANCISCO": "city_1"},
                    "counties": {"SAN FRANCISCO": "county_1"},
                    "zipcodes": ["94103", "94107"],
                },
            },
        }

    monkeypatch.setattr(
        shovels_operations.shovels,
        "get_jurisdiction_details",
        _fake_jurisdiction_detail,
    )

    result = await execute_market_geo_detail(
        input_data={
            "step_config": {"geo_type": "jurisdiction"},
            "cumulative_context": {"results": [{"geo_id": "jur_1"}]},
        }
    )

    validated = ShovelsGeoDetailOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.geo_id == "jur_1"
    assert validated.details["cities"]["SAN FRANCISCO"] == "city_1"


@pytest.mark.asyncio
async def test_execute_address_search_success_validates_address_output(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_address_search(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["q"] == "123 Market St"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "address_search_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "geo_id": "addr_1",
                        "address": "123 Market St, San Francisco, CA",
                        "city": "SAN FRANCISCO",
                        "state": "CA",
                        "zip_code": "94103",
                        "property_type": "commercial",
                    }
                ],
                "result_count": 1,
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_addresses", _fake_address_search)

    result = await execute_address_search(
        input_data={
            "step_config": {"q": "123 Market St", "state": "CA", "size": 20},
            "noise": {"trace_id": "abc123"},
        }
    )

    validated = ShovelsAddressSearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.results[0].geo_id == "addr_1"


@pytest.mark.asyncio
async def test_shovels_market_operations_handle_noisy_input_across_all(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_search_cities(*, api_key: str | None, state: str | None, name_contains: str | None = None, size: int | None = None):
        assert api_key == "test-shovels-key"
        assert state == "CA"
        assert name_contains == "san"
        assert size == 50
        return {
            "attempt": {"provider": "shovels", "action": "market_search_cities_shovels", "status": "found"},
            "mapped": {"results": [{"geo_id": "city_noise_1", "name": "SAN JOSE, CA", "state": "CA"}], "result_count": 1},
        }

    async def _fake_city_metrics_monthly(*, api_key: str | None, geo_id: str | None, metric: str | None, start_date: str | None, end_date: str | None):
        assert api_key == "test-shovels-key"
        assert geo_id == "city_noise_1"
        assert metric == "permit_count"
        assert start_date == "2025-01-01"
        assert end_date == "2025-02-01"
        return {
            "attempt": {"provider": "shovels", "action": "market_city_metrics_monthly_shovels", "status": "found"},
            "mapped": {"geo_id": "city_noise_1", "metric": "permit_count", "data_points": [{"month": "2025-01-01", "value": 12}]},
        }

    async def _fake_city_metrics_current(*, api_key: str | None, geo_id: str | None):
        assert api_key == "test-shovels-key"
        assert geo_id == "city_noise_1"
        return {
            "attempt": {"provider": "shovels", "action": "market_city_metrics_current_shovels", "status": "found"},
            "mapped": {"geo_id": "city_noise_1", "metrics": {"permit_count": 99}},
        }

    async def _fake_city_detail(*, api_key: str | None, geo_id: str | None):
        assert api_key == "test-shovels-key"
        assert geo_id == "city_noise_1"
        return {
            "attempt": {"provider": "shovels", "action": "market_city_detail_shovels", "status": "found"},
            "mapped": {"geo_id": "city_noise_1", "name": "SAN JOSE, CA", "state": "CA", "details": {"counties": {"SANTA CLARA": "county_1"}}},
        }

    async def _fake_address_search(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["q"] == "1 Infinite Loop"
        return {
            "attempt": {"provider": "shovels", "action": "address_search_shovels", "status": "found"},
            "mapped": {"results": [{"geo_id": "addr_noise_1", "address": "1 Infinite Loop, Cupertino, CA", "state": "CA"}], "result_count": 1},
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_cities", _fake_search_cities)
    monkeypatch.setattr(shovels_operations.shovels, "get_city_metrics_monthly", _fake_city_metrics_monthly)
    monkeypatch.setattr(shovels_operations.shovels, "get_city_metrics_current", _fake_city_metrics_current)
    monkeypatch.setattr(shovels_operations.shovels, "get_city_details", _fake_city_detail)
    monkeypatch.setattr(shovels_operations.shovels, "search_addresses", _fake_address_search)

    noisy_context = {
        "results": [{"geo_id": "city_noise_1"}],
        "output": {"geo_id": "city_noise_1"},
        "history": [{"step": "a"}, {"step": "b"}],
        "noise_blob": {"nested": [1, {"x": True}]},
    }

    city_search_result = await execute_market_search_cities(
        input_data={"step_config": {"state": "CA", "name_contains": "san"}, "cumulative_context": noisy_context}
    )
    monthly_result = await execute_market_metrics_monthly(
        input_data={
            "step_config": {
                "geo_type": "city",
                "metric": "permit_count",
                "start_date": "2025-01-01",
                "end_date": "2025-02-01",
            },
            "cumulative_context": noisy_context,
        }
    )
    current_result = await execute_market_metrics_current(
        input_data={"step_config": {"geo_type": "city"}, "cumulative_context": noisy_context}
    )
    detail_result = await execute_market_geo_detail(
        input_data={"step_config": {"geo_type": "city"}, "cumulative_context": noisy_context}
    )
    address_result = await execute_address_search(
        input_data={"step_config": {"q": "1 Infinite Loop", "state": "CA"}, "cumulative_context": noisy_context}
    )

    assert city_search_result["status"] == "found"
    assert monthly_result["status"] == "found"
    assert current_result["status"] == "found"
    assert detail_result["status"] == "found"
    assert address_result["status"] == "found"
