from __future__ import annotations

from typing import Any

import pytest

from app.providers import blitzapi


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.mark.asyncio
async def test_retry_on_429_succeeds_on_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(status_code=429, payload={"error": "rate_limited"}),
        _FakeResponse(
            status_code=200,
            payload={
                "found": True,
                "company": {
                    "name": "Acme",
                    "domain": "acme.com",
                    "website": "https://acme.com",
                    "linkedin_url": "https://www.linkedin.com/company/acme",
                },
            },
        ),
    ]
    call_count = {"count": 0}

    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        response = responses[call_count["count"]]
        call_count["count"] += 1
        return response

    async def _mock_sleep(delay: float) -> None:
        _ = delay

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    monkeypatch.setattr(blitzapi.asyncio, "sleep", _mock_sleep)

    result = await blitzapi.company_search(
        api_key="blitz-key",
        company_linkedin_url="https://www.linkedin.com/company/acme",
    )

    assert call_count["count"] == 2
    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["results"][0]["company_domain"] == "acme.com"


@pytest.mark.asyncio
async def test_retry_on_429_respects_retry_after_header(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        _FakeResponse(status_code=429, payload={"error": "rate_limited"}, headers={"retry-after": "1"}),
        _FakeResponse(
            status_code=200,
            payload={
                "found": True,
                "company": {
                    "name": "Acme",
                    "domain": "acme.com",
                    "linkedin_url": "https://www.linkedin.com/company/acme",
                },
            },
        ),
    ]
    sleep_calls: list[float] = []
    call_count = {"count": 0}

    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        response = responses[call_count["count"]]
        call_count["count"] += 1
        return response

    async def _mock_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    monkeypatch.setattr(blitzapi.asyncio, "sleep", _mock_sleep)

    result = await blitzapi.company_search(
        api_key="blitz-key",
        company_linkedin_url="https://www.linkedin.com/company/acme",
    )

    assert result["attempt"]["status"] == "found"
    assert sleep_calls == [1.0]


@pytest.mark.asyncio
async def test_retry_exhausted_returns_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"count": 0}

    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        call_count["count"] += 1
        return _FakeResponse(status_code=429, payload={"error": "rate_limited_after_retries"})

    async def _mock_sleep(delay: float) -> None:
        _ = delay

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    monkeypatch.setattr(blitzapi.asyncio, "sleep", _mock_sleep)

    result = await blitzapi.company_search(
        api_key="blitz-key",
        company_linkedin_url="https://www.linkedin.com/company/acme",
    )

    assert call_count["count"] == 4
    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == 429
    assert "rate_limited" in str(result["attempt"]["raw_response"])


@pytest.mark.asyncio
async def test_non_429_errors_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = {"count": 0}

    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        call_count["count"] += 1
        return _FakeResponse(status_code=500, payload={"error": "server_error"})

    async def _mock_sleep(delay: float) -> None:
        _ = delay

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    monkeypatch.setattr(blitzapi.asyncio, "sleep", _mock_sleep)

    result = await blitzapi.company_search(
        api_key="blitz-key",
        company_linkedin_url="https://www.linkedin.com/company/acme",
    )

    assert call_count["count"] == 1
    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == 500
