from __future__ import annotations

from typing import Any

import pytest

from app.contracts.icp_companies import FetchIcpCompaniesOutput
from app.providers.revenueinfra.fetch_icp_companies import fetch_icp_companies
from app.services.research_operations import execute_company_fetch_icp_candidates


@pytest.fixture(autouse=True)
def _mock_research_settings(monkeypatch):
    class _Settings:
        revenueinfra_api_url = "https://api.revenueinfra.com"

    monkeypatch.setattr(
        "app.services.research_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_fetch_icp_companies_success(monkeypatch):
    async def _fake_fetch_icp_companies(*, base_url: str, limit: int | None = None):
        assert isinstance(base_url, str)
        assert limit is None
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "fetch_icp_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "company_count": 3,
                "results": [
                    {
                        "company_name": "Abacus.AI",
                        "domain": "abacus.ai",
                        "company_description": "Abacus AI is the world's best AI super assistant...",
                    },
                    {
                        "company_name": "Tailscale",
                        "domain": "tailscale.com",
                        "company_description": "Tailscale develops a software-defined networking platform...",
                    },
                    {
                        "company_name": "Fivetran",
                        "domain": "fivetran.com",
                        "company_description": "Fivetran automates data movement from source systems to data platforms...",
                    },
                ],
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.fetch_icp_companies",
        _fake_fetch_icp_companies,
    )

    result = await execute_company_fetch_icp_candidates(input_data={})

    assert result["status"] == "found"
    validated = FetchIcpCompaniesOutput.model_validate(result["output"])
    assert validated.company_count == 3
    assert isinstance(validated.results, list)
    assert len(validated.results) == 3
    assert validated.results[0].company_name == "Abacus.AI"
    assert validated.results[0].domain == "abacus.ai"
    assert validated.results[0].company_description is not None
    assert validated.results[1].company_name == "Tailscale"
    assert validated.results[2].company_name == "Fivetran"


@pytest.mark.asyncio
async def test_fetch_icp_companies_empty(monkeypatch):
    async def _fake_fetch_icp_companies(*, base_url: str, limit: int | None = None):
        assert isinstance(base_url, str)
        assert limit is None
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "fetch_icp_companies",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "company_count": 0,
                "results": [],
            },
        }

    monkeypatch.setattr(
        "app.providers.revenueinfra.fetch_icp_companies",
        _fake_fetch_icp_companies,
    )

    result = await execute_company_fetch_icp_candidates(input_data={})

    assert result["status"] == "not_found"
    validated = FetchIcpCompaniesOutput.model_validate(result["output"])
    assert validated.company_count == 0
    assert validated.results == []


@pytest.mark.asyncio
async def test_fetch_icp_companies_with_limit(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"count":1,"data":[{}]}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "count": 1,
                "data": [
                    {
                        "id": 2,
                        "company_name": "Abacus.AI",
                        "domain": "abacus.ai",
                        "description": "Abacus AI is the world's best AI super assistant...",
                        "created_at": "2026-02-24T17:53:22.919167+00:00",
                    }
                ],
            }

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, json: dict[str, Any]):
            assert url == "https://api.revenueinfra.com/api/admin/temp/companies-for-parallel-icp"
            assert json == {"limit": 5}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.fetch_icp_companies.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await fetch_icp_companies(
        base_url="https://api.revenueinfra.com",
        limit=5,
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["company_count"] == 1


@pytest.mark.asyncio
async def test_fetch_icp_companies_http_error(monkeypatch):
    class _FakeResponse:
        status_code = 500
        text = '{"error":"server_error"}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {"error": "server_error"}

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, json: dict[str, Any]):
            assert url == "https://api.revenueinfra.com/api/admin/temp/companies-for-parallel-icp"
            assert json == {}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.fetch_icp_companies.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await fetch_icp_companies(
        base_url="https://api.revenueinfra.com",
    )

    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == 500
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_fetch_icp_companies_maps_description_to_company_description(monkeypatch):
    class _FakeResponse:
        status_code = 200
        text = '{"count":1,"data":[{}]}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "count": 1,
                "data": [
                    {
                        "id": 3,
                        "company_name": "Tailscale",
                        "domain": "tailscale.com",
                        "description": "Tailscale develops a software-defined networking platform...",
                        "created_at": "2026-02-24T17:53:22.919167+00:00",
                    }
                ],
            }

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, json: dict[str, Any]):
            assert url == "https://api.revenueinfra.com/api/admin/temp/companies-for-parallel-icp"
            assert json == {}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.providers.revenueinfra.fetch_icp_companies.httpx.AsyncClient",
        _FakeAsyncClient,
    )

    result = await fetch_icp_companies(
        base_url="https://api.revenueinfra.com",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["results"][0]["company_name"] == "Tailscale"
    assert result["mapped"]["results"][0]["company_description"] == (
        "Tailscale develops a software-defined networking platform..."
    )
