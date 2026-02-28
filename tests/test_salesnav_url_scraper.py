from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.providers import rapidapi_salesnav
from app.services import salesnav_operations


class _FakeResponse:
    def __init__(self, *, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.text = "{}"

    def json(self):
        return self._payload


def _sample_success_payload_with_count(count: int) -> dict:
    data = [
        {
            "firstName": f"First{idx}",
            "fullName": f"First{idx} Last{idx}",
            "lastName": f"Last{idx}",
            "geoRegion": "United States",
            "currentPosition": {
                "tenureAtPosition": {"numYears": 1, "numMonths": 2},
                "companyName": "Acme",
                "title": "Director",
                "companyId": "123",
                "companyUrnResolutionResult": {
                    "industry": "Software Development",
                    "location": "Austin, TX",
                },
                "tenureAtCompany": {"numYears": 2, "numMonths": 3},
                "startedOn": {"month": 4, "year": 2021},
            },
            "summary": "Summary text",
            "profileUrn": f"urn-{idx}",
            "navigationUrl": f"https://www.linkedin.com/in/test-{idx}",
            "openLink": False,
        }
        for idx in range(count)
    ]
    return {
        "success": True,
        "status": 200,
        "response": {
            "data": data,
            "pagination": {"total": count, "count": 25, "start": 0, "links": []},
        },
    }


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_missing_api_key():
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key=None,
        sales_nav_url="https://www.linkedin.com/sales/search/people",
    )
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_missing_url():
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key="rapid-key",
        sales_nav_url="  ",
    )
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_success(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        assert url == "https://realtime-linkedin-sales-navigator-data.p.rapidapi.com/premium_search_person_via_url"
        assert headers["x-rapidapi-host"] == "realtime-linkedin-sales-navigator-data.p.rapidapi.com"
        assert headers["x-rapidapi-key"] == "rapid-key"
        assert json["page"] == 1
        assert json["account_number"] == 1
        assert isinstance(json["url"], str)
        return _FakeResponse(status_code=200, payload=_sample_success_payload_with_count(3))

    monkeypatch.setattr(rapidapi_salesnav.httpx.AsyncClient, "post", _mock_post)
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key="rapid-key",
        sales_nav_url="https://www.linkedin.com/sales/search/people",
    )

    assert result["attempt"]["status"] == "found"
    assert result["mapped"]["result_count"] == 3
    assert len(result["mapped"]["results"]) == 3
    first = result["mapped"]["results"][0]
    assert first["full_name"] == "First0 Last0"
    assert first["linkedin_url"] == "https://www.linkedin.com/in/test-0"
    assert first["current_title"] == "Director"
    assert first["current_company_name"] == "Acme"


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_empty_results(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={"success": True, "status": 200, "response": {"data": [], "pagination": {"total": 0}}},
        )

    monkeypatch.setattr(rapidapi_salesnav.httpx.AsyncClient, "post", _mock_post)
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key="rapid-key",
        sales_nav_url="https://www.linkedin.com/sales/search/people",
    )
    assert result["attempt"]["status"] == "not_found"


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_http_error(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(status_code=500, payload={"success": False, "message": "server_error"})

    monkeypatch.setattr(rapidapi_salesnav.httpx.AsyncClient, "post", _mock_post)
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key="rapid-key",
        sales_nav_url="https://www.linkedin.com/sales/search/people",
    )
    assert result["attempt"]["status"] == "failed"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_scrape_sales_nav_url_maps_person_fields(monkeypatch: pytest.MonkeyPatch):
    async def _mock_post(self, url: str, headers: dict, json: dict):  # noqa: ANN001
        _ = (url, headers, json)
        return _FakeResponse(
            status_code=200,
            payload={
                "success": True,
                "status": 200,
                "response": {
                    "data": [
                        {
                            "firstName": "Kyohwe",
                            "fullName": "Kyohwe Goo",
                            "lastName": "Goo",
                            "geoRegion": "South Korea",
                            "currentPosition": {
                                "tenureAtPosition": {"numYears": 4, "numMonths": 8},
                                "companyName": "Hyundai Motor Company",
                                "title": "Design Strategy",
                                "companyId": "825160",
                                "companyUrnResolutionResult": {
                                    "industry": "Motor Vehicle Manufacturing",
                                    "location": "Seoul, Seoul, South Korea",
                                },
                                "tenureAtCompany": {"numYears": 4, "numMonths": 8},
                                "startedOn": {"month": 5, "year": 2020},
                            },
                            "summary": "Studied mechanical engineering",
                            "profileUrn": "ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY",
                            "navigationUrl": "https://www.linkedin.com/in/ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY",
                            "openLink": False,
                        }
                    ],
                    "pagination": {"total": 11, "count": 25, "start": 0, "links": []},
                },
            },
        )

    monkeypatch.setattr(rapidapi_salesnav.httpx.AsyncClient, "post", _mock_post)
    result = await rapidapi_salesnav.scrape_sales_nav_url(
        api_key="rapid-key",
        sales_nav_url="https://www.linkedin.com/sales/search/people",
    )
    person = result["mapped"]["results"][0]
    assert person["full_name"] == "Kyohwe Goo"
    assert person["first_name"] == "Kyohwe"
    assert person["last_name"] == "Goo"
    assert person["linkedin_url"] == "https://www.linkedin.com/in/ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY"
    assert person["profile_urn"] == "ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY"
    assert person["geo_region"] == "South Korea"
    assert person["summary"] == "Studied mechanical engineering"
    assert person["current_title"] == "Design Strategy"
    assert person["current_company_name"] == "Hyundai Motor Company"
    assert person["current_company_id"] == "825160"
    assert person["current_company_industry"] == "Motor Vehicle Manufacturing"
    assert person["current_company_location"] == "Seoul, Seoul, South Korea"
    assert person["position_start_month"] == 5
    assert person["position_start_year"] == 2020
    assert person["tenure_at_position_years"] == 4
    assert person["tenure_at_position_months"] == 8
    assert person["tenure_at_company_years"] == 4
    assert person["tenure_at_company_months"] == 8
    assert person["open_link"] is False


@pytest.mark.asyncio
async def test_execute_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        salesnav_operations,
        "get_settings",
        lambda: SimpleNamespace(rapidapi_salesnav_scrape_api_key="rapid-key"),
    )

    captured: dict[str, object] = {}

    async def _mock_scrape_sales_nav_url(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return {
            "attempt": {"provider": "rapidapi_salesnav", "action": "scrape_sales_nav_url", "status": "found"},
            "mapped": {
                "results": [
                    {
                        "full_name": "Jane Doe",
                        "first_name": "Jane",
                        "last_name": "Doe",
                        "linkedin_url": "https://www.linkedin.com/in/jane-doe",
                    }
                ],
                "result_count": 1,
                "total_available": 1,
                "page": 2,
                "source_url": "https://www.linkedin.com/sales/search/people",
            },
        }

    monkeypatch.setattr(rapidapi_salesnav, "scrape_sales_nav_url", _mock_scrape_sales_nav_url)

    result = await salesnav_operations.execute_person_search_sales_nav_url(
        input_data={
            "cumulative_context": {
                "sales_nav_url": "https://www.linkedin.com/sales/search/people",
            },
            "options": {"page": 2},
        }
    )

    assert captured["sales_nav_url"] == "https://www.linkedin.com/sales/search/people"
    assert captured["page"] == 2
    assert result["status"] == "found"
    assert result["output"]["result_count"] == 1
