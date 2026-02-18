from __future__ import annotations

import pytest

from app.contracts.sec_filings import FetchSECFilingsOutput, SECAnalysisOutput
from app.services.sec_filing_operations import (
    execute_company_analyze_sec_10k,
    execute_company_analyze_sec_10q,
    execute_company_analyze_sec_8k_executive,
    execute_company_research_fetch_sec_filings,
)


@pytest.fixture(autouse=True)
def _mock_sec_settings(monkeypatch):
    class _Settings:
        revenueinfra_api_url = "https://api.revenueinfra.com"

    monkeypatch.setattr(
        "app.services.sec_filing_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_fetch_sec_filings_success_validates_contract_and_all_filing_types(monkeypatch):
    async def _fake_fetch(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "apple.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "fetch_sec_filings",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "cik": "320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "latest_10k": {
                    "filing_date": "2024-11-01",
                    "report_date": "2024-09-28",
                    "accession_number": "0000320193-24-000123",
                    "document_url": "https://www.sec.gov/10k",
                    "items": None,
                },
                "latest_10q": {
                    "filing_date": "2025-01-31",
                    "report_date": "2024-12-28",
                    "accession_number": "0000320193-25-000010",
                    "document_url": "https://www.sec.gov/10q",
                    "items": None,
                },
                "recent_8k_executive_changes": [
                    {
                        "filing_date": "2024-08-15",
                        "report_date": None,
                        "accession_number": None,
                        "document_url": "https://www.sec.gov/8k-exec",
                        "items": ["5.02"],
                    }
                ],
                "recent_8k_earnings": [
                    {
                        "filing_date": "2024-10-01",
                        "report_date": None,
                        "accession_number": None,
                        "document_url": "https://www.sec.gov/8k-earnings",
                        "items": ["2.02"],
                    }
                ],
                "recent_8k_material_contracts": [
                    {
                        "filing_date": "2024-07-10",
                        "report_date": None,
                        "accession_number": None,
                        "document_url": "https://www.sec.gov/8k-contracts",
                        "items": ["1.01"],
                    }
                ],
            },
        }

    monkeypatch.setattr("app.providers.revenueinfra.fetch_sec_filings", _fake_fetch)

    result = await execute_company_research_fetch_sec_filings(
        input_data={
            "noise": {"nested": [1, {"ignore": True}]},
            "cumulative_context": {
                "company_profile": {"company_domain": "apple.com", "company_name": "Apple Inc."},
                "timeline": [{"step": "company.enrich.profile"}],
            },
        }
    )

    assert isinstance(result.get("run_id"), str)
    assert result["operation_id"] == "company.research.fetch_sec_filings"
    assert result["status"] == "found"
    validated = FetchSECFilingsOutput.model_validate(result["output"])
    assert validated.cik == "320193"
    assert validated.latest_10k is not None
    assert validated.latest_10q is not None
    assert isinstance(validated.recent_8k_executive_changes, list)
    assert isinstance(validated.recent_8k_earnings, list)
    assert isinstance(validated.recent_8k_material_contracts, list)
    assert validated.source_provider == "revenueinfra"


@pytest.mark.asyncio
async def test_fetch_sec_filings_missing_domain_returns_failed(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_domain is missing")

    monkeypatch.setattr("app.providers.revenueinfra.fetch_sec_filings", _should_not_be_called)

    result = await execute_company_research_fetch_sec_filings(
        input_data={"cumulative_context": {"company_profile": {"company_name": "Apple Inc."}}}
    )

    assert result["operation_id"] == "company.research.fetch_sec_filings"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_fetch_sec_filings_no_filings_returns_not_found(monkeypatch):
    async def _fake_fetch(*, base_url: str, domain: str):
        assert isinstance(base_url, str)
        assert domain == "apple.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "fetch_sec_filings",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "cik": "320193",
                "ticker": "AAPL",
                "company_name": "Apple Inc.",
                "latest_10k": None,
                "latest_10q": None,
                "recent_8k_executive_changes": [],
                "recent_8k_earnings": [],
                "recent_8k_material_contracts": [],
            },
        }

    monkeypatch.setattr("app.providers.revenueinfra.fetch_sec_filings", _fake_fetch)

    result = await execute_company_research_fetch_sec_filings(
        input_data={"cumulative_context": {"company_domain": "apple.com"}}
    )

    assert result["status"] == "not_found"
    validated = FetchSECFilingsOutput.model_validate(result["output"])
    assert validated.latest_10k is None
    assert validated.latest_10q is None
    assert validated.recent_8k_executive_changes == []


@pytest.mark.asyncio
async def test_analyze_sec_10k_success_validates_shared_analysis_contract(monkeypatch):
    async def _fake_analyze(*, document_url: str, domain: str | None, company_name: str | None):
        assert document_url == "https://www.sec.gov/10k"
        assert domain == "apple.com"
        assert company_name == "Apple Inc."
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "analyze_10k",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "filing_type": "10-K",
                "document_url": document_url,
                "domain": domain,
                "company_name": company_name,
                "analysis": "## Business Overview\nApple builds devices.",
            },
        }

    monkeypatch.setattr("app.providers.revenueinfra.analyze_10k", _fake_analyze)

    result = await execute_company_analyze_sec_10k(
        input_data={
            "noise": ["x", {"ignore": True}],
            "cumulative_context": {
                "company_domain": "apple.com",
                "company_name": "Apple Inc.",
                "latest_10k": {"document_url": "https://www.sec.gov/10k"},
            },
        }
    )

    assert result["operation_id"] == "company.analyze.sec_10k"
    assert result["status"] == "found"
    validated = SECAnalysisOutput.model_validate(result["output"])
    assert validated.filing_type == "10-K"
    assert validated.document_url == "https://www.sec.gov/10k"
    assert "Business Overview" in validated.analysis


@pytest.mark.asyncio
async def test_analyze_sec_10k_missing_document_url_returns_failed(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when latest_10k.document_url is missing")

    monkeypatch.setattr("app.providers.revenueinfra.analyze_10k", _should_not_be_called)

    result = await execute_company_analyze_sec_10k(
        input_data={"cumulative_context": {"company_domain": "apple.com"}}
    )

    assert result["operation_id"] == "company.analyze.sec_10k"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["latest_10k.document_url"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_analyze_sec_10q_success(monkeypatch):
    async def _fake_analyze(*, document_url: str, domain: str | None, company_name: str | None):
        assert document_url == "https://www.sec.gov/10q"
        assert domain == "google.com"
        assert company_name == "Alphabet Inc."
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "analyze_10q",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "filing_type": "10-Q",
                "document_url": document_url,
                "domain": domain,
                "company_name": company_name,
                "analysis": "## Quarter Highlights\nRevenue expanded.",
            },
        }

    monkeypatch.setattr("app.providers.revenueinfra.analyze_10q", _fake_analyze)

    result = await execute_company_analyze_sec_10q(
        input_data={
            "noise": {"x": 1},
            "cumulative_context": {
                "company_profile": {"company_domain": "google.com", "company_name": "Alphabet Inc."},
                "latest_10q": {"document_url": "https://www.sec.gov/10q"},
            },
        }
    )

    assert result["operation_id"] == "company.analyze.sec_10q"
    assert result["status"] == "found"
    validated = SECAnalysisOutput.model_validate(result["output"])
    assert validated.filing_type == "10-Q"
    assert "Quarter Highlights" in validated.analysis


@pytest.mark.asyncio
async def test_analyze_sec_8k_executive_success_uses_most_recent_filing(monkeypatch):
    async def _fake_analyze(*, document_url: str, domain: str | None, company_name: str | None):
        assert document_url == "https://www.sec.gov/8k-exec-most-recent"
        assert domain == "example.com"
        assert company_name == "Example Corp"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "analyze_8k_executive",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "filing_type": "8-K-executive",
                "document_url": document_url,
                "domain": domain,
                "company_name": company_name,
                "analysis": "## Who Left?\nThe CFO resigned.",
            },
        }

    monkeypatch.setattr("app.providers.revenueinfra.analyze_8k_executive", _fake_analyze)

    result = await execute_company_analyze_sec_8k_executive(
        input_data={
            "noise": [True, None],
            "cumulative_context": {
                "company_domain": "example.com",
                "company_name": "Example Corp",
                "recent_8k_executive_changes": [
                    {"document_url": "https://www.sec.gov/8k-exec-most-recent"},
                    {"document_url": "https://www.sec.gov/8k-exec-older"},
                ],
            },
        }
    )

    assert result["operation_id"] == "company.analyze.sec_8k_executive"
    assert result["status"] == "found"
    validated = SECAnalysisOutput.model_validate(result["output"])
    assert validated.filing_type == "8-K-executive"
    assert validated.document_url == "https://www.sec.gov/8k-exec-most-recent"
    assert "Who Left?" in validated.analysis


@pytest.mark.asyncio
async def test_analyze_sec_8k_executive_no_filings_returns_not_found(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when no executive filings exist")

    monkeypatch.setattr("app.providers.revenueinfra.analyze_8k_executive", _should_not_be_called)

    result = await execute_company_analyze_sec_8k_executive(
        input_data={"cumulative_context": {"company_domain": "example.com", "recent_8k_executive_changes": []}}
    )

    assert result["operation_id"] == "company.analyze.sec_8k_executive"
    assert result["status"] == "not_found"
    assert result["provider_attempts"] == []
