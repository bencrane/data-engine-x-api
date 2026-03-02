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
async def test_infer_linkedin_url_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_research_infer_linkedin_url(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name"]


@pytest.mark.asyncio
async def test_infer_linkedin_url_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "infer_linkedin_url", "status": "found"},
            "mapped": {
                "company_linkedin_url": "https://www.linkedin.com/company/salesforce",
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "infer_linkedin_url", _stub)
    result = await hq_workflow_operations.execute_company_research_infer_linkedin_url(
        input_data={"company_name": "Salesforce", "domain": "salesforce.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://www.linkedin.com/company/salesforce"


@pytest.mark.asyncio
async def test_infer_linkedin_url_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "infer_linkedin_url", "status": "not_found"},
            "mapped": {"company_linkedin_url": None, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "infer_linkedin_url", _stub)
    result = await hq_workflow_operations.execute_company_research_infer_linkedin_url(
        input_data={"company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_infer_linkedin_url_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "infer_linkedin_url", "status": "found"},
            "mapped": {"company_linkedin_url": "https://www.linkedin.com/company/salesforce", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "infer_linkedin_url", _stub)
    result = await hq_workflow_operations.execute_company_research_infer_linkedin_url(
        input_data={"cumulative_context": {"canonical_name": "Salesforce", "canonical_domain": "salesforce.com"}}
    )
    assert result["status"] == "found"


@pytest.mark.asyncio
async def test_icp_job_titles_gemini_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_research_icp_job_titles_gemini(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name|domain"]


@pytest.mark.asyncio
async def test_icp_job_titles_gemini_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "research_icp_job_titles_gemini", "status": "found"},
            "mapped": {
                "inferred_product": "CRM platform",
                "buyer_persona": "Sales leaders",
                "titles": [{"title": "VP of Sales", "role": "champion"}],
                "champion_titles": ["VP of Sales"],
                "evaluator_titles": ["Sales Operations Manager"],
                "decision_maker_titles": ["CRO"],
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "research_icp_job_titles_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_icp_job_titles_gemini(
        input_data={"company_name": "Salesforce", "domain": "salesforce.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["champion_titles"] == ["VP of Sales"]


@pytest.mark.asyncio
async def test_icp_job_titles_gemini_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "research_icp_job_titles_gemini", "status": "not_found"},
            "mapped": {"source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "research_icp_job_titles_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_icp_job_titles_gemini(
        input_data={"domain": "unknown.example"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_icp_job_titles_gemini_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        assert kwargs["company_description"] == "CRM software"
        return {
            "attempt": {"provider": "revenueinfra", "action": "research_icp_job_titles_gemini", "status": "found"},
            "mapped": {"source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "research_icp_job_titles_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_icp_job_titles_gemini(
        input_data={
            "cumulative_context": {
                "name": "Salesforce",
                "company_domain": "salesforce.com",
                "description_raw": "CRM software",
            }
        }
    )
    assert result["status"] == "found"


@pytest.mark.asyncio
async def test_discover_customers_gemini_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_research_discover_customers_gemini(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name|domain"]


@pytest.mark.asyncio
async def test_discover_customers_gemini_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "discover_customers_gemini", "status": "found"},
            "mapped": {
                "customers": [{"name": "Toyota", "domain": "toyota.com"}],
                "customer_count": 1,
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "discover_customers_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_discover_customers_gemini(
        input_data={"company_name": "Salesforce", "domain": "salesforce.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["customer_count"] == 1


@pytest.mark.asyncio
async def test_discover_customers_gemini_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "discover_customers_gemini", "status": "not_found"},
            "mapped": {"customers": [], "customer_count": 0, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "discover_customers_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_discover_customers_gemini(
        input_data={"company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_discover_customers_gemini_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "discover_customers_gemini", "status": "found"},
            "mapped": {"customers": [], "customer_count": 0, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "discover_customers_gemini", _stub)
    result = await hq_workflow_operations.execute_company_research_discover_customers_gemini(
        input_data={"cumulative_context": {"canonical_name": "Salesforce", "canonical_domain": "salesforce.com"}}
    )
    assert result["status"] == "found"


@pytest.mark.asyncio
async def test_icp_criterion_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_derive_icp_criterion(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name|domain"]


@pytest.mark.asyncio
async def test_icp_criterion_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["customers"] == ["Toyota", "American Express"]
        assert kwargs["icp_titles"] == ["VP of Sales", "CRO"]
        return {
            "attempt": {"provider": "revenueinfra", "action": "generate_icp_criterion", "status": "found"},
            "mapped": {"icp_criterion": "Enterprise 500+ employees", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "generate_icp_criterion", _stub)
    result = await hq_workflow_operations.execute_company_derive_icp_criterion(
        input_data={
            "company_name": "Salesforce",
            "customers": [{"name": "Toyota"}, "American Express"],
            "titles": [{"title": "VP of Sales"}, "CRO"],
        }
    )
    assert result["status"] == "found"
    assert result["output"]["icp_criterion"] == "Enterprise 500+ employees"


@pytest.mark.asyncio
async def test_icp_criterion_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "generate_icp_criterion", "status": "not_found"},
            "mapped": {"icp_criterion": None, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "generate_icp_criterion", _stub)
    result = await hq_workflow_operations.execute_company_derive_icp_criterion(
        input_data={"company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_icp_criterion_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["domain"] == "salesforce.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "generate_icp_criterion", "status": "found"},
            "mapped": {"icp_criterion": "Enterprise criteria", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "generate_icp_criterion", _stub)
    result = await hq_workflow_operations.execute_company_derive_icp_criterion(
        input_data={"cumulative_context": {"name": "Salesforce", "domain": "salesforce.com"}}
    )
    assert result["status"] == "found"


@pytest.mark.asyncio
async def test_icp_criterion_list_extraction_strings_and_dicts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _stub(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "attempt": {"provider": "revenueinfra", "action": "generate_icp_criterion", "status": "found"},
            "mapped": {"icp_criterion": "criteria", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "generate_icp_criterion", _stub)
    result = await hq_workflow_operations.execute_company_derive_icp_criterion(
        input_data={
            "company_name": "Salesforce",
            "cumulative_context": {
                "customers": [{"name": "Toyota"}, "T-Mobile"],
                "champion_titles": ["VP Sales", "CRO"],
            },
        }
    )
    assert result["status"] == "found"
    assert captured["customers"] == ["Toyota", "T-Mobile"]
    assert captured["icp_titles"] == ["VP Sales", "CRO"]


@pytest.mark.asyncio
async def test_salesnav_url_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_derive_salesnav_url(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["org_id", "company_name"]


@pytest.mark.asyncio
async def test_salesnav_url_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["org_id"] == "12345"
        assert kwargs["company_name"] == "Salesforce"
        assert kwargs["titles"] == ["VP of Sales", "CRO"]
        return {
            "attempt": {"provider": "revenueinfra", "action": "build_salesnav_url", "status": "found"},
            "mapped": {
                "salesnav_url": "https://www.linkedin.com/sales/search/people?...",
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "build_salesnav_url", _stub)
    result = await hq_workflow_operations.execute_company_derive_salesnav_url(
        input_data={
            "org_id": "12345",
            "company_name": "Salesforce",
            "titles": [{"title": "VP of Sales"}, "CRO"],
        }
    )
    assert result["status"] == "found"
    assert result["output"]["salesnav_url"] == "https://www.linkedin.com/sales/search/people?..."


@pytest.mark.asyncio
async def test_salesnav_url_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "build_salesnav_url", "status": "not_found"},
            "mapped": {"salesnav_url": None, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "build_salesnav_url", _stub)
    result = await hq_workflow_operations.execute_company_derive_salesnav_url(
        input_data={"org_id": "12345", "company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_salesnav_url_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["org_id"] == "12345"
        assert kwargs["company_name"] == "Salesforce"
        return {
            "attempt": {"provider": "revenueinfra", "action": "build_salesnav_url", "status": "found"},
            "mapped": {"salesnav_url": "https://www.linkedin.com/sales/search/people?...", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "build_salesnav_url", _stub)
    result = await hq_workflow_operations.execute_company_derive_salesnav_url(
        input_data={"cumulative_context": {"orgId": "12345", "canonical_name": "Salesforce"}}
    )
    assert result["status"] == "found"


@pytest.mark.asyncio
async def test_salesnav_url_list_extraction_strings_and_dicts(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def _stub(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "attempt": {"provider": "revenueinfra", "action": "build_salesnav_url", "status": "found"},
            "mapped": {"salesnav_url": "https://www.linkedin.com/sales/search/people?...", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "build_salesnav_url", _stub)
    result = await hq_workflow_operations.execute_company_derive_salesnav_url(
        input_data={
            "company_name": "Salesforce",
            "cumulative_context": {
                "company_linkedin_id": "12345",
                "champion_titles": ["VP Sales", "CRO"],
                "excluded_seniority": ["Entry", "Training"],
                "companyHQRegions": ["United States"],
            },
            "titles": [{"title": "Sales Director"}],
            "regions": ["United States"],
        }
    )
    assert result["status"] == "found"
    assert captured["titles"] == ["Sales Director"]
    assert captured["excluded_seniority"] == ["Entry", "Training"]
    assert captured["company_hq_regions"] == ["United States"]


@pytest.mark.asyncio
async def test_evaluate_icp_fit_missing_required_inputs() -> None:
    result = await hq_workflow_operations.execute_company_derive_evaluate_icp_fit(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["criterion"]


@pytest.mark.asyncio
async def test_evaluate_icp_fit_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["criterion"] == "Enterprise companies 500+ employees"
        assert kwargs["company_name"] == "JPMorgan Chase"
        return {
            "attempt": {"provider": "revenueinfra", "action": "evaluate_icp_fit", "status": "found"},
            "mapped": {
                "icp_fit_verdict": "strong_fit",
                "icp_fit_reasoning": "Clear alignment",
                "source_provider": "revenueinfra",
            },
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "evaluate_icp_fit", _stub)
    result = await hq_workflow_operations.execute_company_derive_evaluate_icp_fit(
        input_data={
            "criterion": "Enterprise companies 500+ employees",
            "company_name": "JPMorgan Chase",
            "domain": "jpmorganchase.com",
        }
    )
    assert result["status"] == "found"
    assert result["output"]["icp_fit_verdict"] == "strong_fit"


@pytest.mark.asyncio
async def test_evaluate_icp_fit_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {
            "attempt": {"provider": "revenueinfra", "action": "evaluate_icp_fit", "status": "not_found"},
            "mapped": {"icp_fit_verdict": None, "icp_fit_reasoning": None, "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "evaluate_icp_fit", _stub)
    result = await hq_workflow_operations.execute_company_derive_evaluate_icp_fit(
        input_data={"criterion": "Enterprise companies 500+ employees", "company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_evaluate_icp_fit_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _stub(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["criterion"] == "Enterprise companies 500+ employees"
        assert kwargs["company_name"] == "JPMorgan Chase"
        assert kwargs["domain"] == "jpmorganchase.com"
        assert kwargs["description"] == "Global financial services firm"
        return {
            "attempt": {"provider": "revenueinfra", "action": "evaluate_icp_fit", "status": "found"},
            "mapped": {"icp_fit_verdict": "strong_fit", "icp_fit_reasoning": "Clear alignment", "source_provider": "revenueinfra"},
        }

    monkeypatch.setattr(hq_workflow_operations.revenueinfra, "evaluate_icp_fit", _stub)
    result = await hq_workflow_operations.execute_company_derive_evaluate_icp_fit(
        input_data={
            "cumulative_context": {
                "icp_criterion": "Enterprise companies 500+ employees",
                "canonical_name": "JPMorgan Chase",
                "company_domain": "jpmorganchase.com",
                "description_raw": "Global financial services firm",
            }
        }
    )
    assert result["status"] == "found"
