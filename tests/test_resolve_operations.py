from __future__ import annotations

import pytest

from app.services import resolve_operations


class _SettingsStub:
    revenueinfra_api_url = "https://api.revenueinfra.com"
    revenueinfra_ingest_api_key = "test-key"


@pytest.fixture(autouse=True)
def _stub_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(resolve_operations, "get_settings", lambda: _SettingsStub())


@pytest.mark.asyncio
async def test_resolve_domain_from_email_missing_input():
    result = await resolve_operations.execute_company_resolve_domain_from_email(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["work_email"]


@pytest.mark.asyncio
async def test_resolve_domain_from_email_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["work_email"] == "jane@stripe.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_email", "status": "found"},
            "mapped": {"domain": "stripe.com", "resolve_source": "email_extract"},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_email", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_email(
        input_data={"work_email": "jane@stripe.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["domain"] == "stripe.com"
    assert result["output"]["resolve_source"] == "email_extract"


@pytest.mark.asyncio
async def test_resolve_domain_from_email_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_email", "status": "not_found"},
            "mapped": {"domain": None, "resolve_source": None},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_email", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_email(
        input_data={"work_email": "jane@stripe.com"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_domain_from_linkedin_missing_input():
    result = await resolve_operations.execute_company_resolve_domain_from_linkedin(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_linkedin_url"]


@pytest.mark.asyncio
async def test_resolve_domain_from_linkedin_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["company_linkedin_url"] == "linkedin.com/company/stripe"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_linkedin", "status": "found"},
            "mapped": {"domain": "stripe.com", "resolve_source": "core.companies"},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_linkedin", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_linkedin(
        input_data={"company_linkedin_url": "linkedin.com/company/stripe"}
    )
    assert result["status"] == "found"
    assert result["output"]["domain"] == "stripe.com"
    assert result["output"]["resolve_source"] == "core.companies"


@pytest.mark.asyncio
async def test_resolve_domain_from_linkedin_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_linkedin", "status": "not_found"},
            "mapped": {"domain": None, "resolve_source": None},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_linkedin", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_linkedin(
        input_data={"linkedin_url": "linkedin.com/company/stripe"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_domain_from_name_missing_input():
    result = await resolve_operations.execute_company_resolve_domain_from_name(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["company_name"]


@pytest.mark.asyncio
async def test_resolve_domain_from_name_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["company_name"] == "Stripe Inc"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_company_name", "status": "found"},
            "mapped": {
                "domain": "stripe.com",
                "cleaned_company_name": "Stripe",
                "resolve_source": "extracted.cleaned_company_names",
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_company_name", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_name(
        input_data={"company_name": "Stripe Inc"}
    )
    assert result["status"] == "found"
    assert result["output"]["domain"] == "stripe.com"
    assert result["output"]["cleaned_company_name"] == "Stripe"


@pytest.mark.asyncio
async def test_resolve_domain_from_name_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "resolve_domain_from_company_name",
                "status": "not_found",
            },
            "mapped": {"domain": None, "cleaned_company_name": None, "resolve_source": None},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_company_name", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_name(
        input_data={"company_name": "Unknown Co"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_linkedin_from_domain_missing_input():
    result = await resolve_operations.execute_company_resolve_linkedin_from_domain(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["domain"]


@pytest.mark.asyncio
async def test_resolve_linkedin_from_domain_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["domain"] == "stripe.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_linkedin_from_domain", "status": "found"},
            "mapped": {
                "company_linkedin_url": "https://linkedin.com/company/stripe",
                "resolve_source": "core.companies",
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_linkedin_from_domain", _stub)
    result = await resolve_operations.execute_company_resolve_linkedin_from_domain(
        input_data={"domain": "stripe.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://linkedin.com/company/stripe"


@pytest.mark.asyncio
async def test_resolve_linkedin_from_domain_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_linkedin_from_domain", "status": "not_found"},
            "mapped": {"company_linkedin_url": None, "resolve_source": None},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_linkedin_from_domain", _stub)
    result = await resolve_operations.execute_company_resolve_linkedin_from_domain(
        input_data={"company_domain": "unknown.example"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_person_linkedin_from_email_missing_input():
    result = await resolve_operations.execute_person_resolve_linkedin_from_email(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["work_email"]


@pytest.mark.asyncio
async def test_resolve_person_linkedin_from_email_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["work_email"] == "jane@stripe.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "resolve_person_linkedin_from_email",
                "status": "found",
            },
            "mapped": {
                "person_linkedin_url": "https://linkedin.com/in/jane-doe",
                "resolve_source": "reference.email_to_person",
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_person_linkedin_from_email", _stub)
    result = await resolve_operations.execute_person_resolve_linkedin_from_email(
        input_data={"work_email": "jane@stripe.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["person_linkedin_url"] == "https://linkedin.com/in/jane-doe"


@pytest.mark.asyncio
async def test_resolve_person_linkedin_from_email_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "resolve_person_linkedin_from_email",
                "status": "not_found",
            },
            "mapped": {"person_linkedin_url": None, "resolve_source": None},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_person_linkedin_from_email", _stub)
    result = await resolve_operations.execute_person_resolve_linkedin_from_email(
        input_data={"email": "jane@stripe.com"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_location_from_domain_missing_input():
    result = await resolve_operations.execute_company_resolve_location_from_domain(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["domain"]


@pytest.mark.asyncio
async def test_resolve_location_from_domain_success(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["domain"] == "stripe.com"
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "resolve_company_location_from_domain",
                "status": "found",
            },
            "mapped": {
                "company_city": "South San Francisco",
                "company_state": "CA",
                "company_country": "US",
                "resolve_source": "core.company_locations",
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_company_location_from_domain", _stub)
    result = await resolve_operations.execute_company_resolve_location_from_domain(
        input_data={"domain": "stripe.com"}
    )
    assert result["status"] == "found"
    assert result["output"]["company_city"] == "South San Francisco"
    assert result["output"]["company_state"] == "CA"
    assert result["output"]["company_country"] == "US"


@pytest.mark.asyncio
async def test_resolve_location_from_domain_not_found(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        return {
            "attempt": {
                "provider": "revenueinfra",
                "action": "resolve_company_location_from_domain",
                "status": "not_found",
            },
            "mapped": {
                "company_city": None,
                "company_state": None,
                "company_country": None,
                "resolve_source": None,
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_company_location_from_domain", _stub)
    result = await resolve_operations.execute_company_resolve_location_from_domain(
        input_data={"canonical_domain": "unknown.example"}
    )
    assert result["status"] == "not_found"


@pytest.mark.asyncio
async def test_resolve_domain_from_email_reads_cumulative_context(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["work_email"] == "jane@stripe.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_domain_from_email", "status": "found"},
            "mapped": {"domain": "stripe.com", "resolve_source": "email_extract"},
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_domain_from_email", _stub)
    result = await resolve_operations.execute_company_resolve_domain_from_email(
        input_data={"cumulative_context": {"work_email": "jane@stripe.com"}}
    )
    assert result["status"] == "found"
    assert result["output"]["domain"] == "stripe.com"


@pytest.mark.asyncio
async def test_resolve_linkedin_from_domain_reads_cumulative_context(monkeypatch: pytest.MonkeyPatch):
    async def _stub(**kwargs):
        assert kwargs["domain"] == "stripe.com"
        return {
            "attempt": {"provider": "revenueinfra", "action": "resolve_linkedin_from_domain", "status": "found"},
            "mapped": {
                "company_linkedin_url": "https://linkedin.com/company/stripe",
                "resolve_source": "core.companies",
            },
        }

    monkeypatch.setattr(resolve_operations.revenueinfra, "resolve_linkedin_from_domain", _stub)
    result = await resolve_operations.execute_company_resolve_linkedin_from_domain(
        input_data={"cumulative_context": {"company_domain": "stripe.com"}}
    )
    assert result["status"] == "found"
    assert result["output"]["company_linkedin_url"] == "https://linkedin.com/company/stripe"
