from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.auth.models import AuthContext
from app.contracts.fmcsa_socrata import FMCSASocrataQueryOutput
from app.providers import socrata
from app.routers import execute_v1
from app.services import fmcsa_socrata_operations as operations


class _FakeResponse:
    def __init__(self, *, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def _set_socrata_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = SimpleNamespace(
        socrata_api_key_id="test-key-id",
        socrata_api_key_secret="test-key-secret",
    )
    monkeypatch.setattr(operations, "get_settings", lambda: settings)


@pytest.mark.asyncio
async def test_query_dataset_posts_to_expected_endpoint_with_basic_auth_and_query_payload(
    monkeypatch: pytest.MonkeyPatch,
):
    auth_capture: dict[str, str] = {}
    request_capture: dict[str, object] = {}

    class _FakeBasicAuth:
        def __init__(self, username: str, password: str):
            auth_capture["username"] = username
            auth_capture["password"] = password

    class _FakeAsyncClient:
        def __init__(self, *, timeout, auth):
            request_capture["timeout"] = timeout
            request_capture["auth"] = auth

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, json):
            request_capture["url"] = url
            request_capture["json"] = json
            return _FakeResponse(status_code=200, payload=[{"dot_number": "123456"}])

    monkeypatch.setattr(socrata.httpx, "BasicAuth", _FakeBasicAuth)
    monkeypatch.setattr(socrata.httpx, "AsyncClient", _FakeAsyncClient)

    result = await socrata.query_dataset(
        dataset_id="az4n-8mr2",
        query="SELECT * WHERE `DOT_NUMBER` = 123456",
        api_key_id="test-key-id",
        api_key_secret="test-key-secret",
    )

    assert auth_capture == {
        "username": "test-key-id",
        "password": "test-key-secret",
    }
    assert request_capture["url"] == "https://data.transportation.gov/api/v3/views/az4n-8mr2/query.json"
    assert request_capture["json"] == {"query": "SELECT * WHERE `DOT_NUMBER` = 123456"}
    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["rows"] == [{"dot_number": "123456"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_provider_status"),
    [
        (400, "bad_request"),
        (429, "rate_limited"),
        (500, "server_error"),
    ],
)
async def test_query_dataset_maps_http_failures(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_provider_status: str,
):
    class _FakeAsyncClient:
        def __init__(self, *, timeout, auth):
            self.timeout = timeout
            self.auth = auth

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url: str, json):
            _ = (url, json)
            return _FakeResponse(status_code=status_code, payload={"message": "failed"})

    monkeypatch.setattr(socrata.httpx, "AsyncClient", _FakeAsyncClient)

    result = await socrata.query_dataset(
        dataset_id="sa6p-acbp",
        query="SELECT * WHERE `DOCKET_NUMBER` = 'MC012345'",
        api_key_id="id",
        api_key_secret="secret",
    )

    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == status_code
    assert result["attempt"]["provider_status"] == expected_provider_status
    assert result["mapped"]["rows"] == []


@pytest.mark.asyncio
async def test_company_census_wrapper_returns_missing_inputs_when_no_identifier(monkeypatch: pytest.MonkeyPatch):
    _set_socrata_settings(monkeypatch)

    result = await operations.execute_company_enrich_fmcsa_company_census(
        input_data={"dot_number": {"bad": True}, "mc_number": []}
    )

    assert result["operation_id"] == "company.enrich.fmcsa.company_census"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["dot_number|mc_number"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executor", "input_data", "expected_dataset_id", "expected_query"),
    [
        (
            operations.execute_company_enrich_fmcsa_company_census,
            {"dot_number": "123456"},
            "az4n-8mr2",
            "SELECT * WHERE `DOT_NUMBER` = 123456",
        ),
        (
            operations.execute_company_enrich_fmcsa_carrier_all_history,
            {"dot_number": "123456"},
            "6eyk-hxee",
            "SELECT * WHERE `DOT_NUMBER` = '123456'",
        ),
        (
            operations.execute_company_enrich_fmcsa_revocation_all_history,
            {"dot_number": "123456"},
            "sa6p-acbp",
            "SELECT * WHERE `DOT_NUMBER` = '123456'",
        ),
    ],
)
async def test_wrappers_map_dot_lookup_to_expected_dataset_field(
    monkeypatch: pytest.MonkeyPatch,
    executor,
    input_data: dict[str, object],
    expected_dataset_id: str,
    expected_query: str,
):
    _set_socrata_settings(monkeypatch)
    captured: dict[str, str] = {}

    async def _fake_query_dataset(**kwargs):
        captured["dataset_id"] = kwargs["dataset_id"]
        captured["query"] = kwargs["query"]
        return {
            "attempt": {"provider": "socrata", "action": "query_dataset", "status": "found"},
            "mapped": {"rows": [{"id": 1}]},
        }

    monkeypatch.setattr(operations.socrata, "query_dataset", _fake_query_dataset)

    result = await executor(input_data=input_data)

    assert captured["dataset_id"] == expected_dataset_id
    assert captured["query"] == expected_query
    assert result["status"] == "found"
    assert result["output"]["result_count"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("executor", "input_data", "expected_dataset_id", "expected_query"),
    [
        (
            operations.execute_company_enrich_fmcsa_company_census,
            {"mc_number": "12345"},
            "az4n-8mr2",
            "SELECT * WHERE (`DOCKET1PREFIX` = 'MC' AND `DOCKET1` = 12345) OR (`DOCKET2PREFIX` = 'MC' AND `DOCKET2` = 12345) OR (`DOCKET3PREFIX` = 'MC' AND `DOCKET3` = 12345)",
        ),
        (
            operations.execute_company_enrich_fmcsa_carrier_all_history,
            {"mc_number": "12345"},
            "6eyk-hxee",
            "SELECT * WHERE `DOCKET_NUMBER` = 'MC012345'",
        ),
        (
            operations.execute_company_enrich_fmcsa_revocation_all_history,
            {"mc_number": "12345"},
            "sa6p-acbp",
            "SELECT * WHERE `DOCKET_NUMBER` = 'MC012345'",
        ),
        (
            operations.execute_company_enrich_fmcsa_insur_all_history,
            {"mc_number": "12345"},
            "ypjt-5ydn",
            "SELECT * WHERE `prefix_docket_number` = 'MC012345'",
        ),
    ],
)
async def test_wrappers_map_mc_lookup_correctly(
    monkeypatch: pytest.MonkeyPatch,
    executor,
    input_data: dict[str, object],
    expected_dataset_id: str,
    expected_query: str,
):
    _set_socrata_settings(monkeypatch)
    captured: dict[str, str] = {}

    async def _fake_query_dataset(**kwargs):
        captured["dataset_id"] = kwargs["dataset_id"]
        captured["query"] = kwargs["query"]
        return {
            "attempt": {"provider": "socrata", "action": "query_dataset", "status": "found"},
            "mapped": {"rows": [{"id": 1}, {"id": 2}]},
        }

    monkeypatch.setattr(operations.socrata, "query_dataset", _fake_query_dataset)

    result = await executor(input_data=input_data)

    assert captured["dataset_id"] == expected_dataset_id
    assert captured["query"] == expected_query
    assert result["status"] == "found"
    assert result["output"]["identifier_type_used"] == "mc_number"
    assert result["output"]["result_count"] == 2


def test_shared_output_contract_validates_dataset_native_rows():
    output = FMCSASocrataQueryOutput.model_validate(
        {
            "dataset_name": "Carrier - All With History",
            "dataset_id": "6eyk-hxee",
            "identifier_type_used": "dot_number",
            "identifier_value_used": "123456",
            "result_count": 1,
            "matched_rows": [{"DOT_NUMBER": "123456", "LEGAL_NAME": "Acme"}],
            "source_provider": "socrata",
        }
    )

    assert output.dataset_id == "6eyk-hxee"
    assert output.identifier_type_used == "dot_number"
    assert output.matched_rows[0]["LEGAL_NAME"] == "Acme"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation_id", "handler_name"),
    [
        ("company.enrich.fmcsa.company_census", "execute_company_enrich_fmcsa_company_census"),
        ("company.enrich.fmcsa.carrier_all_history", "execute_company_enrich_fmcsa_carrier_all_history"),
        ("company.enrich.fmcsa.revocation_all_history", "execute_company_enrich_fmcsa_revocation_all_history"),
        ("company.enrich.fmcsa.insur_all_history", "execute_company_enrich_fmcsa_insur_all_history"),
    ],
)
async def test_execute_v1_routes_new_fmcsa_socrata_operations(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    handler_name: str,
):
    fake_result = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "operation_id": operation_id,
        "status": "found",
        "output": {
            "dataset_name": "Test",
            "dataset_id": "test-id",
            "identifier_type_used": "dot_number",
            "identifier_value_used": "123",
            "result_count": 0,
            "matched_rows": [],
            "source_provider": "socrata",
        },
        "provider_attempts": [],
    }
    handler = AsyncMock(return_value=fake_result)
    persist_calls: list[dict] = []

    monkeypatch.setattr(execute_v1, handler_name, handler)
    monkeypatch.setattr(execute_v1, "persist_operation_execution", lambda **kwargs: persist_calls.append(kwargs))

    payload = execute_v1.ExecuteV1Request(
        operation_id=operation_id,
        entity_type="company",
        input={"dot_number": "123456"},
    )
    auth = AuthContext(
        user_id="11111111-1111-1111-1111-111111111111",
        org_id="22222222-2222-2222-2222-222222222222",
        company_id="33333333-3333-3333-3333-333333333333",
        role="org_admin",
        auth_method="api_token",
    )

    response = await execute_v1.execute_v1(payload, auth)

    assert operation_id in execute_v1.SUPPORTED_OPERATION_IDS
    assert response.data == fake_result
    assert handler.await_count == 1
    assert len(persist_calls) == 1
    assert persist_calls[0]["operation_id"] == operation_id


def test_authhist_wrapper_is_not_exposed_in_supported_operation_ids():
    assert "company.enrich.fmcsa.authhist_all_history" not in execute_v1.SUPPORTED_OPERATION_IDS
