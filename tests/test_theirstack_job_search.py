from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from app.contracts.theirstack import TheirStackJobSearchExtendedOutput
from app.providers import theirstack as theirstack_provider
from app.services import theirstack_operations
from app.services.theirstack_operations import (
    execute_company_search_by_job_postings,
    execute_job_search,
)


def _sample_job_payload() -> dict[str, Any]:
    return {
        "id": 90210,
        "job_title": "Senior Data Engineer",
        "normalized_title": "data engineer",
        "url": "https://jobs.stripe.com/roles/90210",
        "final_url": "https://stripe.com/jobs/listing/90210",
        "source_url": "https://www.linkedin.com/jobs/view/90210",
        "date_posted": "2026-02-18",
        "discovered_at": "2026-02-18T09:00:00",
        "reposted": True,
        "date_reposted": "2026-02-19",
        "company": "Stripe",
        "company_domain": "stripe.com",
        "location": "New York, NY",
        "short_location": "New York, NY",
        "long_location": "New York, New York, United States",
        "state_code": "NY",
        "postal_code": "10001",
        "latitude": 40.7128,
        "longitude": -74.0060,
        "country": "United States",
        "country_code": "US",
        "cities": ["New York", "San Francisco"],
        "locations": [
            {
                "name": "New York",
                "state": "New York",
                "state_code": "NY",
                "country_code": "US",
                "country_name": "United States",
                "display_name": "New York, New York, United States",
                "latitude": 40.7128,
                "longitude": -74.006,
                "type": "city",
                "admin1_code": "NY",
                "admin1_name": "New York",
                "continent": "NA",
                "id": 5128581,
            },
            {
                "name": "San Francisco",
                "state": "California",
                "state_code": "CA",
                "country_code": "US",
                "country_name": "United States",
                "display_name": "San Francisco, California, United States",
                "latitude": 37.7749,
                "longitude": -122.4194,
                "type": "city",
                "admin1_code": "CA",
                "admin1_name": "California",
                "continent": "NA",
                "id": 5391959,
            },
        ],
        "countries": ["United States"],
        "country_codes": ["US"],
        "remote": False,
        "hybrid": True,
        "seniority": "senior",
        "employment_statuses": ["full_time"],
        "easy_apply": True,
        "salary_string": "$185,000 - $230,000",
        "min_annual_salary_usd": 185000,
        "max_annual_salary_usd": 230000,
        "avg_annual_salary_usd": 207500,
        "salary_currency": "USD",
        "description": "Build distributed data systems for product analytics and risk.",
        "technology_slugs": ["python", "kafka", "postgresql"],
        "hiring_team": [
            {
                "first_name": "Priya",
                "full_name": "Priya Shah",
                "image_url": "https://media.licdn.com/priya.jpg",
                "linkedin_url": "https://www.linkedin.com/in/priya-shah",
                "role": "VP Engineering",
                "thumbnail_url": "https://media.licdn.com/priya-thumb.jpg",
            },
            {
                "first_name": None,
                "full_name": None,
                "image_url": "https://media.licdn.com/ghost.jpg",
                "linkedin_url": None,
                "role": "Recruiter",
            },
        ],
        "company_object": {
            "id": "stripe",
            "name": "Stripe",
            "domain": "stripe.com",
            "industry": "financial services",
            "country": "United States",
            "employee_count": 8300,
            "logo": "https://logo.clearbit.com/stripe.com",
            "num_jobs": 412,
            "linkedin_url": "https://www.linkedin.com/company/stripe",
            "num_jobs_last_30_days": 27,
            "founded_year": 2010,
            "annual_revenue_usd": 14000000000,
            "total_funding_usd": 2200000000,
            "last_funding_round_date": "2023-03-15",
            "employee_count_range": "5001-10000",
            "long_description": "Stripe builds economic infrastructure for the internet.",
            "city": "South San Francisco",
            "publicly_traded_symbol": None,
            "publicly_traded_exchange": None,
            "funding_stage": "late_stage",
            "technology_slugs": ["kafka", "redis"],
            "technology_names": ["Kafka", "Redis"],
        },
        "manager_roles": ["VP Engineering", "Director of Data"],
    }


def _set_theirstack_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        theirstack_operations,
        "get_settings",
        lambda: SimpleNamespace(theirstack_api_key="test-theirstack-key"),
    )


def _mock_provider_result_with_single_job() -> dict[str, Any]:
    return {
        "attempt": {
            "provider": "theirstack",
            "action": "search_jobs",
            "status": "found",
            "http_status": 200,
        },
        "mapped": {
            "results": [theirstack_provider._map_job_item(_sample_job_payload())],
            "result_count": 1,
            "total_results": 987,
            "total_companies": 456,
        },
    }


def test_map_job_item_full_fields():
    mapped = theirstack_provider._map_job_item(_sample_job_payload())
    assert mapped["job_id"] == 90210
    assert mapped["theirstack_job_id"] == 90210
    assert mapped["job_title"] == "Senior Data Engineer"
    assert mapped["normalized_title"] == "data engineer"
    assert mapped["company_name"] == "Stripe"
    assert mapped["company_domain"] == "stripe.com"
    assert mapped["url"] == "https://jobs.stripe.com/roles/90210"
    assert mapped["final_url"] == "https://stripe.com/jobs/listing/90210"
    assert mapped["source_url"] == "https://www.linkedin.com/jobs/view/90210"
    assert mapped["date_posted"] == "2026-02-18"
    assert mapped["discovered_at"] == "2026-02-18T09:00:00"
    assert mapped["reposted"] is True
    assert mapped["date_reposted"] == "2026-02-19"
    assert mapped["location"] == "New York, NY"
    assert mapped["short_location"] == "New York, NY"
    assert mapped["long_location"] == "New York, New York, United States"
    assert mapped["state_code"] == "NY"
    assert mapped["postal_code"] == "10001"
    assert mapped["latitude"] == 40.7128
    assert mapped["longitude"] == -74.006
    assert mapped["country"] == "United States"
    assert mapped["country_code"] == "US"
    assert mapped["cities"] == ["New York", "San Francisco"]
    assert mapped["locations"] is not None
    assert len(mapped["locations"]) == 2
    first_location = mapped["locations"][0]
    assert first_location["name"] == "New York"
    assert first_location["state_code"] == "NY"
    assert first_location["display_name"] == "New York, New York, United States"
    assert first_location["latitude"] == 40.7128
    assert first_location["type"] == "city"
    assert "admin1_code" not in first_location
    assert "admin1_name" not in first_location
    assert "continent" not in first_location
    assert "id" not in first_location
    assert mapped["countries"] == ["United States"]
    assert mapped["country_codes"] == ["US"]
    assert mapped["remote"] is False
    assert mapped["hybrid"] is True
    assert mapped["seniority"] == "senior"
    assert mapped["employment_statuses"] == ["full_time"]
    assert mapped["easy_apply"] is True
    assert mapped["salary_string"] == "$185,000 - $230,000"
    assert mapped["min_annual_salary_usd"] == 185000.0
    assert mapped["max_annual_salary_usd"] == 230000.0
    assert mapped["avg_annual_salary_usd"] == 207500.0
    assert mapped["salary_currency"] == "USD"
    assert mapped["description"].startswith("Build distributed data systems")
    assert mapped["technology_slugs"] == ["python", "kafka", "postgresql"]
    assert mapped["hiring_team"] == [
        {
            "full_name": "Priya Shah",
            "first_name": "Priya",
            "linkedin_url": "https://www.linkedin.com/in/priya-shah",
            "role": "VP Engineering",
            "image_url": "https://media.licdn.com/priya.jpg",
        }
    ]
    assert mapped["company_object"]["theirstack_company_id"] == "stripe"
    assert mapped["company_object"]["domain"] == "stripe.com"
    assert mapped["manager_roles"] == ["VP Engineering", "Director of Data"]


def test_map_job_item_minimal_fields():
    mapped = theirstack_provider._map_job_item({"id": "55", "company": "Notion", "remote": None})
    assert mapped["job_id"] == 55
    assert mapped["theirstack_job_id"] == 55
    assert mapped["company_name"] == "Notion"
    assert mapped["job_title"] is None
    assert mapped["remote"] is None
    assert mapped["locations"] is None
    assert mapped["countries"] is None
    assert mapped["country_codes"] is None
    assert mapped["hiring_team"] is None
    assert mapped["company_object"] is None


def test_map_hiring_team_item_valid():
    mapped = theirstack_provider._map_hiring_team_item(
        {
            "first_name": "Ana",
            "full_name": "Ana Martins",
            "linkedin_url": "https://www.linkedin.com/in/ana-martins",
            "role": "Head of Talent",
            "image_url": "https://media.licdn.com/ana.jpg",
        }
    )
    assert mapped == {
        "full_name": "Ana Martins",
        "first_name": "Ana",
        "linkedin_url": "https://www.linkedin.com/in/ana-martins",
        "role": "Head of Talent",
        "image_url": "https://media.licdn.com/ana.jpg",
    }


def test_map_hiring_team_item_skip_empty():
    assert (
        theirstack_provider._map_hiring_team_item(
            {
                "first_name": "Ghost",
                "full_name": None,
                "linkedin_url": None,
                "role": "Recruiter",
            }
        )
        is None
    )


def test_map_location_item_valid():
    mapped = theirstack_provider._map_location_item(
        {
            "name": "New York",
            "state": "New York",
            "state_code": "NY",
            "country_code": "US",
            "country_name": "United States",
            "display_name": "New York, New York, United States",
            "latitude": 40.7128,
            "longitude": -74.006,
            "type": "city",
            "admin1_code": "NY",
            "admin1_name": "New York",
            "continent": "NA",
            "id": 5128581,
        }
    )
    assert mapped is not None
    assert mapped["name"] == "New York"
    assert mapped["state"] == "New York"
    assert mapped["state_code"] == "NY"
    assert mapped["country_code"] == "US"
    assert mapped["country_name"] == "United States"
    assert mapped["display_name"] == "New York, New York, United States"
    assert mapped["latitude"] == 40.7128
    assert mapped["longitude"] == -74.006
    assert mapped["type"] == "city"
    assert "admin1_code" not in mapped
    assert "admin1_name" not in mapped
    assert "continent" not in mapped
    assert "id" not in mapped


def test_map_location_item_skip_empty():
    assert theirstack_provider._map_location_item({"name": None, "display_name": None, "latitude": 0}) is None


def test_map_company_object_valid():
    mapped = theirstack_provider._map_company_object(_sample_job_payload()["company_object"])
    assert mapped["theirstack_company_id"] == "stripe"
    assert mapped["name"] == "Stripe"
    assert mapped["employee_count"] == 8300
    assert mapped["annual_revenue_usd"] == 14000000000.0
    assert mapped["technology_names"] == ["Kafka", "Redis"]


def test_map_company_object_skip_empty():
    assert theirstack_provider._map_company_object({"id": "x", "name": None, "domain": "  "}) is None


@pytest.mark.asyncio
async def test_search_jobs_pagination_params():
    captured_payload: dict[str, Any] = {}

    class _FakeResponse:
        status_code = 200
        text = '{"metadata":{"total_results":11,"total_companies":7},"data":[]}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {"metadata": {"total_results": 11, "total_companies": 7}, "data": []}

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]):
            assert url == "https://api.theirstack.com/v1/jobs/search"
            assert headers["Authorization"] == "Bearer key-123"
            captured_payload.update(json)
            return _FakeResponse()

    with patch("app.providers.theirstack.httpx.AsyncClient", _FakeAsyncClient):
        await theirstack_provider.search_jobs(
            api_key="key-123",
            filters={"company_domain_or": ["stripe.com"]},
            limit=50,
            offset=25,
            page=3,
            cursor="abc-cursor-123",
            include_total_results=True,
        )

    assert captured_payload == {
        "company_domain_or": ["stripe.com"],
        "limit": 50,
        "offset": 25,
        "page": 3,
        "cursor": "abc-cursor-123",
        "include_total_results": True,
    }


@pytest.mark.asyncio
async def test_search_jobs_metadata_in_output():
    class _FakeResponse:
        status_code = 200
        text = '{"metadata":{"total_results":2034,"total_companies":1045},"data":[]}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {"metadata": {"total_results": 2034, "total_companies": 1045}, "data": []}

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]):
            return _FakeResponse()

    with patch("app.providers.theirstack.httpx.AsyncClient", _FakeAsyncClient):
        result = await theirstack_provider.search_jobs(
            api_key="key-123",
            filters={"posted_at_max_age_days": 7},
            limit=10,
            include_total_results=True,
        )

    assert result["mapped"]["result_count"] == 0
    assert result["mapped"]["total_results"] == 2034
    assert result["mapped"]["total_companies"] == 1045


@pytest.mark.asyncio
async def test_job_search_full_filters(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    captured_kwargs: dict[str, Any] = {}

    async def _fake_search_jobs(**kwargs):
        captured_kwargs.update(kwargs)
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)

    step_config = {
        "job_title_or": ["Data Engineer"],
        "job_title_not": ["Intern"],
        "job_title_pattern_or": ["Senior*"],
        "job_country_code_or": ["US"],
        "job_location_pattern_not": ["Remote only"],
        "posted_at_max_age_days": 0,
        "discovered_at_max_age_days": 14,
        "remote": False,
        "job_seniority_or": ["senior"],
        "min_salary_usd": 180000,
        "max_salary_usd": 260000,
        "easy_apply": True,
        "employment_statuses_or": ["full_time"],
        "job_description_contains_or": ["postgres", "kafka"],
        "job_technology_slug_and": ["python", "kafka"],
        "url_domain_or": ["greenhouse.io"],
        "company_domain_or": ["stripe.com"],
        "company_name_partial_match_or": ["Stripe"],
        "company_linkedin_url_or": ["https://www.linkedin.com/company/stripe"],
        "company_description_pattern_or": ["payments"],
        "min_revenue_usd": 1000000000,
        "max_revenue_usd": 30000000000,
        "min_employee_count": 1000,
        "max_employee_count": 20000,
        "min_funding_usd": 100000000,
        "max_funding_usd": 5000000000,
        "funding_stage_or": ["late_stage"],
        "industry_id_or": ["fintech"],
        "company_country_code_or": ["US"],
        "company_technology_slug_or": ["kafka"],
        "company_investors_or": ["Sequoia Capital"],
        "company_tags_or": ["fintech"],
        "only_yc_companies": False,
        "company_type": "direct_employer",
        "blur_company_data": False,
        "limit": 100,
        "offset": 200,
        "page": 5,
        "cursor": "cursor-5",
        "include_total_results": True,
    }
    result = await execute_job_search(input_data={"step_config": step_config})

    assert result["status"] == "found"
    assert captured_kwargs["api_key"] == "test-theirstack-key"
    assert captured_kwargs["limit"] == 100
    assert captured_kwargs["offset"] == 200
    assert captured_kwargs["page"] == 5
    assert captured_kwargs["cursor"] == "cursor-5"
    assert captured_kwargs["include_total_results"] is True
    assert captured_kwargs["filters"]["job_title_or"] == ["Data Engineer"]
    assert captured_kwargs["filters"]["remote"] is False
    assert captured_kwargs["filters"]["posted_at_max_age_days"] == 0
    assert captured_kwargs["filters"]["company_type"] == "direct_employer"


@pytest.mark.asyncio
async def test_job_search_missing_required_filter():
    result = await execute_job_search(
        input_data={
            "step_config": {
                "job_title_or": ["Data Engineer"],
                "remote": True,
            }
        }
    )
    assert result["operation_id"] == "job.search"
    assert result["status"] == "failed"
    assert "posted_at_max_age_days" in result["missing_inputs"][0]


@pytest.mark.asyncio
async def test_job_search_boolean_false_preserved(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)
    captured_filters: dict[str, Any] = {}

    async def _fake_search_jobs(**kwargs):
        captured_filters.update(kwargs["filters"])
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)

    await execute_job_search(
        input_data={"step_config": {"company_domain_or": ["stripe.com"], "remote": False}}
    )
    assert captured_filters["remote"] is False


@pytest.mark.asyncio
async def test_job_search_integer_zero_preserved(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)
    captured_filters: dict[str, Any] = {}

    async def _fake_search_jobs(**kwargs):
        captured_filters.update(kwargs["filters"])
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)

    await execute_job_search(
        input_data={"step_config": {"posted_at_max_age_days": 0, "company_domain_or": ["stripe.com"]}}
    )
    assert captured_filters["posted_at_max_age_days"] == 0


@pytest.mark.asyncio
async def test_job_search_success_response_shape(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_jobs(**kwargs):
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)

    result = await execute_job_search(
        input_data={"step_config": {"company_domain_or": ["stripe.com"], "include_total_results": True}}
    )

    validated = TheirStackJobSearchExtendedOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.total_results == 987
    assert validated.results[0].hiring_team is not None
    assert validated.results[0].company_object is not None
    assert validated.results[0].locations is not None
    assert validated.results[0].countries is not None
    assert validated.results[0].theirstack_job_id == validated.results[0].job_id


@pytest.mark.asyncio
async def test_job_search_empty_results(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_jobs(**kwargs):
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_jobs",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {"results": [], "result_count": 0, "total_results": 0, "total_companies": 0},
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)
    result = await execute_job_search(input_data={"step_config": {"company_domain_or": ["stripe.com"]}})
    assert result["status"] == "not_found"
    assert result["output"]["result_count"] == 0


@pytest.mark.asyncio
async def test_job_search_api_error(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_jobs(**kwargs):
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_jobs",
                "status": "failed",
                "http_status": 429,
                "raw_response": {"error": "rate_limit"},
            },
            "mapped": {"results": [], "result_count": 0, "total_results": None, "total_companies": None},
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)
    result = await execute_job_search(input_data={"step_config": {"company_domain_or": ["stripe.com"]}})
    assert result["status"] == "failed"
    assert result["provider_attempts"][0]["http_status"] == 429


@pytest.mark.asyncio
async def test_company_search_by_job_postings_still_works(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_jobs(**kwargs):
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)
    result = await execute_company_search_by_job_postings(
        input_data={"step_config": {"job_title_or": ["Data Engineer"], "limit": 10}}
    )
    assert result["status"] == "found"
    assert result["output"]["results"][0]["job_title"] == "Senior Data Engineer"
    assert result["output"]["results"][0]["theirstack_job_id"] == 90210


@pytest.mark.asyncio
async def test_company_search_by_job_postings_expanded_filters(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)
    captured_filters: dict[str, Any] = {}

    async def _fake_search_jobs(**kwargs):
        captured_filters.update(kwargs["filters"])
        return _mock_provider_result_with_single_job()

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)
    await execute_company_search_by_job_postings(
        input_data={
            "step_config": {
                "company_domain_or": ["stripe.com"],
                "remote": False,
                "posted_at_gte": "2026-02-01",
                "posted_at_lte": "2026-02-19",
                "min_salary_usd": 170000,
                "max_salary_usd": 250000,
                "employment_statuses_or": ["full_time"],
                "company_type": "direct_employer",
                "min_employee_count": 1000,
                "max_employee_count": 25000,
                "min_revenue_usd": 1000000000,
                "max_revenue_usd": 40000000000,
            }
        }
    )
    assert captured_filters["company_domain_or"] == ["stripe.com"]
    assert captured_filters["remote"] is False
    assert captured_filters["posted_at_gte"] == "2026-02-01"
    assert captured_filters["posted_at_lte"] == "2026-02-19"
    assert captured_filters["min_employee_count"] == 1000
    assert captured_filters["max_revenue_usd"] == 40000000000
