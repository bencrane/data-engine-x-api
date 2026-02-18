from __future__ import annotations

import pytest

from app.services import search_operations


@pytest.mark.asyncio
async def test_person_search_with_job_title_calls_leadmagic_role_first(monkeypatch: pytest.MonkeyPatch):
    call_order: list[str] = []

    async def _stub_role(**kwargs):
        call_order.append("leadmagic_role")
        kwargs["attempts"].append({"provider": "leadmagic", "action": "role_finder", "status": "found"})
        return [
            {
                "full_name": "Jane Doe",
                "first_name": "Jane",
                "last_name": "Doe",
                "linkedin_url": "https://linkedin.com/in/jane-doe",
                "headline": "VP Sales",
                "current_title": "VP Sales",
                "current_company_name": "Acme",
                "current_company_domain": "acme.com",
                "location_name": "US",
                "country_code": "US",
                "source_person_id": None,
                "source_provider": "leadmagic",
                "raw": {},
            }
        ], None

    async def _stub_never_called(**kwargs):
        raise AssertionError("Fallback providers should not run when leadmagic role finder returns results")

    monkeypatch.setattr(search_operations, "_search_people_leadmagic_role", _stub_role)
    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_never_called)
    monkeypatch.setattr(search_operations, "_person_search_provider_order", lambda: ["prospeo", "blitzapi", "companyenrich", "leadmagic"])

    result = await search_operations.execute_person_search(
        input_data={"job_title": "VP Sales", "company_domain": "acme.com"}
    )

    assert call_order == ["leadmagic_role"]
    assert result["status"] == "found"
    assert result["output"]["result_count"] == 1


@pytest.mark.asyncio
async def test_person_search_with_cascade_calls_blitz_waterfall(monkeypatch: pytest.MonkeyPatch):
    called = {"waterfall": False}

    async def _stub_waterfall(**kwargs):
        called["waterfall"] = True
        assert kwargs["company_linkedin_url"] == "https://linkedin.com/company/acme"
        assert kwargs["max_results"] == 7
        assert isinstance(kwargs["cascade"], list)
        kwargs["attempts"].append({"provider": "blitzapi", "action": "waterfall_icp_search", "status": "not_found"})
        return [], {"page": 1, "totalPages": 1, "totalItems": 0}

    async def _stub_never_called(**kwargs):
        raise AssertionError("Only waterfall search should run when cascade is provided")

    monkeypatch.setattr(search_operations, "_search_people_blitzapi_waterfall", _stub_waterfall)
    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_leadmagic_employees", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_leadmagic_role", _stub_never_called)

    result = await search_operations.execute_person_search(
        input_data={
            "company_linkedin_url": "https://linkedin.com/company/acme",
            "max_results": 7,
            "cascade": [{"include_title": ["VP Sales"], "location": ["WORLD"]}],
        }
    )

    assert called["waterfall"] is True
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_person_search_max_results_is_mapped_per_provider(monkeypatch: pytest.MonkeyPatch):
    seen: dict[str, int] = {}

    async def _stub_prospeo(**kwargs):
        kwargs["attempts"].append({"provider": "prospeo", "action": "person_search", "status": "not_found"})
        return [], None

    async def _stub_blitz(**kwargs):
        seen["blitz_max_results"] = kwargs["max_results"]
        kwargs["attempts"].append({"provider": "blitzapi", "action": "employee_finder", "status": "not_found"})
        return [], None

    async def _stub_companyenrich(**kwargs):
        seen["companyenrich_page_size"] = kwargs["page_size"]
        kwargs["attempts"].append({"provider": "companyenrich", "action": "person_search", "status": "not_found"})
        return [], None

    async def _stub_leadmagic(**kwargs):
        seen["leadmagic_limit"] = kwargs["max_results"]
        kwargs["attempts"].append({"provider": "leadmagic", "action": "employee_finder", "status": "not_found"})
        return [], None

    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_prospeo)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_blitz)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_companyenrich)
    monkeypatch.setattr(search_operations, "_search_people_leadmagic_employees", _stub_leadmagic)
    monkeypatch.setattr(search_operations, "_person_search_provider_order", lambda: ["prospeo", "blitzapi", "companyenrich", "leadmagic"])

    await search_operations.execute_person_search(
        input_data={
            "company_domain": "acme.com",
            "company_linkedin_url": "https://linkedin.com/company/acme",
            "max_results": 12,
        }
    )

    assert seen["blitz_max_results"] == 12
    assert seen["companyenrich_page_size"] == 12
    assert seen["leadmagic_limit"] == 12


@pytest.mark.asyncio
async def test_person_search_without_title_or_cascade_keeps_waterfall_order(monkeypatch: pytest.MonkeyPatch):
    call_order: list[str] = []

    async def _stub_prospeo(**kwargs):
        call_order.append("prospeo")
        kwargs["attempts"].append({"provider": "prospeo", "action": "person_search", "status": "not_found"})
        return [], None

    async def _stub_blitz(**kwargs):
        call_order.append("blitzapi")
        kwargs["attempts"].append({"provider": "blitzapi", "action": "employee_finder", "status": "not_found"})
        return [], None

    async def _stub_companyenrich(**kwargs):
        call_order.append("companyenrich")
        kwargs["attempts"].append({"provider": "companyenrich", "action": "person_search", "status": "not_found"})
        return [], None

    async def _stub_leadmagic(**kwargs):
        call_order.append("leadmagic")
        kwargs["attempts"].append({"provider": "leadmagic", "action": "employee_finder", "status": "not_found"})
        return [], None

    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_prospeo)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_blitz)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_companyenrich)
    monkeypatch.setattr(search_operations, "_search_people_leadmagic_employees", _stub_leadmagic)
    monkeypatch.setattr(search_operations, "_person_search_provider_order", lambda: ["prospeo", "blitzapi", "companyenrich", "leadmagic"])

    result = await search_operations.execute_person_search(input_data={"company_domain": "acme.com"})

    assert result["status"] == "not_found"
    assert call_order == ["prospeo", "blitzapi", "companyenrich", "leadmagic"]


@pytest.mark.asyncio
async def test_person_search_blitzapi_eligible_with_company_linkedin_url(monkeypatch: pytest.MonkeyPatch):
    called = {"blitz": False}

    async def _stub_prospeo(**kwargs):
        kwargs["attempts"].append({"provider": "prospeo", "action": "person_search", "status": "not_found"})
        return [], None

    async def _stub_blitz(**kwargs):
        called["blitz"] = True
        assert kwargs["company_linkedin_url"] == "https://linkedin.com/company/acme"
        kwargs["attempts"].append({"provider": "blitzapi", "action": "employee_finder", "status": "found"})
        return [
            {
                "full_name": "John Doe",
                "first_name": "John",
                "last_name": "Doe",
                "linkedin_url": "https://linkedin.com/in/john-doe",
                "headline": "Director",
                "current_title": "Director",
                "current_company_name": None,
                "current_company_domain": None,
                "location_name": "US",
                "country_code": "US",
                "source_person_id": "1",
                "source_provider": "blitzapi",
                "raw": {},
            }
        ], None

    async def _stub_never_called(**kwargs):
        raise AssertionError("Search should stop after first provider with results")

    monkeypatch.setattr(search_operations, "_search_people_prospeo", _stub_prospeo)
    monkeypatch.setattr(search_operations, "_search_people_blitzapi", _stub_blitz)
    monkeypatch.setattr(search_operations, "_search_people_companyenrich", _stub_never_called)
    monkeypatch.setattr(search_operations, "_search_people_leadmagic_employees", _stub_never_called)
    monkeypatch.setattr(search_operations, "_person_search_provider_order", lambda: ["prospeo", "blitzapi", "companyenrich", "leadmagic"])

    result = await search_operations.execute_person_search(
        input_data={"company_linkedin_url": "https://linkedin.com/company/acme"}
    )

    assert called["blitz"] is True
    assert result["status"] == "found"
