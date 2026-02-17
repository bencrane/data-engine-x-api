from __future__ import annotations

import pytest

from app.services import search_operations


@pytest.mark.asyncio
async def test_execute_person_search_tolerates_rich_context_and_bad_types(monkeypatch: pytest.MonkeyPatch):
    async def _stub_search_people_prospeo(**kwargs):
        assert kwargs["query"] is None
        assert kwargs["page"] == 1
        assert kwargs["company_domain"] == "acme.com"
        assert kwargs["company_name"] == "Acme Inc"
        assert kwargs["provider_filters"] is None
        kwargs["attempts"].append(
            {
                "provider": "prospeo",
                "action": "person_search",
                "status": "not_found",
            }
        )
        return [], None

    async def _stub_search_people_blitzapi(**kwargs):
        assert kwargs["query"] is None
        assert kwargs["company_domain"] == "acme.com"
        assert kwargs["company_linkedin_url"] == "https://linkedin.com/company/acme"
        assert kwargs["limit"] == 100
        assert kwargs["provider_filters"] is None
        kwargs["attempts"].append(
            {
                "provider": "blitzapi",
                "action": "person_search",
                "status": "not_found",
            }
        )
        return [], None

    async def _stub_search_people_companyenrich(**kwargs):
        assert kwargs["query"] is None
        assert kwargs["page"] == 1
        assert kwargs["page_size"] == 25
        assert kwargs["company_domain"] == "acme.com"
        assert kwargs["company_name"] == "Acme Inc"
        assert kwargs["provider_filters"] is None
        kwargs["attempts"].append(
            {
                "provider": "companyenrich",
                "action": "person_search",
                "status": "not_found",
            }
        )
        return [], None

    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_search_people_prospeo)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_search_people_blitzapi)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_search_people_companyenrich)
    monkeypatch.setattr(search_operations, "_person_search_provider_order", lambda: ["prospeo", "blitzapi", "companyenrich"])

    result = await search_operations.execute_person_search(
        input_data={
            "query": {"unexpected": "object"},
            "page": {"nested": "bad-value"},
            "page_size": ["bad-value"],
            "limit": "not-a-number",
            "company_domain": "https://www.acme.com/path",
            "company_name": " Acme Inc ",
            "company_linkedin_url": " https://linkedin.com/company/acme ",
            "provider_filters": {"blitzapi": ["unexpected-list"]},
            "ads": [{"creative": "foo"}],
            "company_profile": {"employees": "100-500"},
            "continuation_token": {"cursor": "abc"},
            "pricing_page_url": "https://acme.com/pricing",
            "g2_url": "https://www.g2.com/products/acme/reviews",
        }
    )

    assert result["operation_id"] == "person.search"
    assert result["status"] == "not_found"
    assert "output" in result
    assert result["output"]["result_count"] == 0
    assert isinstance(result["provider_attempts"], list)
