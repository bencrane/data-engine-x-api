from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from app.contracts.job_validation import JobValidationOutput
from app.services import research_operations
from app.services.research_operations import execute_job_validate_is_active


@pytest.fixture(autouse=True)
def _mock_research_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        research_operations,
        "get_settings",
        lambda: SimpleNamespace(
            revenueinfra_api_url="https://api.revenueinfra.com",
            revenueinfra_ingest_api_key="test-ingest-key",
        ),
    )


@pytest.mark.asyncio
async def test_validate_job_active_missing_domain(monkeypatch: pytest.MonkeyPatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called without company_domain")

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _should_not_be_called)

    result = await execute_job_validate_is_active(
        input_data={"job_title": "Senior Data Engineer"}
    )

    assert result["operation_id"] == "job.validate.is_active"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_domain"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_validate_job_active_missing_title(monkeypatch: pytest.MonkeyPatch):
    async def _should_not_be_called(**kwargs):  # noqa: ARG001
        raise AssertionError("Provider should not be called without job_title")

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _should_not_be_called)

    result = await execute_job_validate_is_active(
        input_data={"company_domain": "stripe.com"}
    )

    assert result["operation_id"] == "job.validate.is_active"
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["job_title"]
    assert result["provider_attempts"] == []


@pytest.mark.asyncio
async def test_validate_job_active_success_active(monkeypatch: pytest.MonkeyPatch):
    async def _fake_validate_job_active(**kwargs):
        assert kwargs["company_domain"] == "stripe.com"
        assert kwargs["job_title"] == "Senior Data Engineer"
        assert kwargs["company_name"] == "Stripe"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "validate_job_active",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "validation_result": "active",
                "confidence": "high",
                "indeed_found": True,
                "indeed_match_count": 2,
                "indeed_any_expired": False,
                "indeed_matched_by": "domain",
                "linkedin_found": True,
                "linkedin_match_count": 1,
                "linkedin_matched_by": "domain",
            },
        }

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _fake_validate_job_active)

    result = await execute_job_validate_is_active(
        input_data={
            "company_domain": "stripe.com",
            "job_title": "Senior Data Engineer",
            "company_name": "Stripe",
        }
    )

    assert result["status"] == "found"
    validated = JobValidationOutput.model_validate(result["output"])
    assert validated.validation_result == "active"
    assert validated.confidence == "high"
    assert validated.indeed_found is True
    assert validated.indeed_match_count == 2
    assert validated.linkedin_found is True
    assert validated.linkedin_match_count == 1


@pytest.mark.asyncio
async def test_validate_job_active_success_expired(monkeypatch: pytest.MonkeyPatch):
    async def _fake_validate_job_active(**kwargs):  # noqa: ARG001
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "validate_job_active",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "validation_result": "expired",
                "confidence": "high",
                "indeed_found": True,
                "indeed_match_count": 1,
                "indeed_any_expired": True,
                "indeed_matched_by": "domain",
                "linkedin_found": False,
                "linkedin_match_count": 0,
                "linkedin_matched_by": None,
            },
        }

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _fake_validate_job_active)

    result = await execute_job_validate_is_active(
        input_data={"company_domain": "stripe.com", "job_title": "Senior Data Engineer"}
    )

    assert result["status"] == "found"
    assert result["output"]["validation_result"] == "expired"


@pytest.mark.asyncio
async def test_validate_job_active_success_unknown(monkeypatch: pytest.MonkeyPatch):
    async def _fake_validate_job_active(**kwargs):  # noqa: ARG001
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "validate_job_active",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "validation_result": "unknown",
                "confidence": "low",
                "indeed_found": False,
                "indeed_match_count": 0,
                "indeed_any_expired": False,
                "indeed_matched_by": None,
                "linkedin_found": False,
                "linkedin_match_count": 0,
                "linkedin_matched_by": None,
            },
        }

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _fake_validate_job_active)

    result = await execute_job_validate_is_active(
        input_data={"company_domain": "stripe.com", "job_title": "Senior Data Engineer"}
    )

    assert result["status"] == "found"
    assert result["output"]["validation_result"] == "unknown"


@pytest.mark.asyncio
async def test_validate_job_active_api_error(monkeypatch: pytest.MonkeyPatch):
    class _FakeResponse:
        status_code = 500
        text = '{"error":"internal"}'

        @staticmethod
        def json() -> dict[str, Any]:
            return {"error": "internal"}

    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]):
            assert url == "https://api.revenueinfra.com/api/ingest/brightdata/validate-job"
            assert headers["x-api-key"] == "test-ingest-key"
            assert json["company_domain"] == "stripe.com"
            return _FakeResponse()

    monkeypatch.setattr("app.providers.revenueinfra.validate_job.httpx.AsyncClient", _FakeAsyncClient)

    result = await execute_job_validate_is_active(
        input_data={"company_domain": "stripe.com", "job_title": "Senior Data Engineer"}
    )

    assert result["status"] == "failed"
    assert result["provider_attempts"][0]["http_status"] == 500


@pytest.mark.asyncio
async def test_validate_job_active_timeout(monkeypatch: pytest.MonkeyPatch):
    class _FakeAsyncClient:
        def __init__(self, *, timeout: float):
            assert timeout == 30.0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]):  # noqa: ARG002
            raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.providers.revenueinfra.validate_job.httpx.AsyncClient", _FakeAsyncClient)

    result = await execute_job_validate_is_active(
        input_data={"company_domain": "stripe.com", "job_title": "Senior Data Engineer"}
    )

    assert result["status"] == "failed"
    assert result["provider_attempts"][0]["error"] == "timeout"


@pytest.mark.asyncio
async def test_validate_job_active_reads_from_cumulative_context(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def _fake_validate_job_active(**kwargs):
        captured.update(kwargs)
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "validate_job_active",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "validation_result": "active",
                "confidence": "medium",
                "indeed_found": True,
                "indeed_match_count": 1,
                "indeed_any_expired": False,
                "indeed_matched_by": "company_name",
                "linkedin_found": False,
                "linkedin_match_count": 0,
                "linkedin_matched_by": None,
            },
        }

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _fake_validate_job_active)

    result = await execute_job_validate_is_active(
        input_data={
            "cumulative_context": {
                "company_domain": "stripe.com",
                "job_title": "Data Engineer",
                "company_name": "Stripe",
            }
        }
    )

    assert result["status"] == "found"
    assert captured["company_domain"] == "stripe.com"
    assert captured["job_title"] == "Data Engineer"
    assert captured["company_name"] == "Stripe"


@pytest.mark.asyncio
async def test_validate_job_active_reads_from_company_object(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    async def _fake_validate_job_active(**kwargs):
        captured.update(kwargs)
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "validate_job_active",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "validation_result": "active",
                "confidence": "high",
                "indeed_found": True,
                "indeed_match_count": 1,
                "indeed_any_expired": False,
                "indeed_matched_by": "domain",
                "linkedin_found": True,
                "linkedin_match_count": 1,
                "linkedin_matched_by": "domain",
            },
        }

    monkeypatch.setattr(research_operations.revenueinfra, "validate_job_active", _fake_validate_job_active)

    result = await execute_job_validate_is_active(
        input_data={
            "job_title": "Staff Data Engineer",
            "cumulative_context": {
                "company_object": {
                    "domain": "stripe.com",
                    "name": "Stripe",
                }
            },
        }
    )

    assert result["status"] == "found"
    assert captured["company_domain"] == "stripe.com"
    assert captured["company_name"] == "Stripe"
