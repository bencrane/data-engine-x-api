from __future__ import annotations

from typing import Any

import pytest

from app.services import blitzapi_person_operations


class _SettingsStub:
    blitzapi_api_key = "blitz-key"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(blitzapi_person_operations, "get_settings", lambda: _SettingsStub())


@pytest.mark.asyncio
async def test_waterfall_icp_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MissingKeySettings:
        blitzapi_api_key = None

    monkeypatch.setattr(blitzapi_person_operations, "get_settings", lambda: _MissingKeySettings())

    async def _stub_search_icp_waterfall(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["api_key"] is None
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "waterfall_icp_search",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "pagination": None},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_icp_waterfall", _stub_search_icp_waterfall)
    result = await blitzapi_person_operations.execute_person_search_waterfall_icp_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/acme"}
    )

    assert result["status"] == "skipped"
    assert result["provider_attempts"][0]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_waterfall_icp_missing_linkedin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _should_not_call(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        raise AssertionError("BlitzAPI should not be called when linkedin url is missing")

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_icp_waterfall", _should_not_call)
    result = await blitzapi_person_operations.execute_person_search_waterfall_icp_blitzapi(input_data={})

    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_linkedin_url"]


@pytest.mark.asyncio
async def test_waterfall_icp_success(monkeypatch: pytest.MonkeyPatch) -> None:
    canonical_results = [
        {
            "full_name": "Jane Smith",
            "first_name": "Jane",
            "last_name": "Smith",
            "linkedin_url": "https://www.linkedin.com/in/jane-smith",
            "headline": "VP Sales",
            "current_title": "VP Sales",
            "source_provider": "blitzapi",
        }
    ]

    async def _stub_search_icp_waterfall(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["api_key"] == "blitz-key"
        assert kwargs["company_linkedin_url"] == "https://www.linkedin.com/company/acme"
        assert kwargs["max_results"] == 10
        return {
            "attempt": {"provider": "blitzapi", "action": "waterfall_icp_search", "status": "found"},
            "mapped": {"results": canonical_results, "pagination": {"page": 1, "totalPages": 1, "totalItems": 1}},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_icp_waterfall", _stub_search_icp_waterfall)
    result = await blitzapi_person_operations.execute_person_search_waterfall_icp_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/acme"}
    )

    assert result["status"] == "found"
    assert result["output"]["results_count"] == 1
    assert result["output"]["results"][0]["full_name"] == "Jane Smith"
    assert result["output"]["results"][0]["linkedin_url"] == "https://www.linkedin.com/in/jane-smith"
    assert result["output"]["results"][0]["current_title"] == "VP Sales"


@pytest.mark.asyncio
async def test_waterfall_icp_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_icp_waterfall(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        return {
            "attempt": {"provider": "blitzapi", "action": "waterfall_icp_search", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"page": 1, "totalPages": 1, "totalItems": 0}},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_icp_waterfall", _stub_search_icp_waterfall)
    result = await blitzapi_person_operations.execute_person_search_waterfall_icp_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/acme"}
    )

    assert result["status"] == "not_found"
    assert result["output"]["results"] == []
    assert result["output"]["results_count"] == 0


@pytest.mark.asyncio
async def test_waterfall_icp_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_icp_waterfall(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_linkedin_url"] == "https://www.linkedin.com/company/acme"
        return {
            "attempt": {"provider": "blitzapi", "action": "waterfall_icp_search", "status": "found"},
            "mapped": {"results": [{"full_name": "Alex Doe"}], "pagination": {"page": 1, "totalPages": 1, "totalItems": 1}},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_icp_waterfall", _stub_search_icp_waterfall)
    result = await blitzapi_person_operations.execute_person_search_waterfall_icp_blitzapi(
        input_data={"cumulative_context": {"company_linkedin_url": "https://www.linkedin.com/company/acme"}}
    )

    assert result["status"] == "found"
    assert result["output"]["results_count"] == 1


@pytest.mark.asyncio
async def test_employee_finder_missing_linkedin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _should_not_call(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        raise AssertionError("BlitzAPI should not be called when linkedin url is missing")

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_employees", _should_not_call)
    result = await blitzapi_person_operations.execute_person_search_employee_finder_blitzapi(input_data={})

    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_linkedin_url"]


@pytest.mark.asyncio
async def test_employee_finder_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_employees(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_linkedin_url"] == "https://www.linkedin.com/company/acme"
        return {
            "attempt": {"provider": "blitzapi", "action": "employee_finder", "status": "found"},
            "mapped": {
                "results": [{"full_name": "Taylor Moss", "linkedin_url": "https://www.linkedin.com/in/taylor-moss"}],
                "pagination": {"page": 1, "totalPages": 3, "totalItems": 25},
            },
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_employees", _stub_search_employees)
    result = await blitzapi_person_operations.execute_person_search_employee_finder_blitzapi(
        input_data={"company_linkedin_url": "https://www.linkedin.com/company/acme", "max_results": 10, "page": 1}
    )

    assert result["status"] == "found"
    assert result["output"]["results_count"] == 1
    assert result["output"]["pagination"]["totalItems"] == 25


@pytest.mark.asyncio
async def test_employee_finder_with_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_employees(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["job_level"] == ["VP", "Director"]
        assert kwargs["job_function"] == ["Sales & Business Development"]
        assert kwargs["country_code"] == ["US"]
        return {
            "attempt": {"provider": "blitzapi", "action": "employee_finder", "status": "found"},
            "mapped": {"results": [{"full_name": "Jordan Lee"}], "pagination": {"page": 2, "totalPages": 4, "totalItems": 40}},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_employees", _stub_search_employees)
    result = await blitzapi_person_operations.execute_person_search_employee_finder_blitzapi(
        input_data={
            "company_linkedin_url": "https://www.linkedin.com/company/acme",
            "job_level": ["VP", "Director"],
            "job_function": ["Sales & Business Development"],
            "country_code": ["US"],
            "page": 2,
        }
    )

    assert result["status"] == "found"
    assert result["output"]["results_count"] == 1


@pytest.mark.asyncio
async def test_employee_finder_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_search_employees(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_linkedin_url"] == "https://www.linkedin.com/company/acme"
        return {
            "attempt": {"provider": "blitzapi", "action": "employee_finder", "status": "not_found"},
            "mapped": {"results": [], "pagination": {"page": 1, "totalPages": 1, "totalItems": 0}},
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "search_employees", _stub_search_employees)
    result = await blitzapi_person_operations.execute_person_search_employee_finder_blitzapi(
        input_data={"cumulative_context": {"company_linkedin_url": "https://www.linkedin.com/company/acme"}}
    )

    assert result["status"] == "not_found"
    assert result["output"]["results_count"] == 0


@pytest.mark.asyncio
async def test_find_email_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MissingKeySettings:
        blitzapi_api_key = None

    monkeypatch.setattr(blitzapi_person_operations, "get_settings", lambda: _MissingKeySettings())

    async def _stub_find_work_email(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["api_key"] is None
        return {
            "attempt": {
                "provider": "blitzapi",
                "action": "find_work_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "find_work_email", _stub_find_work_email)
    result = await blitzapi_person_operations.execute_person_contact_resolve_email_blitzapi(
        input_data={"person_linkedin_url": "https://www.linkedin.com/in/jane-smith"}
    )

    assert result["status"] == "skipped"
    assert result["provider_attempts"][0]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_find_email_missing_linkedin_url(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _should_not_call(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        raise AssertionError("BlitzAPI should not be called when linkedin url is missing")

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "find_work_email", _should_not_call)
    result = await blitzapi_person_operations.execute_person_contact_resolve_email_blitzapi(input_data={})

    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["person_linkedin_url"]


@pytest.mark.asyncio
async def test_find_email_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_find_work_email(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["person_linkedin_url"] == "https://www.linkedin.com/in/jane-smith"
        return {
            "attempt": {"provider": "blitzapi", "action": "find_work_email", "status": "found"},
            "mapped": {
                "work_email": "jane@acme.com",
                "all_emails": [{"email": "jane@acme.com", "email_domain": "acme.com"}],
                "source_provider": "blitzapi",
            },
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "find_work_email", _stub_find_work_email)
    result = await blitzapi_person_operations.execute_person_contact_resolve_email_blitzapi(
        input_data={"person_linkedin_url": "https://www.linkedin.com/in/jane-smith"}
    )

    assert result["status"] == "found"
    assert result["output"]["work_email"] == "jane@acme.com"
    assert result["output"]["all_emails"][0]["email"] == "jane@acme.com"


@pytest.mark.asyncio
async def test_find_email_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_find_work_email(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        return {
            "attempt": {"provider": "blitzapi", "action": "find_work_email", "status": "not_found"},
            "mapped": None,
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "find_work_email", _stub_find_work_email)
    result = await blitzapi_person_operations.execute_person_contact_resolve_email_blitzapi(
        input_data={"person_linkedin_url": "https://www.linkedin.com/in/jane-smith"}
    )

    assert result["status"] == "not_found"
    assert result["output"]["work_email"] is None
    assert result["output"]["all_emails"] is None


@pytest.mark.asyncio
async def test_find_email_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub_find_work_email(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["person_linkedin_url"] == "https://www.linkedin.com/in/jane-smith"
        return {
            "attempt": {"provider": "blitzapi", "action": "find_work_email", "status": "found"},
            "mapped": {
                "work_email": "jane@acme.com",
                "all_emails": [{"email": "jane@acme.com"}],
                "source_provider": "blitzapi",
            },
        }

    monkeypatch.setattr(blitzapi_person_operations.blitzapi, "find_work_email", _stub_find_work_email)
    result = await blitzapi_person_operations.execute_person_contact_resolve_email_blitzapi(
        input_data={"cumulative_context": {"person_linkedin_url": "https://www.linkedin.com/in/jane-smith"}}
    )

    assert result["status"] == "found"
    assert result["output"]["work_email"] == "jane@acme.com"
