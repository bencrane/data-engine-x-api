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
async def test_lookup_missing_domain() -> None:
    result = await hq_workflow_operations.execute_company_research_lookup_customers_resolved(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["domain"]


@pytest.mark.asyncio
async def test_lookup_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["domain"] == "vanta.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers_resolved",
                "status": "found",
            },
            "mapped": {
                "customers": [
                    {
                        "origin_company_name": "Vanta",
                        "origin_company_domain": "vanta.com",
                        "customer_name": "Notion",
                        "customer_domain": "notion.so",
                        "customer_linkedin_url": "https://www.linkedin.com/company/notion-hq",
                    }
                ],
                "customer_count": 1,
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_customers_resolved", _stub)
    result = await hq_workflow_operations.execute_company_research_lookup_customers_resolved(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["customer_count"] == 1
    assert result["output"]["customers"][0]["customer_name"] == "Notion"
    assert result["output"]["customers"][0]["customer_domain"] == "notion.so"
    assert result["output"]["customers"][0]["customer_linkedin_url"] == "https://www.linkedin.com/company/notion-hq"


@pytest.mark.asyncio
async def test_lookup_empty_customers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["domain"] == "vanta.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers_resolved",
                "status": "not_found",
            },
            "mapped": {
                "customers": [],
                "customer_count": 0,
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_customers_resolved", _stub)
    result = await hq_workflow_operations.execute_company_research_lookup_customers_resolved(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "not_found"
    assert result["output"]["customers"] == []
    assert result["output"]["customer_count"] == 0


@pytest.mark.asyncio
async def test_lookup_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["domain"] == "vanta.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers_resolved",
                "status": "failed",
            },
            "mapped": None,
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_customers_resolved", _stub)
    result = await hq_workflow_operations.execute_company_research_lookup_customers_resolved(
        input_data={"domain": "vanta.com"}
    )
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_lookup_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["domain"] == "vanta.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "lookup_customers_resolved",
                "status": "found",
            },
            "mapped": {
                "customers": [],
                "customer_count": 0,
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "lookup_customers_resolved", _stub)
    result = await hq_workflow_operations.execute_company_research_lookup_customers_resolved(
        input_data={"cumulative_context": {"canonical_domain": "vanta.com"}}
    )
    assert result["status"] == "found"

