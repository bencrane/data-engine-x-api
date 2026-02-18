from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.company_enrich import FMCSACarrierEnrichOutput
from app.contracts.search import FMCSACarrierSearchOutput
from app.providers import fmcsa
from app.services import company_operations, search_operations


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self) -> dict:
        return self._payload


def _set_fmcsa_key(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(fmcsa_api_key="test-fmcsa-key")
    monkeypatch.setattr(search_operations, "get_settings", lambda: settings)
    monkeypatch.setattr(company_operations, "get_settings", lambda: settings)


@pytest.mark.asyncio
async def test_execute_company_search_fmcsa_noisy_input_returns_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        assert "carriers/name/Acme%20Logistics" in url
        assert "webKey=test-fmcsa-key" in url
        assert "size=7" in url
        return _FakeResponse(
            status_code=200,
            payload={
                "content": [
                    {
                        "dotNumber": "12345",
                        "legalName": "Acme Logistics LLC",
                        "dbaName": "Acme",
                        "allowToOperate": "Y",
                        "phyCity": "Dallas",
                        "phyState": "TX",
                        "telephone": "555-0100",
                    }
                ]
            },
        )

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_fmcsa(
        input_data={
            "carrier_name": "Acme Logistics",
            "results": [{"noise": True}],
            "metadata": {"trace_id": "abc"},
            "step_config": {"max_results": 7},
        }
    )

    assert result["operation_id"] == "company.search.fmcsa"
    assert result["status"] == "found"
    assert isinstance(result["output"], dict)
    assert isinstance(result["provider_attempts"], list)


@pytest.mark.asyncio
async def test_execute_company_search_fmcsa_missing_name_failed():
    result = await search_operations.execute_company_search_fmcsa(
        input_data={"step_config": {"max_results": 10}, "results": [{"carrier_name": {"bad": True}}]}
    )

    assert result["operation_id"] == "company.search.fmcsa"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["carrier_name|company_name"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_search_fmcsa_success_validates_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        assert "carriers/name/Swift" in url
        return _FakeResponse(
            status_code=200,
            payload={
                "content": [
                    {
                        "dotNumber": "1001",
                        "legalName": "Swift Trucking",
                        "dbaName": "Swift",
                        "allowToOperate": True,
                        "phyCity": "Phoenix",
                        "phyState": "AZ",
                        "telephone": "555-1111",
                    },
                    {
                        "dotNumber": "1002",
                        "legalName": "Swift Freight",
                        "dbaName": None,
                        "allowToOperate": False,
                        "phyCity": "Tempe",
                        "phyState": "AZ",
                        "telephone": "555-2222",
                    },
                ]
            },
        )

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_fmcsa(input_data={"company_name": "Swift"})
    validated = FMCSACarrierSearchOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.result_count == 2
    assert validated.source_provider == "fmcsa"
    assert validated.results[0].dot_number == "1001"


@pytest.mark.asyncio
async def test_execute_company_search_fmcsa_empty_results_returns_not_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        _ = url
        return _FakeResponse(status_code=200, payload={"content": []})

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await search_operations.execute_company_search_fmcsa(input_data={"carrier_name": "Unknown Carrier"})

    assert result["status"] == "not_found"
    assert result["output"]["result_count"] == 0
    assert result["output"]["results"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_fmcsa_noisy_input_returns_structured_response(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        if "/basics?" in url:
            return _FakeResponse(
                status_code=200,
                payload={"content": [{"basic": "Unsafe Driving", "percentile": 55.2, "violationCount": 12}]},
            )
        if "/authority?" in url:
            return _FakeResponse(
                status_code=200,
                payload={"content": {"operatingStatus": "ACTIVE", "grantDate": "2018-01-01"}},
            )
        return _FakeResponse(
            status_code=200,
            payload={
                "content": {
                    "dotNumber": "90001",
                    "legalName": "Acme Carrier",
                    "allowToOperate": True,
                    "phyCity": "Houston",
                    "phyState": "TX",
                    "busVehicle": 4,
                    "vanVehicle": 5,
                    "passengerVehicle": 1,
                    "driverTotal": 77,
                }
            },
        )

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await company_operations.execute_company_enrich_fmcsa(
        input_data={
            "results": [{"dot_number": "90001"}],
            "timeline": {"noise": True},
            "step_config": {"ignored": True},
        }
    )

    assert result["operation_id"] == "company.enrich.fmcsa"
    assert result["status"] == "found"
    assert isinstance(result["output"], dict)
    assert isinstance(result["provider_attempts"], list)


@pytest.mark.asyncio
async def test_execute_company_enrich_fmcsa_missing_dot_number_failed():
    result = await company_operations.execute_company_enrich_fmcsa(input_data={"results": [{"dot_number": {"bad": True}}]})

    assert result["operation_id"] == "company.enrich.fmcsa"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["dot_number"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_fmcsa_success_validates_full_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        if "/basics?" in url:
            return _FakeResponse(
                status_code=200,
                payload={
                    "content": [
                        {
                            "basic": "Unsafe Driving",
                            "percentile": 67.5,
                            "violationCount": 21,
                            "seriousViolationCount": 3,
                            "deficiency": False,
                        }
                    ]
                },
            )
        if "/authority?" in url:
            return _FakeResponse(
                status_code=200,
                payload={"content": {"operatingStatus": "ACTIVE", "grantDate": "2020-10-03"}},
            )
        return _FakeResponse(
            status_code=200,
            payload={
                "content": {
                    "dotNumber": "777777",
                    "legalName": "Prime Carrier Inc",
                    "dbaName": "Prime Carrier",
                    "allowToOperate": True,
                    "outOfService": False,
                    "outOfServiceDate": None,
                    "busVehicle": 10,
                    "vanVehicle": 20,
                    "passengerVehicle": 5,
                    "phyStreet": "100 Main St",
                    "phyCity": "Nashville",
                    "phyState": "TN",
                    "phyZipcode": "37201",
                    "telephone": "555-9999",
                    "complaintCount": 4,
                    "driverTotal": 120,
                }
            },
        )

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await company_operations.execute_company_enrich_fmcsa(input_data={"dot_number": "777777"})
    validated = FMCSACarrierEnrichOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.dot_number == "777777"
    assert validated.total_power_units == 35
    assert validated.authority_status == "ACTIVE"
    assert validated.basic_scores is not None
    assert validated.basic_scores[0].category == "Unsafe Driving"
    assert validated.source_provider == "fmcsa"


@pytest.mark.asyncio
async def test_execute_company_enrich_fmcsa_basics_failure_returns_partial_found(
    monkeypatch: pytest.MonkeyPatch,
):
    _set_fmcsa_key(monkeypatch)

    async def _mock_get(self, url: str):  # noqa: ANN001
        if "/basics?" in url:
            return _FakeResponse(status_code=503, payload={"error": "temporarily unavailable"})
        if "/authority?" in url:
            return _FakeResponse(
                status_code=200,
                payload={"content": {"operatingStatus": "ACTIVE", "grantDate": "2015-05-20"}},
            )
        return _FakeResponse(
            status_code=200,
            payload={
                "content": {
                    "dotNumber": "888888",
                    "legalName": "Partial Carrier LLC",
                    "allowToOperate": True,
                    "busVehicle": 2,
                    "vanVehicle": 3,
                    "passengerVehicle": 0,
                    "driverTotal": 11,
                }
            },
        )

    monkeypatch.setattr(fmcsa.httpx.AsyncClient, "get", _mock_get)

    result = await company_operations.execute_company_enrich_fmcsa(input_data={"dot_number": "888888"})
    validated = FMCSACarrierEnrichOutput.model_validate(result["output"])

    assert result["status"] == "found"
    assert validated.dot_number == "888888"
    assert validated.basic_scores is None
    assert validated.authority_status == "ACTIVE"
    assert result["provider_attempts"][0]["provider_status"] == "partial"
