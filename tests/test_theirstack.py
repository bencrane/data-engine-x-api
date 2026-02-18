from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.theirstack import (
    TheirStackCompanySearchOutput,
    TheirStackHiringSignalsOutput,
    TheirStackJobSearchOutput,
    TheirStackTechStackOutput,
)
from app.services import theirstack_operations
from app.services.theirstack_operations import (
    execute_company_enrich_hiring_signals,
    execute_company_enrich_tech_stack,
    execute_company_search_by_job_postings,
    execute_company_search_by_tech_stack,
)


def _set_theirstack_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        theirstack_operations,
        "get_settings",
        lambda: SimpleNamespace(theirstack_api_key="test-theirstack-key"),
    )


@pytest.mark.asyncio
async def test_execute_company_search_by_tech_stack_missing_filters_failed():
    result = await execute_company_search_by_tech_stack(
        input_data={
            "noise": {"anything": True},
            "step_config": {"limit": 20},
            "cumulative_context": {"results": [{"ignored": True}]},
        }
    )

    assert result["operation_id"] == "company.search.by_tech_stack"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert "technology_slug_or" in result["missing_inputs"][0]


@pytest.mark.asyncio
async def test_execute_company_search_by_tech_stack_success_validates_contract(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_companies(*, api_key: str | None, filters: dict, limit: int):
        assert api_key == "test-theirstack-key"
        assert filters == {
            "technology_slug_or": ["postgresql", "snowflake"],
            "industry_or": ["Software"],
            "company_country_code_or": ["US"],
            "job_title_or": ["Data Engineer"],
        }
        assert limit == 25
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_companies",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "company_name": "Acme",
                        "domain": "acme.com",
                        "linkedin_url": "https://www.linkedin.com/company/acme",
                        "industry": "Software",
                        "employee_count": 1200,
                        "country_code": "US",
                        "num_jobs": 50,
                        "num_jobs_last_30_days": 8,
                        "technology_slugs": ["postgresql", "snowflake"],
                        "annual_revenue_usd": 125000000.0,
                        "total_funding_usd": 50000000,
                        "funding_stage": "series_c",
                    }
                ],
                "result_count": 1,
            },
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "search_companies", _fake_search_companies)

    result = await execute_company_search_by_tech_stack(
        input_data={
            "step_config": {
                "technology_slug_or": ["postgresql", "snowflake"],
                "industry_or": ["Software"],
                "company_country_code_or": ["US"],
                "job_title_or": ["Data Engineer"],
                "limit": 25,
            },
            "cumulative_context": {"noise": [1, 2, 3]},
        }
    )

    validated = TheirStackCompanySearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.results[0].domain == "acme.com"


@pytest.mark.asyncio
async def test_execute_company_search_by_job_postings_missing_filters_failed():
    result = await execute_company_search_by_job_postings(
        input_data={
            "noise": {"anything": True},
            "step_config": {"limit": 10},
            "history": [{"step": "upstream"}],
        }
    )

    assert result["operation_id"] == "company.search.by_job_postings"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert "job_title_or" in result["missing_inputs"][0]


@pytest.mark.asyncio
async def test_execute_company_search_by_job_postings_success_validates_contract(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_search_jobs(*, api_key: str | None, filters: dict, limit: int):
        assert api_key == "test-theirstack-key"
        assert filters == {
            "job_title_or": ["Data Engineer"],
            "job_country_code_or": ["US"],
            "posted_at_max_age_days": 14,
            "job_technology_slug_or": ["snowflake"],
            "job_seniority_or": ["senior"],
        }
        assert limit == 15
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_jobs",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "job_id": 123,
                        "job_title": "Senior Data Engineer",
                        "company_name": "Acme",
                        "company_domain": "acme.com",
                        "url": "https://jobs.acme.com/123",
                        "date_posted": "2026-02-01",
                        "location": "United States",
                        "seniority": "senior",
                    }
                ],
                "result_count": 1,
            },
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "search_jobs", _fake_search_jobs)

    result = await execute_company_search_by_job_postings(
        input_data={
            "step_config": {
                "job_title_or": ["Data Engineer"],
                "job_country_code_or": ["US"],
                "posted_at_max_age_days": 14,
                "job_technology_slug_or": ["snowflake"],
                "job_seniority_or": ["senior"],
                "limit": 15,
            },
            "extra": {"nested": True},
        }
    )

    validated = TheirStackJobSearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.results[0].job_title == "Senior Data Engineer"


@pytest.mark.asyncio
async def test_execute_company_enrich_tech_stack_missing_identifiers_failed():
    result = await execute_company_enrich_tech_stack(
        input_data={
            "company_profile": {"employee_count": 100},
            "cumulative_context": {"history": [{"step": "x"}]},
        }
    )

    assert result["operation_id"] == "company.enrich.tech_stack"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain|company_name|company_linkedin_url"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_tech_stack_success_validates_contract(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_get_technographics(
        *,
        api_key: str | None,
        company_domain: str | None,
        company_name: str | None,
        company_linkedin_url: str | None,
    ):
        assert api_key == "test-theirstack-key"
        assert company_domain == "acme.com"
        assert company_name == "Acme"
        assert company_linkedin_url == "https://www.linkedin.com/company/acme"
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "technographics",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "technologies": [
                    {
                        "name": "Snowflake",
                        "slug": "snowflake",
                        "category": "Data Warehouse",
                        "confidence": "high",
                        "jobs": 22,
                        "jobs_last_30_days": 5,
                        "first_date_found": "2024-01-01",
                        "last_date_found": "2026-01-30",
                        "rank_within_category": 1,
                    }
                ],
                "technology_count": 1,
            },
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "get_technographics", _fake_get_technographics)

    result = await execute_company_enrich_tech_stack(
        input_data={
            "cumulative_context": {
                "company_profile": {
                    "company_domain": "acme.com",
                    "company_name": "Acme",
                    "company_linkedin_url": "https://www.linkedin.com/company/acme",
                },
                "noise": {"anything": "goes"},
            }
        }
    )

    validated = TheirStackTechStackOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.technology_count == 1
    assert validated.technologies[0].name == "Snowflake"


@pytest.mark.asyncio
async def test_execute_company_enrich_hiring_signals_missing_domain_failed():
    result = await execute_company_enrich_hiring_signals(
        input_data={"cumulative_context": {"company_profile": {"company_name": "Acme"}}}
    )

    assert result["operation_id"] == "company.enrich.hiring_signals"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_execute_company_enrich_hiring_signals_success_validates_contract(monkeypatch: pytest.MonkeyPatch):
    _set_theirstack_key(monkeypatch)

    async def _fake_enrich_hiring_signals(*, api_key: str | None, company_domain: str | None):
        assert api_key == "test-theirstack-key"
        assert company_domain == "acme.com"
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "enrich_hiring_signals",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "company_name": "Acme",
                "domain": "acme.com",
                "num_jobs": 120,
                "num_jobs_last_30_days": 18,
                "technology_slugs": ["snowflake", "postgresql"],
                "recent_job_titles": ["Senior Data Engineer", "Analytics Engineer"],
            },
        }

    monkeypatch.setattr(theirstack_operations.theirstack, "enrich_hiring_signals", _fake_enrich_hiring_signals)

    result = await execute_company_enrich_hiring_signals(
        input_data={
            "cumulative_context": {
                "company_profile": {"company_domain": "acme.com"},
                "extra": {"noise": True},
            }
        }
    )

    validated = TheirStackHiringSignalsOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.domain == "acme.com"
    assert validated.num_jobs_last_30_days == 18
