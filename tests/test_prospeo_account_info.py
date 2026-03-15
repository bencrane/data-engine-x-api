from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.providers.prospeo import get_account_information


@pytest.mark.asyncio
async def test_adapter_success():
    mock_response = SimpleNamespace(
        status_code=200,
        text='{"error": false, "response": {"current_plan": "STARTER", "remaining_credits": 99, "used_credits": 1, "current_team_members": 1, "next_quota_renewal_days": 25, "next_quota_renewal_date": "2023-06-18 20:52:28+00:00"}}',
        json=lambda: {
            "error": False,
            "response": {
                "current_plan": "STARTER",
                "remaining_credits": 99,
                "used_credits": 1,
                "current_team_members": 1,
                "next_quota_renewal_days": 25,
                "next_quota_renewal_date": "2023-06-18 20:52:28+00:00",
            },
        },
    )

    with patch("app.providers.prospeo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await get_account_information(api_key="test-key")

    assert result["error"] is False
    assert result["current_plan"] == "STARTER"
    assert result["remaining_credits"] == 99
    assert result["used_credits"] == 1


@pytest.mark.asyncio
async def test_adapter_missing_api_key():
    result = await get_account_information(api_key=None)
    assert result["error"] is True
    assert result["error_message"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_adapter_missing_api_key_empty_string():
    result = await get_account_information(api_key="")
    assert result["error"] is True
    assert result["error_message"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_adapter_upstream_error():
    mock_response = SimpleNamespace(
        status_code=401,
        text='{"error": true, "error_code": "INVALID_API_KEY"}',
        json=lambda: {"error": True, "error_code": "INVALID_API_KEY"},
    )

    with patch("app.providers.prospeo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await get_account_information(api_key="bad-key")

    assert result["error"] is True
    assert result["error_code"] == "INVALID_API_KEY"
    assert result["http_status"] == 401


def test_endpoint_success():
    from fastapi.testclient import TestClient

    from app.auth import AuthContext
    from app.main import app
    from app.routers.providers_v1 import _resolve_flexible_auth

    tenant_auth = AuthContext(
        org_id="org-1",
        company_id="co-1",
        user_id="u1",
        role="org_admin",
        auth_method="api_token",
    )
    app.dependency_overrides[_resolve_flexible_auth] = lambda: tenant_auth

    with patch("app.routers.providers_v1.get_account_information", new_callable=AsyncMock) as mock_adapter:
        mock_adapter.return_value = {
            "error": False,
            "current_plan": "STARTER",
            "remaining_credits": 99,
            "used_credits": 1,
        }
        try:
            client = TestClient(app)
            response = client.post("/api/v1/providers/prospeo/account")
            assert response.status_code == 200
            body = response.json()
            assert body["data"]["current_plan"] == "STARTER"
            assert body["data"]["remaining_credits"] == 99
        finally:
            app.dependency_overrides.pop(_resolve_flexible_auth, None)


def test_endpoint_missing_key():
    from fastapi.testclient import TestClient

    from app.auth import AuthContext
    from app.main import app
    from app.routers.providers_v1 import _resolve_flexible_auth

    tenant_auth = AuthContext(
        org_id="org-1",
        company_id="co-1",
        user_id="u1",
        role="org_admin",
        auth_method="api_token",
    )
    app.dependency_overrides[_resolve_flexible_auth] = lambda: tenant_auth

    with patch("app.routers.providers_v1.get_account_information", new_callable=AsyncMock) as mock_adapter:
        mock_adapter.return_value = {
            "error": True,
            "error_message": "missing_provider_api_key",
        }
        try:
            client = TestClient(app)
            response = client.post("/api/v1/providers/prospeo/account")
            assert response.status_code == 503
            assert "not configured" in response.json()["error"].lower() or "api key" in response.json()["error"].lower()
        finally:
            app.dependency_overrides.pop(_resolve_flexible_auth, None)
