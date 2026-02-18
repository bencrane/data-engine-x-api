from __future__ import annotations

import pytest

from app.contracts.courtlistener import (
    BankruptcyFilingSearchOutput,
    CourtFilingSearchOutput,
    DocketDetailOutput,
)
from app.services.courtlistener_operations import (
    execute_company_research_check_court_filings,
    execute_company_research_get_docket_detail,
    execute_company_signal_bankruptcy_filings,
)


@pytest.fixture(autouse=True)
def _mock_courtlistener_settings(monkeypatch):
    class _Settings:
        courtlistener_api_key = "test-courtlistener-key"

    monkeypatch.setattr(
        "app.services.courtlistener_operations.get_settings",
        lambda: _Settings(),
    )


@pytest.mark.asyncio
async def test_check_court_filings_missing_company_name_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when company_name is missing")

    monkeypatch.setattr(
        "app.providers.courtlistener.search_court_filings",
        _should_not_be_called,
    )

    result = await execute_company_research_check_court_filings(
        input_data={
            "noise": [{"foo": "bar"}],
            "cumulative_context": {"history": [{"operation_id": "company.enrich.profile"}]},
            "step_config": {"date_filed_gte": "2025-01-01"},
        }
    )

    assert result["operation_id"] == "company.research.check_court_filings"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_check_court_filings_success_validates_contract(monkeypatch):
    async def _fake_search_court_filings(
        *,
        api_key: str | None,
        company_name: str | None,
        court_type: str | None,
        date_filed_gte: str | None,
        date_filed_lte: str | None,
    ):
        assert api_key == "test-courtlistener-key"
        assert company_name == "Acme Logistics"
        assert court_type == "nysb"
        assert date_filed_gte == "2025-01-01"
        assert date_filed_lte == "2025-01-31"
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_court_filings",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "docket_id": 1001,
                        "case_name": "In re: Acme Logistics, LLC",
                        "court": "nysb",
                        "court_citation": "Bankr. S.D.N.Y.",
                        "docket_number": "25-10001",
                        "date_filed": "2025-01-02",
                        "date_terminated": None,
                        "judge": "Judge Example",
                        "party_names": ["Acme Logistics, LLC", "IRS"],
                        "attorneys": ["Jane Doe, Esq."],
                        "relevance_score": 14.2,
                        "url": "https://www.courtlistener.com/docket/1001/in-re-acme-logistics-llc/",
                    }
                ],
                "result_count": 1,
            },
        }

    monkeypatch.setattr(
        "app.providers.courtlistener.search_court_filings",
        _fake_search_court_filings,
    )

    result = await execute_company_research_check_court_filings(
        input_data={
            "noise": {"unrelated": True},
            "cumulative_context": {
                "company_profile": {"company_name": "Acme Logistics"},
                "timeline": [{"step": "prior_step"}],
            },
            "step_config": {
                "court_type": "nysb",
                "date_filed_gte": "2025-01-01",
                "date_filed_lte": "2025-01-31",
            },
        }
    )

    assert result["operation_id"] == "company.research.check_court_filings"
    assert result["status"] == "found"
    validated = CourtFilingSearchOutput.model_validate(result["output"])
    assert validated.result_count == 1
    assert validated.results[0].docket_id == 1001
    assert result["output"]["court_filing_count"] == 1
    assert result["output"]["court_filings"][0]["case_name"] == "In re: Acme Logistics, LLC"


@pytest.mark.asyncio
async def test_check_court_filings_no_results_returns_not_found(monkeypatch):
    async def _fake_search_court_filings(**kwargs):  # noqa: ARG001
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_court_filings",
                "status": "not_found",
                "http_status": 200,
            },
            "mapped": {
                "results": [],
                "result_count": 0,
            },
        }

    monkeypatch.setattr(
        "app.providers.courtlistener.search_court_filings",
        _fake_search_court_filings,
    )

    result = await execute_company_research_check_court_filings(
        input_data={
            "cumulative_context": {"company_name": "Acme Logistics"},
            "step_config": {"date_filed_gte": "2025-01-01"},
            "noise": ["x", {"nested": {"ignored": True}}],
        }
    )

    assert result["status"] == "not_found"
    validated = CourtFilingSearchOutput.model_validate(result["output"])
    assert validated.results == []
    assert validated.result_count == 0


@pytest.mark.asyncio
async def test_bankruptcy_filings_missing_required_date_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when date_filed_gte is missing")

    monkeypatch.setattr(
        "app.providers.courtlistener.search_bankruptcy_filings",
        _should_not_be_called,
    )

    result = await execute_company_signal_bankruptcy_filings(
        input_data={
            "noise": {"ignored": 1},
            "step_config": {"date_filed_lte": "2025-01-31"},
            "cumulative_context": {"metadata": {"pipeline_run_id": "run_1"}},
        }
    )

    assert result["operation_id"] == "company.signal.bankruptcy_filings"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["date_filed_gte"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_bankruptcy_filings_success_validates_contract_with_multiple_filings(monkeypatch):
    async def _fake_search_bankruptcy_filings(
        *,
        api_key: str | None,
        date_filed_gte: str | None,
        date_filed_lte: str | None,
        courts: list[str] | None,
    ):
        assert api_key == "test-courtlistener-key"
        assert date_filed_gte == "2025-01-01"
        assert date_filed_lte == "2025-01-31"
        assert courts == ["deb", "nysb"]
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_bankruptcy_filings",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "docket_id": 2001,
                        "case_name": "In re: Debtor One",
                        "case_name_short": "Debtor One",
                        "court_id": "deb",
                        "court_citation": "Bankr. D. Del.",
                        "docket_number": "25-10011",
                        "date_filed": "2025-01-03",
                        "date_terminated": None,
                        "date_last_filing": "2025-01-10",
                        "judge": "Judge One",
                        "pacer_case_id": "pcid-1",
                        "url": "https://www.courtlistener.com/docket/2001/in-re-debtor-one/",
                    },
                    {
                        "docket_id": 2002,
                        "case_name": "In re: Debtor Two",
                        "case_name_short": "Debtor Two",
                        "court_id": "nysb",
                        "court_citation": "Bankr. S.D.N.Y.",
                        "docket_number": "25-10012",
                        "date_filed": "2025-01-05",
                        "date_terminated": None,
                        "date_last_filing": "2025-01-12",
                        "judge": "Judge Two",
                        "pacer_case_id": "pcid-2",
                        "url": "https://www.courtlistener.com/docket/2002/in-re-debtor-two/",
                    },
                ],
                "result_count": 2,
            },
        }

    monkeypatch.setattr(
        "app.providers.courtlistener.search_bankruptcy_filings",
        _fake_search_bankruptcy_filings,
    )

    result = await execute_company_signal_bankruptcy_filings(
        input_data={
            "noise": [{"unused": "value"}],
            "step_config": {
                "date_filed_gte": "2025-01-01",
                "date_filed_lte": "2025-01-31",
                "courts": ["deb", "nysb"],
            },
            "cumulative_context": {"history": [{"step": "seed"}]},
        }
    )

    assert result["operation_id"] == "company.signal.bankruptcy_filings"
    assert result["status"] == "found"
    validated = BankruptcyFilingSearchOutput.model_validate(result["output"])
    assert validated.result_count == 2
    assert validated.results[0].docket_id == 2001
    assert validated.results[1].docket_id == 2002


@pytest.mark.asyncio
async def test_get_docket_detail_missing_docket_id_fails_without_provider_call(monkeypatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called when docket_id is missing")

    monkeypatch.setattr(
        "app.providers.courtlistener.get_docket_detail",
        _should_not_be_called,
    )

    result = await execute_company_research_get_docket_detail(
        input_data={
            "noise": {"ignored": True},
            "cumulative_context": {"company_name": "Acme"},
        }
    )

    assert result["operation_id"] == "company.research.get_docket_detail"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["docket_id"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_get_docket_detail_success_validates_contract(monkeypatch):
    async def _fake_get_docket_detail(*, api_key: str | None, docket_id: int | str | None):
        assert api_key == "test-courtlistener-key"
        assert docket_id == 3001
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "get_docket_detail",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "docket_id": 3001,
                "case_name": "In re: Acme Holdings",
                "court_id": "nysb",
                "docket_number": "25-10021",
                "date_filed": "2025-01-06",
                "date_terminated": None,
                "parties": ["Acme Holdings", "United States Trustee"],
                "judge": "Judge Example",
                "url": "https://www.courtlistener.com/docket/3001/in-re-acme-holdings/",
            },
        }

    monkeypatch.setattr(
        "app.providers.courtlistener.get_docket_detail",
        _fake_get_docket_detail,
    )

    result = await execute_company_research_get_docket_detail(
        input_data={
            "noise": ["extra", {"ignored": 1}],
            "cumulative_context": {
                "court_filings": [{"docket_id": 3001}],
                "history": [{"step": "company.research.check_court_filings"}],
            },
        }
    )

    assert result["operation_id"] == "company.research.get_docket_detail"
    assert result["status"] == "found"
    validated = DocketDetailOutput.model_validate(result["output"])
    assert validated.docket_id == 3001
    assert validated.case_name == "In re: Acme Holdings"
    assert validated.parties == ["Acme Holdings", "United States Trustee"]
