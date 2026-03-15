from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.services.company_operations import execute_company_enrich_bulk_profile


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prospeo_bulk_result(matched_indices: dict[str, dict], not_matched: list[str] | None = None):
    """Build a mock bulk_enrich_companies() return value."""
    matched = [
        {"identifier": idx, "company": company}
        for idx, company in matched_indices.items()
    ]
    return {
        "attempt": {
            "provider": "prospeo",
            "action": "bulk_company_enrich",
            "status": "found" if matched else "not_found",
            "duration_ms": 500,
            "raw_response": {},
        },
        "mapped": {
            "matched": matched,
            "not_matched": not_matched or [],
            "invalid_datapoints": [],
            "total_cost": len(matched),
        },
    }


RAW_PROSPEO_INTERCOM = {
    "name": "Intercom",
    "domain": "intercom.com",
    "website": "https://intercom.com",
    "linkedin_url": "https://www.linkedin.com/company/intercom",
    "type": "Privately Held",
    "industry": "Software",
    "employee_count": 1200,
    "employee_range": "1001-5000",
    "founded": 2011,
    "location": {"city": "San Francisco", "country_code": "US"},
    "description": "Customer messaging platform",
    "keywords": ["SaaS"],
    "revenue_range_printed": "$100M-$500M",
    "logo_url": None,
    "company_id": 12345,
}

RAW_PROSPEO_INTERCOM_NO_LINKEDIN = {
    **RAW_PROSPEO_INTERCOM,
    "linkedin_url": None,
}


def _blitzapi_result(raw_company: dict | None):
    """Simulate _blitzapi_company_enrich side effect."""
    async def _side_effect(*, input_data, attempts):
        attempts.append({
            "provider": "blitzapi",
            "action": "company_enrich",
            "status": "found" if raw_company else "not_found",
        })
        return raw_company
    return _side_effect


def _companyenrich_result(raw_company: dict | None):
    async def _side_effect(*, input_data, attempts):
        attempts.append({
            "provider": "companyenrich",
            "action": "company_enrich",
            "status": "found" if raw_company else "not_found",
        })
        return raw_company
    return _side_effect


def _leadmagic_result(raw_company: dict | None):
    async def _side_effect(*, input_data, attempts):
        attempts.append({
            "provider": "leadmagic",
            "action": "company_enrich",
            "status": "found" if raw_company else "not_found",
        })
        return raw_company
    return _side_effect


def _no_result():
    """Provider returns nothing."""
    async def _side_effect(*, input_data, attempts):
        attempts.append({"provider": "noop", "status": "not_found"})
        return None
    return _side_effect


def _patch_providers(prospeo_bulk, blitzapi_fn=None, companyenrich_fn=None, leadmagic_fn=None):
    """Context manager stack for patching all provider dependencies."""
    import contextlib
    return contextlib.ExitStack().__enter__() or None  # placeholder; we use individual patches


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_waterfall_prospeo_matched_blitzapi_fills_gaps():
    """Prospeo returns domain but no LinkedIn URL; blitzapi fills the LinkedIn URL."""
    prospeo_bulk = _prospeo_bulk_result(
        matched_indices={"0": RAW_PROSPEO_INTERCOM_NO_LINKEDIN},
    )

    blitz_raw = {
        "name": "Intercom",
        "domain": "intercom.com",
        "website": "https://intercom.com",
        "linkedin_url": "https://www.linkedin.com/company/intercom",
        "linkedin_id": "1234",
        "type": "Privately Held",
        "industry": "Software",
        "employees_on_linkedin": 1200,
        "size": "1001-5000",
        "founded_year": 2011,
        "hq": {"city": "San Francisco", "country_code": "US"},
        "about": "Customer messaging platform",
        "specialties": ["SaaS"],
        "followers": 50000,
    }

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=prospeo_bulk), \
         patch("app.services.company_operations.get_settings") as mock_settings, \
         patch("app.services.company_operations._blitzapi_company_enrich", side_effect=_blitzapi_result(blitz_raw)), \
         patch("app.services.company_operations._companyenrich_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._leadmagic_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._provider_order", return_value=["prospeo", "blitzapi", "companyenrich", "leadmagic"]):
        mock_settings.return_value.prospeo_api_key = "test-key"

        result = await execute_company_enrich_bulk_profile(input_data={
            "companies": [{"company_domain": "intercom.com"}]
        })

    assert result["status"] == "found"
    items = result["output"]["results"]
    assert len(items) == 1
    assert items[0]["status"] == "found"
    assert items[0]["source_providers"] == ["prospeo", "blitzapi"]
    assert items[0]["company_profile"]["company_linkedin_url"] == "https://www.linkedin.com/company/intercom"
    assert items[0]["company_profile"]["company_domain"] == "intercom.com"


@pytest.mark.asyncio
async def test_prospeo_unmatched_fallback_companyenrich():
    """Prospeo doesn't match; companyenrich finds the company."""
    prospeo_bulk = _prospeo_bulk_result(matched_indices={}, not_matched=["0"])

    ce_raw = {
        "name": "Acme Corp",
        "domain": "acme.com",
        "website": "https://acme.com",
        "socials": {"linkedin_url": "https://www.linkedin.com/company/acme"},
        "type": "Private",
        "industry": "Manufacturing",
        "industries": ["Manufacturing", "Industrial"],
        "employees": "501-1000",
        "founded_year": 1990,
        "location": {"city": {"name": "Chicago"}, "state": {"name": "IL"}, "country": {"code": "US"}},
        "description": "Industrial widgets",
        "categories": ["Widgets"],
        "revenue": "$50M-$100M",
        "logo_url": "https://example.com/logo.png",
        "id": "ce-123",
    }

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=prospeo_bulk), \
         patch("app.services.company_operations.get_settings") as mock_settings, \
         patch("app.services.company_operations._blitzapi_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._companyenrich_company_enrich", side_effect=_companyenrich_result(ce_raw)), \
         patch("app.services.company_operations._leadmagic_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._provider_order", return_value=["prospeo", "blitzapi", "companyenrich", "leadmagic"]):
        mock_settings.return_value.prospeo_api_key = "test-key"

        result = await execute_company_enrich_bulk_profile(input_data={
            "companies": [{"company_domain": "acme.com"}]
        })

    assert result["status"] == "found"
    items = result["output"]["results"]
    assert items[0]["source_providers"] == ["companyenrich"]
    assert items[0]["company_profile"]["company_name"] == "Acme Corp"


@pytest.mark.asyncio
async def test_all_providers_miss():
    """No provider returns data."""
    prospeo_bulk = _prospeo_bulk_result(matched_indices={}, not_matched=["0"])

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=prospeo_bulk), \
         patch("app.services.company_operations.get_settings") as mock_settings, \
         patch("app.services.company_operations._blitzapi_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._companyenrich_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._leadmagic_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._provider_order", return_value=["prospeo", "blitzapi", "companyenrich", "leadmagic"]):
        mock_settings.return_value.prospeo_api_key = "test-key"

        result = await execute_company_enrich_bulk_profile(input_data={
            "companies": [{"company_domain": "unknown.xyz"}]
        })

    assert result["status"] == "not_found"
    items = result["output"]["results"]
    assert items[0]["status"] == "not_found"
    assert items[0]["company_profile"] is None
    assert items[0]["source_providers"] == []


@pytest.mark.asyncio
async def test_mixed_batch():
    """3 companies: one Prospeo+blitzapi, one companyenrich only, one not found."""
    prospeo_bulk = _prospeo_bulk_result(
        matched_indices={"0": RAW_PROSPEO_INTERCOM},
        not_matched=["1", "2"],
    )

    blitz_raw = {
        "name": "Intercom",
        "domain": "intercom.com",
        "linkedin_url": "https://www.linkedin.com/company/intercom",
        "linkedin_id": "1234",
        "type": "Privately Held",
        "industry": "Software",
        "employees_on_linkedin": 1200,
        "size": "1001-5000",
        "founded_year": 2011,
        "hq": {"city": "San Francisco", "country_code": "US"},
        "about": "Messaging",
    }
    ce_raw = {
        "name": "Acme Corp",
        "domain": "acme.com",
        "website": "https://acme.com",
        "socials": {},
        "type": "Private",
        "industry": "Manufacturing",
        "location": {"country": {"code": "US"}},
    }

    call_count = {"blitz": 0, "ce": 0}

    async def blitz_side_effect(*, input_data, attempts):
        call_count["blitz"] += 1
        idx = call_count["blitz"]
        if idx == 1:  # company 0
            attempts.append({"provider": "blitzapi", "status": "found"})
            return blitz_raw
        attempts.append({"provider": "blitzapi", "status": "not_found"})
        return None

    async def ce_side_effect(*, input_data, attempts):
        call_count["ce"] += 1
        idx = call_count["ce"]
        if idx == 2:  # company 1 (second call)
            attempts.append({"provider": "companyenrich", "status": "found"})
            return ce_raw
        attempts.append({"provider": "companyenrich", "status": "not_found"})
        return None

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=prospeo_bulk), \
         patch("app.services.company_operations.get_settings") as mock_settings, \
         patch("app.services.company_operations._blitzapi_company_enrich", side_effect=blitz_side_effect), \
         patch("app.services.company_operations._companyenrich_company_enrich", side_effect=ce_side_effect), \
         patch("app.services.company_operations._leadmagic_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._provider_order", return_value=["prospeo", "blitzapi", "companyenrich", "leadmagic"]):
        mock_settings.return_value.prospeo_api_key = "test-key"

        result = await execute_company_enrich_bulk_profile(input_data={
            "companies": [
                {"company_domain": "intercom.com"},
                {"company_domain": "acme.com"},
                {"company_domain": "unknown.xyz"},
            ]
        })

    assert result["status"] == "found"
    output = result["output"]
    assert output["total_submitted"] == 3
    assert output["total_found"] == 2
    assert output["total_not_found"] == 1
    assert output["total_failed"] == 0
    assert output["results"][0]["source_providers"] == ["prospeo", "blitzapi"]
    assert output["results"][1]["source_providers"] == ["companyenrich"]
    assert output["results"][2]["status"] == "not_found"


@pytest.mark.asyncio
async def test_identifier_chaining_prospeo_linkedin_to_blitzapi():
    """Prospeo returns a LinkedIn URL not in the original input; blitzapi receives it."""
    prospeo_company = {
        **RAW_PROSPEO_INTERCOM,
        "linkedin_url": "https://www.linkedin.com/company/intercom",
    }
    prospeo_bulk = _prospeo_bulk_result(matched_indices={"0": prospeo_company})

    received_inputs = []

    async def blitz_capture(*, input_data, attempts):
        received_inputs.append(dict(input_data))
        attempts.append({"provider": "blitzapi", "status": "not_found"})
        return None

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=prospeo_bulk), \
         patch("app.services.company_operations.get_settings") as mock_settings, \
         patch("app.services.company_operations._blitzapi_company_enrich", side_effect=blitz_capture), \
         patch("app.services.company_operations._companyenrich_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._leadmagic_company_enrich", side_effect=_no_result()), \
         patch("app.services.company_operations._provider_order", return_value=["prospeo", "blitzapi", "companyenrich", "leadmagic"]):
        mock_settings.return_value.prospeo_api_key = "test-key"

        await execute_company_enrich_bulk_profile(input_data={
            "companies": [{"company_domain": "intercom.com"}]  # no linkedin_url in input
        })

    assert len(received_inputs) == 1
    assert received_inputs[0]["company_linkedin_url"] == "https://www.linkedin.com/company/intercom"


@pytest.mark.asyncio
async def test_missing_input():
    result = await execute_company_enrich_bulk_profile(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["companies"]


@pytest.mark.asyncio
async def test_over_50_companies():
    companies = [{"company_domain": f"company{i}.com"} for i in range(51)]
    result = await execute_company_enrich_bulk_profile(input_data={"companies": companies})
    assert result["status"] == "failed"
    assert result["error"]["code"] == "max_50_companies_exceeded"
    assert result["error"]["submitted_count"] == 51


@pytest.mark.asyncio
async def test_empty_companies_list():
    result = await execute_company_enrich_bulk_profile(input_data={"companies": []})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["companies"]
