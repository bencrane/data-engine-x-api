from __future__ import annotations

from typing import Any

import pytest

from app.services import hq_workflow_operations


class _SettingsStub:
    revenueinfra_api_url = "https://api.revenueinfra.com"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hq_workflow_operations, "get_settings", lambda: _SettingsStub())


@pytest.mark.asyncio
async def test_lookup_missing_company_name() -> None:
    result = await hq_workflow_operations.execute_company_resolve_domain_from_name_hq(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name"]


@pytest.mark.asyncio
async def test_lookup_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Datadog"
        return {
            "attempt": {"provider": "revenueinfra", "action": "lookup_company_by_name", "status": "found"},
            "mapped": {
                "company_domain": "datadoghq.com",
                "company_linkedin_url": "https://www.linkedin.com/company/datadog",
                "match_type": "exact_cleaned_name",
                "matched_name": "Datadog",
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_company_by_name", _stub)
    result = await hq_workflow_operations.execute_company_resolve_domain_from_name_hq(
        input_data={"company_name": "Datadog"}
    )
    assert result["status"] == "found"
    assert result["output"]["company_domain"] == "datadoghq.com"
    assert result["output"]["company_linkedin_url"] == "https://www.linkedin.com/company/datadog"
    assert result["output"]["match_type"] == "exact_cleaned_name"


@pytest.mark.asyncio
async def test_lookup_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "lookup_company_by_name", "status": "not_found"},
            "mapped": None,
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_company_by_name", _stub)
    result = await hq_workflow_operations.execute_company_resolve_domain_from_name_hq(
        input_data={"company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_lookup_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_company_by_name",
                "status": "failed",
                "http_status": 500,
            },
            "mapped": None,
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_company_by_name", _stub)
    result = await hq_workflow_operations.execute_company_resolve_domain_from_name_hq(
        input_data={"company_name": "Datadog"}
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_lookup_reads_current_company_name(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Datadog"
        return {
            "attempt": {"provider": "revenueinfra", "action": "lookup_company_by_name", "status": "found"},
            "mapped": {
                "company_domain": "datadoghq.com",
                "company_linkedin_url": "https://www.linkedin.com/company/datadog",
                "match_type": "exact_cleaned_name",
                "matched_name": "Datadog",
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_company_by_name", _stub)
    result = await hq_workflow_operations.execute_company_resolve_domain_from_name_hq(
        input_data={"cumulative_context": {"current_company_name": "Datadog"}}
    )
    assert result["status"] == "found"
    assert result["output"]["company_domain"] == "datadoghq.com"
