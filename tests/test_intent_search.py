"""Tests for the intent-based search endpoint and service."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.intent_search import execute_intent_search


def _mock_provider_result(
    *,
    provider: str,
    action: str,
    results: list[dict[str, Any]] | None = None,
    pagination: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mapped_results = results or []
    return {
        "attempt": {
            "provider": provider,
            "action": action,
            "status": "found" if mapped_results else "not_found",
        },
        "mapped": {
            "results": mapped_results,
            "pagination": pagination or {"page": 1, "totalPages": 1},
        },
    }


def _fake_person(name: str = "Jane Doe") -> dict[str, Any]:
    return {
        "full_name": name,
        "first_name": name.split()[0],
        "last_name": name.split()[-1],
        "linkedin_url": f"https://linkedin.com/in/{name.lower().replace(' ', '-')}",
        "headline": "VP of Sales",
        "current_title": "VP of Sales",
        "current_company_name": "Acme",
        "current_company_domain": "acme.com",
        "location_name": "Texas",
        "country_code": "US",
        "source_person_id": "123",
        "source_provider": "prospeo",
        "raw": {},
    }


def _fake_company(name: str = "Acme Corp") -> dict[str, Any]:
    return {
        "company_name": name,
        "company_domain": "acme.com",
        "company_website": "https://acme.com",
        "company_linkedin_url": "https://linkedin.com/company/acme",
        "industry_primary": "Staffing and Recruiting",
        "employee_range": "201-500",
        "founded_year": 2010,
        "hq_country_code": "US",
        "source_company_id": "456",
        "source_provider": "prospeo",
        "raw": {},
    }


# ---------- Person search tests ----------


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_people", new_callable=AsyncMock)
async def test_person_search_prospeo_with_enum_resolution(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="person_search",
        results=[_fake_person()],
    )

    result = await execute_intent_search(
        search_type="people",
        criteria={"seniority": "VP", "department": "Sales", "location": "Texas"},
        provider=None,
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "prospeo"
    assert result["result_count"] == 1

    # Verify Prospeo was called with resolved filters
    call_kwargs = mock_search.call_args.kwargs
    filters = call_kwargs["provider_filters"]["prospeo"]
    assert filters["person_seniority"] == {"include": ["Vice President"]}
    assert filters["person_department"] == {"include": ["All Sales"]}
    assert filters["person_location_search"] == {"include": ["Texas"]}

    # Verify enum resolution metadata
    assert result["enum_resolution"]["seniority"]["resolved_value"] == "Vice President"
    assert result["enum_resolution"]["seniority"]["match_type"] == "synonym"
    assert result["enum_resolution"]["department"]["resolved_value"] == "All Sales"


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.blitzapi.search_employees", new_callable=AsyncMock)
async def test_person_search_blitzapi_with_enum_resolution(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="blitzapi",
        action="employee_finder",
        results=[_fake_person()],
    )

    result = await execute_intent_search(
        search_type="people",
        criteria={"seniority": "Director", "department": "Engineering"},
        provider="blitzapi",
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "blitzapi"
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs["job_level"] == ["Director"]
    assert call_kwargs["job_function"] == ["Engineering"]


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.blitzapi.search_employees", new_callable=AsyncMock)
@patch("app.services.intent_search.prospeo.search_people", new_callable=AsyncMock)
async def test_person_search_fallback_to_blitzapi(mock_prospeo, mock_blitzapi, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"

    # Prospeo returns empty
    mock_prospeo.return_value = _mock_provider_result(
        provider="prospeo", action="person_search", results=[]
    )
    # BlitzAPI returns results
    mock_blitzapi.return_value = _mock_provider_result(
        provider="blitzapi",
        action="employee_finder",
        results=[_fake_person()],
    )

    result = await execute_intent_search(
        search_type="people",
        criteria={"seniority": "VP", "company_linkedin_url": "https://linkedin.com/company/acme"},
        provider=None,
        limit=25,
        page=1,
    )

    # Prospeo was tried first
    mock_prospeo.assert_called_once()
    # BlitzAPI returned the results
    assert result["provider_used"] == "blitzapi"
    assert result["result_count"] == 1


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_people", new_callable=AsyncMock)
async def test_person_search_with_pass_through_fields(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="person_search",
        results=[_fake_person()],
    )

    result = await execute_intent_search(
        search_type="people",
        criteria={"job_title": "Account Executive", "company_domain": "salestalent.inc"},
        provider=None,
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "prospeo"
    call_kwargs = mock_search.call_args.kwargs
    filters = call_kwargs["provider_filters"]["prospeo"]
    # Pass-through fields are used directly, not enum-resolved
    assert filters["person_job_title"] == {"include": ["Account Executive"]}
    assert filters["company"]["websites"] == {"include": ["salestalent.inc"]}
    # No enum resolution entries for pass-through fields
    assert "job_title" not in result["enum_resolution"]
    assert "company_domain" not in result["enum_resolution"]


# ---------- Company search tests ----------


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_companies", new_callable=AsyncMock)
async def test_company_search_prospeo_with_industry(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="company_search",
        results=[_fake_company()],
    )

    result = await execute_intent_search(
        search_type="companies",
        criteria={"industry": "Staffing and Recruiting", "employee_range": "201-500"},
        provider=None,
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "prospeo"
    call_kwargs = mock_search.call_args.kwargs
    filters = call_kwargs["provider_filters"]["prospeo"]
    assert filters["company"]["industry"] == {"include": ["Staffing and Recruiting"]}
    assert filters["company"]["employee_range"] == {"include": ["201-500"]}


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.blitzapi.search_companies", new_callable=AsyncMock)
async def test_company_search_blitzapi_with_filters(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="blitzapi",
        action="search_companies",
        results=[_fake_company()],
    )

    result = await execute_intent_search(
        search_type="companies",
        criteria={
            "industry": "Computer Software",
            "company_type": "Privately Held",
            "continent": "North America",
        },
        provider="blitzapi",
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "blitzapi"
    call_kwargs = mock_search.call_args.kwargs
    company_filters = call_kwargs["company_filters"]
    assert company_filters["industry"] == {"include": ["Computer Software"]}
    assert company_filters["type"] == {"include": ["Privately Held"]}
    assert company_filters["hq"]["continent"] == ["North America"]


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_companies", new_callable=AsyncMock)
async def test_company_search_with_query_only(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="company_search",
        results=[_fake_company()],
    )

    result = await execute_intent_search(
        search_type="companies",
        criteria={"query": "staffing companies texas"},
        provider=None,
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "prospeo"
    call_kwargs = mock_search.call_args.kwargs
    assert call_kwargs["query"] == "staffing companies texas"


# ---------- Enum resolution metadata tests ----------


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_people", new_callable=AsyncMock)
async def test_unresolved_fields_in_response(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="person_search",
        results=[_fake_person()],
    )

    result = await execute_intent_search(
        search_type="people",
        criteria={"seniority": "xyzzy123", "location": "Texas"},
        provider="prospeo",
        limit=25,
        page=1,
    )

    assert "seniority" in result["unresolved_fields"]
    assert result["enum_resolution"]["seniority"]["match_type"] == "none"
    assert result["enum_resolution"]["seniority"]["resolved_value"] is None


@pytest.mark.asyncio
@patch("app.services.intent_search.get_settings")
@patch("app.services.intent_search.prospeo.search_companies", new_callable=AsyncMock)
async def test_list_criteria_values(mock_search, mock_settings):
    mock_settings.return_value.prospeo_api_key = "test-key"
    mock_settings.return_value.blitzapi_api_key = "test-key"
    mock_search.return_value = _mock_provider_result(
        provider="prospeo",
        action="company_search",
        results=[_fake_company()],
    )

    result = await execute_intent_search(
        search_type="companies",
        criteria={"industry": ["Construction", "Accounting"]},
        provider="prospeo",
        limit=25,
        page=1,
    )

    assert result["provider_used"] == "prospeo"
    call_kwargs = mock_search.call_args.kwargs
    filters = call_kwargs["provider_filters"]["prospeo"]
    # Both values should be individually resolved and passed as a list
    industry_include = filters["company"]["industry"]["include"]
    assert "Construction" in industry_include
    assert "Accounting" in industry_include
    assert len(industry_include) == 2


# ---------- Edge case tests ----------


@pytest.mark.asyncio
async def test_missing_criteria_returns_empty():
    result = await execute_intent_search(
        search_type="people",
        criteria={},
        provider=None,
        limit=25,
        page=1,
    )

    assert result["result_count"] == 0
    assert result["results"] == []
