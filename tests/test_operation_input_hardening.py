from __future__ import annotations

import pytest

from app.services.adyntel_operations import (
    execute_company_ads_search_google,
    execute_company_ads_search_linkedin,
    execute_company_ads_search_meta,
)
from app.services.company_operations import execute_company_enrich_profile
from app.services.email_operations import (
    execute_person_contact_resolve_email,
    execute_person_contact_resolve_mobile_phone,
    execute_person_contact_verify_email,
)
from app.services.research_operations import (
    execute_company_research_resolve_g2_url,
    execute_company_research_resolve_pricing_page_url,
)


def _assert_structured_result(result: dict) -> None:
    assert isinstance(result, dict)
    assert isinstance(result.get("run_id"), str)
    assert isinstance(result.get("operation_id"), str)
    assert result.get("status") in {"found", "not_found", "failed", "verified"}
    assert isinstance(result.get("provider_attempts"), list)


@pytest.mark.asyncio
async def test_execute_person_contact_resolve_email_noisy_input_returns_structured_failure():
    result = await execute_person_contact_resolve_email(
        input_data={
            "full_name": {"nested": "object"},
            "first_name": ["bad"],
            "last_name": {"also": "bad"},
            "company_domain": {"domain": "acme.com"},
            "company_name": ["Acme"],
            "company_profile": {"employee_count": 200},
            "results": [{"full_name": "ignored"}],
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_person_contact_verify_email_noisy_input_returns_structured_failure():
    result = await execute_person_contact_verify_email(
        input_data={
            "email": {"not": "a-string"},
            "verification": ["bad"],
            "company_domain": "acme.com",
            "extra": {"rich": {"context": True}},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_person_contact_resolve_mobile_phone_noisy_input_returns_structured_failure():
    result = await execute_person_contact_resolve_mobile_phone(
        input_data={
            "profile_url": {"url": "https://linkedin.com/in/test"},
            "linkedin_url": ["https://linkedin.com/in/test"],
            "work_email": {"email": "person@acme.com"},
            "personal_email": ["person@gmail.com"],
            "company_profile": {"company_name": "Acme"},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_enrich_profile_noisy_input_returns_structured_failure():
    result = await execute_company_enrich_profile(
        input_data={
            "company_domain": {"domain": "acme.com"},
            "company_website": ["https://acme.com"],
            "company_linkedin_url": {"url": "https://linkedin.com/company/acme"},
            "company_name": ["Acme"],
            "source_company_id": {"id": 123},
            "person_results": [{"full_name": "Someone"}],
            "timeline": {"events": []},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_research_resolve_g2_url_noisy_input_returns_structured_failure():
    result = await execute_company_research_resolve_g2_url(
        input_data={
            "company_name": {"name": "Acme"},
            "company_domain": ["acme.com"],
            "cumulative_context": {"company_profile": {"industry_primary": "SaaS"}},
            "results": [{"source": "search"}],
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_research_resolve_pricing_page_url_noisy_input_returns_structured_failure():
    result = await execute_company_research_resolve_pricing_page_url(
        input_data={
            "company_name": {"name": "Acme"},
            "company_domain": {"domain": "acme.com"},
            "ads": [{"headline": "demo"}],
            "metadata": {"pipeline_run_id": "run_123"},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_ads_search_linkedin_noisy_input_returns_structured_response():
    result = await execute_company_ads_search_linkedin(
        input_data={
            "company_domain": {"domain": "acme.com"},
            "linkedin_page_id": ["12345"],
            "continuation_token": {"cursor": "abc"},
            "entity_context": {"company_name": "Acme"},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_ads_search_meta_noisy_input_returns_structured_response():
    result = await execute_company_ads_search_meta(
        input_data={
            "company_domain": {"domain": "acme.com"},
            "facebook_url": {"url": "https://facebook.com/acme"},
            "keyword": ["acme"],
            "country_code": {"bad": "US"},
            "media_type": {"bad": "image"},
            "active_status": {"bad": "active"},
            "continuation_token": {"cursor": "meta"},
        }
    )
    _assert_structured_result(result)


@pytest.mark.asyncio
async def test_execute_company_ads_search_google_noisy_input_returns_structured_response():
    result = await execute_company_ads_search_google(
        input_data={
            "company_domain": {"domain": "acme.com"},
            "media_type": {"bad": "video"},
            "continuation_token": {"cursor": "google"},
            "extra": [{"noise": True}],
        }
    )
    _assert_structured_result(result)
