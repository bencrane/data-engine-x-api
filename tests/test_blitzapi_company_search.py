from __future__ import annotations

from typing import Any

import pytest

from app.providers import blitzapi
from app.services import blitzapi_company_search


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
    monkeypatch.setattr(blitzapi_company_search, "get_settings", lambda: _SettingsStub())


@pytest.mark.asyncio
async def test_search_companies_missing_api_key() -> None:
    result = await blitzapi.search_companies(api_key=None, company_filters={"keywords": {"include": ["SaaS"], "exclude": []}})
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_search_companies_no_filters() -> None:
    result = await blitzapi_company_search.execute_company_search_blitzapi(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_filters"]


@pytest.mark.asyncio
async def test_search_companies_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_companies(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["api_key"] == "blitz-key"
        return {
            "attempt": {"provider": "blitzapi", "action": "search_companies", "status": "found"},
            "mapped": {
                "results": [
                    {
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
                        "description_raw": "BlitzAPI provides enriched B2B data access...",
                        "specialties": None,
                        "follower_count": 6,
                        "source_provider": "blitzapi",
                    },
                    {
                        "company_name": "Acme Cloud",
                        "company_domain": "acmecloud.com",
                        "company_website": "https://acmecloud.com",
                        "company_linkedin_url": "https://www.linkedin.com/company/acme-cloud",
                        "company_linkedin_id": "222222",
                        "company_type": "Privately Held",
                        "industry_primary": "Software Development",
                        "employee_count": 150,
                        "employee_range": "51-200",
                        "founded_year": 2018,
                        "hq_locality": "New York",
                        "hq_country_code": "US",
                        "description_raw": "Cloud infrastructure company",
                        "specialties": ["IaaS"],
                        "follower_count": 2000,
                        "source_provider": "blitzapi",
                    },
                ],
                "pagination": {
                    "cursor": "eyJwYWdlIjoyLCJzZWFyY2hfaWQiOiJhYmMxMjMifQ==",
                    "totalItems": 148,
                    "pageItems": 2,
                },
            },
        }

    monkeypatch.setattr(blitzapi_company_search.blitzapi, "search_companies", _stub_search_companies)
    result = await blitzapi_company_search.execute_company_search_blitzapi(
        input_data={"company_filters": {"keywords": {"include": ["SaaS"], "exclude": []}}}
    )

    assert result["status"] == "found"
    assert isinstance(result["output"]["results"], list)
    assert len(result["output"]["results"]) == 2
    assert result["output"]["results_count"] == 2
    assert result["output"]["total_results"] == 148
    assert result["output"]["cursor"] == "eyJwYWdlIjoyLCJzZWFyY2hfaWQiOiJhYmMxMjMifQ=="
    assert result["output"]["results"][0]["company_linkedin_id"] == "108037802"
    assert result["output"]["results"][0]["company_name"] == "Blitzapi"
    assert result["output"]["results"][0]["company_domain"] == "blitz-api.ai"
    assert result["output"]["results"][0]["description_raw"] == "BlitzAPI provides enriched B2B data access..."


@pytest.mark.asyncio
async def test_search_companies_empty_results(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = self
        assert method == "POST"
        assert url == "https://api.blitz-api.ai/v2/search/companies"
        assert headers["x-api-key"] == "blitz-key"
        assert json["max_results"] == 10
        return _FakeResponse(
            status_code=200,
            payload={"results": [], "results_count": 0, "total_results": 0, "cursor": None},
        )

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    result = await blitzapi.search_companies(
        api_key="blitz-key",
        company_filters={"keywords": {"include": ["SaaS"], "exclude": []}},
        max_results=10,
    )
    assert result["attempt"]["status"] == "not_found"
    assert result["mapped"]["results"] == []


@pytest.mark.asyncio
async def test_search_companies_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _mock_request(self, method: str, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ANN001
        _ = (self, method, url, headers, json)
        return _FakeResponse(status_code=500, payload={"success": False, "message": "error"})

    monkeypatch.setattr(blitzapi.httpx.AsyncClient, "request", _mock_request)
    result = await blitzapi.search_companies(
        api_key="blitz-key",
        company_filters={"keywords": {"include": ["SaaS"], "exclude": []}},
        max_results=10,
    )
    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == 500


@pytest.mark.asyncio
async def test_search_companies_with_keyword_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_companies(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_filters"]["keywords"]["include"] == ["SaaS", "cloud platform"]
        assert kwargs["company_filters"]["keywords"]["exclude"] == ["agency"]
        return {
            "attempt": {"provider": "blitzapi", "action": "search_companies", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"cursor": None, "totalItems": 0, "pageItems": 0}},
        }

    monkeypatch.setattr(blitzapi_company_search.blitzapi, "search_companies", _stub_search_companies)
    result = await blitzapi_company_search.execute_company_search_blitzapi(
        input_data={
            "company_filters": {
                "keywords": {
                    "include": ["SaaS", "cloud platform"],
                    "exclude": ["agency"],
                }
            }
        }
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_search_companies_assembles_filters_from_individual_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_companies(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_filters"] == {
            "keywords": {"include": ["SaaS"], "exclude": []},
            "hq": {"country_code": ["US"]},
            "employee_range": ["51-200"],
        }
        return {
            "attempt": {"provider": "blitzapi", "action": "search_companies", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"cursor": None, "totalItems": 0, "pageItems": 0}},
        }

    monkeypatch.setattr(blitzapi_company_search.blitzapi, "search_companies", _stub_search_companies)
    result = await blitzapi_company_search.execute_company_search_blitzapi(
        input_data={
            "keywords_include": ["SaaS"],
            "hq_country_code": "US",
            "employee_range": ["51-200"],
        }
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_search_companies_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_companies(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["cursor"] == "next-cursor-token"
        return {
            "attempt": {"provider": "blitzapi", "action": "search_companies", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"cursor": None, "totalItems": 0, "pageItems": 0}},
        }

    monkeypatch.setattr(blitzapi_company_search.blitzapi, "search_companies", _stub_search_companies)
    result = await blitzapi_company_search.execute_company_search_blitzapi(
        input_data={
            "company_filters": {"industry": {"include": ["Software Development"], "exclude": []}},
            "cursor": "next-cursor-token",
        }
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_search_companies_from_step_config(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_companies(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_filters"] == {
            "industry": {"include": ["Software Development"], "exclude": []},
            "type": {"include": ["Privately Held"], "exclude": []},
        }
        assert kwargs["max_results"] == 25
        return {
            "attempt": {"provider": "blitzapi", "action": "search_companies", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"cursor": None, "totalItems": 0, "pageItems": 0}},
        }

    monkeypatch.setattr(blitzapi_company_search.blitzapi, "search_companies", _stub_search_companies)
    result = await blitzapi_company_search.execute_company_search_blitzapi(
        input_data={
            "cumulative_context": {
                "step_config": {
                    "industry_include": ["Software Development"],
                    "type_include": ["Privately Held"],
                    "max_results": 25,
                }
            }
        }
    )
    assert result["status"] == "not_found"
