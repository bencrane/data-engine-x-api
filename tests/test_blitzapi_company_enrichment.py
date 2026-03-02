from __future__ import annotations

from typing import Any

import pytest

from app.providers import blitzapi
from app.services import company_operations


class _SettingsStub:
    blitzapi_api_key = "blitz-key"


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers: dict[str, str] = {}
        self.text = "{}"

    def json(self) -> dict[str, Any]:
        return self._payload


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(company_operations, "get_settings", lambda: _SettingsStub())


@pytest.mark.asyncio
async def test_enrich_company_missing_api_key() -> None:
    result = await blitzapi.enrich_company_profile(
        api_key=None,
        company_linkedin_url="https://www.linkedin.com/company/blitz-api",
    )
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_enrich_company_missing_linkedin_url() -> None:
    result = await blitzapi.enrich_company_profile(
        api_key="blitz-key",
        company_linkedin_url="   ",
    )
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_enrich_company_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = self
        assert method == "POST"
        assert url == "https://api.blitz-api.ai/v2/enrichment/company"
        assert headers["x-api-key"] == "blitz-key"
        assert json == {"company_linkedin_url": "https://www.linkedin.com/company/blitz-api"}
        return _FakeResponse(
            status_code=200,
            payload={
                "found": True,
                "company": {
                    "linkedin_url": "https://www.linkedin.com/company/blitz-api",
                    "linkedin_id": 108037802,
                    "name": "Blitzapi",
                    "about": "BlitzAPI provides enriched B2B data access through a suite of flexible and high-performance APIs...",
                    "specialties": None,
                    "industry": "Technology; Information and Internet",
                    "type": "Privately Held",
                    "size": "1-10",
                    "employees_on_linkedin": 3,
                    "followers": 6,
                    "founded_year": None,
                    "hq": {
                        "city": "Paris",
                        "country_code": "FR",
                    },
                    "domain": "blitz-api.ai",
                    "website": "https://blitz-api.ai",
                },
            },
        )

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await company_operations.execute_company_enrich_profile_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/blitz-api"}
    )

    assert result["status"] == "found"
    assert result["output"]["company_linkedin_id"] == "108037802"
    assert result["output"]["company_name"] == "Blitzapi"
    assert result["output"]["description_raw"].startswith("BlitzAPI provides enriched B2B data access")
    assert result["output"]["company_domain"] == "blitz-api.ai"
    assert result["output"]["hq_locality"] == "Paris"
    assert result["output"]["hq_country_code"] == "FR"


@pytest.mark.asyncio
async def test_enrich_company_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        return _FakeResponse(status_code=200, payload={"found": False})

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await company_operations.execute_company_enrich_profile_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/missing"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_enrich_company_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        return _FakeResponse(status_code=500, payload={"success": False, "message": "error"})

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)

    result = await company_operations.execute_company_enrich_profile_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/blitz-api"}
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_enrich_company_domain_bridge(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str | None]] = []

    async def _stub_resolve_linkedin_from_domain(*, api_key: str | None, domain: str | None) -> dict[str, Any]:
        assert api_key == "blitz-key"
        calls.append(("resolve", domain))
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "resolve_linkedin_from_domain",
                "status": "found",
            },
            "mapped": {
                "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
            },
        }

    async def _stub_enrich_company_profile(*, api_key: str | None, company_linkedin_url: str | None) -> dict[str, Any]:
        assert api_key == "blitz-key"
        calls.append(("enrich", company_linkedin_url))
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "enrich_company_profile",
                "status": "found",
            },
            "mapped": {
                "company_name": "Blitzapi",
                "company_domain": "blitz-api.ai",
                "company_website": "https://blitz-api.ai",
                "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
                "company_linkedin_id": "108037802",
                "company_type": "Privately Held",
                "industry_primary": "Technology; Information and Internet",
                "employee_count": 3,
                "employee_range": "1-10",
                "founded_year": None,
                "hq_locality": "Paris",
                "hq_country_code": "FR",
                "description_raw": "desc",
                "specialties": None,
                "follower_count": 6,
                "source_provider": "blitzapi",
            },
        }

    monkeypatch.setattr(company_operations.blitzapi, "resolve_linkedin_from_domain", _stub_resolve_linkedin_from_domain)
    monkeypatch.setattr(company_operations.blitzapi, "enrich_company_profile", _stub_enrich_company_profile)

    result = await company_operations.execute_company_enrich_profile_blitzapi(
        input_data={"company_domain": "blitz-api.ai"}
    )
    assert result["status"] == "found"
    assert calls == [
        ("resolve", "blitz-api.ai"),
        ("enrich", "https://www.linkedin.com/company/blitz-api"),
    ]


@pytest.mark.asyncio
async def test_enrich_company_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_enrich_company_profile(*, api_key: str | None, company_linkedin_url: str | None) -> dict[str, Any]:
        assert api_key == "blitz-key"
        assert company_linkedin_url == "https://www.linkedin.com/company/blitz-api"
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "enrich_company_profile",
                "status": "found",
            },
            "mapped": {
                "company_name": "Blitzapi",
                "company_domain": "blitz-api.ai",
                "company_website": "https://blitz-api.ai",
                "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
                "company_linkedin_id": "108037802",
                "company_type": "Privately Held",
                "industry_primary": "Technology; Information and Internet",
                "employee_count": 3,
                "employee_range": "1-10",
                "founded_year": None,
                "hq_locality": "Paris",
                "hq_country_code": "FR",
                "description_raw": "desc",
                "specialties": None,
                "follower_count": 6,
                "source_provider": "blitzapi",
            },
        }

    monkeypatch.setattr(company_operations.blitzapi, "enrich_company_profile", _stub_enrich_company_profile)

    result = await company_operations.execute_company_enrich_profile_blitzapi(
        input_data={"cumulative_context": {"linkedin_url": "https://www.linkedin.com/company/blitz-api"}}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://www.linkedin.com/company/blitz-api"
