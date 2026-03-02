from __future__ import annotations

from typing import Any

import pytest

from app.providers import blitzapi
from app.services import resolve_operations


class _SettingsStub:
    blitzapi_api_key = "blitz-key"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(resolve_operations, "get_settings", lambda: _SettingsStub())


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = {}
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_resolve_linkedin_missing_api_key() -> None:
    result = await blitzapi.resolve_linkedin_from_domain(api_key=None, domain="vanta.com")
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_resolve_linkedin_missing_domain() -> None:
    result = await blitzapi.resolve_linkedin_from_domain(api_key="blitz-key", domain="   ")
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_resolve_linkedin_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = self
        assert method == "POST"
        assert url == "https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin"
        assert headers["x-api-key"] == "blitz-key"
        assert json == {"domain": "vanta.com"}
        return _FakeResponse(
            status_code=200,
            payload={
                "found": True,
                "company_linkedin_url": "https://www.linkedin.com/company/vanta-security",
            },
        )

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await resolve_operations.execute_company_resolve_linkedin_from_domain_blitzapi(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://www.linkedin.com/company/vanta-security"


@pytest.mark.asyncio
async def test_resolve_linkedin_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        return _FakeResponse(status_code=200, payload={"found": False})

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await resolve_operations.execute_company_resolve_linkedin_from_domain_blitzapi(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_linkedin_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        return _FakeResponse(status_code=500, payload={"success": False, "message": "error"})

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await resolve_operations.execute_company_resolve_linkedin_from_domain_blitzapi(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "failed"
    assert result["provider_attempts"][0]["http_status"] == 500


@pytest.mark.asyncio
async def test_resolve_linkedin_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_resolve_linkedin_from_domain(*, api_key: str | None, domain: str | None) -> dict[str, Any]:
        assert api_key == "blitz-key"
        assert domain == "vanta.com"
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "resolve_linkedin_from_domain",
                "status": "found",
            },
            "mapped": {
                "company_linkedin_url": "https://www.linkedin.com/company/vanta-security",
                "resolve_source": "blitzapi",
            },
        }

    monkeypatch.setattr(resolve_operations.blitzapi, "resolve_linkedin_from_domain", _stub_resolve_linkedin_from_domain)

    result = await resolve_operations.execute_company_resolve_linkedin_from_domain_blitzapi(
        input_data={"cumulative_context": {"company_domain": "vanta.com"}}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://www.linkedin.com/company/vanta-security"
