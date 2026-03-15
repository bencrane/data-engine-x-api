from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.prospeo import bulk_enrich_companies
from app.services.company_operations import execute_company_enrich_bulk_prospeo


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PROSPEO_MATCHED_RESPONSE = {
    "error": False,
    "total_cost": 2,
    "matched": [
        {
            "identifier": "0",
            "company": {
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
                "keywords": ["SaaS", "Messaging"],
                "revenue_range_printed": "$100M-$500M",
                "logo_url": "https://example.com/logo.png",
                "company_id": 12345,
            },
        },
        {
            "identifier": "1",
            "company": {
                "name": "Deloitte",
                "domain": "deloitte.com",
                "website": "https://deloitte.com",
                "linkedin_url": "https://www.linkedin.com/company/deloitte",
                "type": "Public Company",
                "industry": "Consulting",
                "employee_count": 300000,
                "employee_range": "10001+",
                "founded": 1845,
                "location": {"city": "London", "country_code": "GB"},
                "description": "Professional services",
                "keywords": ["Consulting"],
                "revenue_range_printed": "$50B+",
                "logo_url": None,
                "company_id": 67890,
            },
        },
    ],
    "not_matched": ["2"],
    "invalid_datapoints": [],
}


def _mock_response(status_code: int, body: dict):
    """Create a mock httpx response."""

    class FakeResponse:
        def __init__(self):
            self.status_code = status_code
            self.text = str(body)

        def json(self):
            return body

    return FakeResponse()


# ---------------------------------------------------------------------------
# Adapter Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_adapter_success():
    records = [
        {"identifier": "0", "company_website": "intercom.com"},
        {"identifier": "1", "company_linkedin_url": "https://www.linkedin.com/company/deloitte"},
        {"identifier": "2", "company_name": "Milka"},
    ]
    mock_resp = _mock_response(200, PROSPEO_MATCHED_RESPONSE)

    with patch("app.providers.prospeo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await bulk_enrich_companies(api_key="test-key", records=records)

    assert result["attempt"]["status"] == "found"
    assert result["attempt"]["provider"] == "prospeo"
    assert len(result["mapped"]["matched"]) == 2
    assert result["mapped"]["not_matched"] == ["2"]
    assert result["mapped"]["total_cost"] == 2
    assert result["mapped"]["matched"][0]["identifier"] == "0"
    assert result["mapped"]["matched"][1]["identifier"] == "1"


@pytest.mark.asyncio
async def test_adapter_missing_api_key():
    result = await bulk_enrich_companies(api_key=None, records=[{"identifier": "0", "company_name": "Test"}])
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_provider_api_key"


@pytest.mark.asyncio
async def test_adapter_empty_records():
    result = await bulk_enrich_companies(api_key="test-key", records=[])
    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"


@pytest.mark.asyncio
async def test_adapter_over_50_records():
    records = [{"identifier": str(i), "company_name": f"Company {i}"} for i in range(51)]
    result = await bulk_enrich_companies(api_key="test-key", records=records)
    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["error"] == "max_50_records_exceeded"
    assert result["attempt"]["submitted_count"] == 51


@pytest.mark.asyncio
async def test_adapter_upstream_error():
    error_body = {"error": True, "error_code": "INVALID_API_KEY"}
    mock_resp = _mock_response(401, error_body)

    with patch("app.providers.prospeo.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        result = await bulk_enrich_companies(api_key="bad-key", records=[{"identifier": "0", "company_name": "Test"}])

    assert result["attempt"]["status"] == "failed"
    assert result["attempt"]["http_status"] == 401
    assert result["attempt"]["provider_status"] == "INVALID_API_KEY"


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_service_end_to_end():
    adapter_result = {
        "attempt": {"provider": "prospeo", "action": "bulk_company_enrich", "status": "found", "duration_ms": 500, "raw_response": PROSPEO_MATCHED_RESPONSE},
        "mapped": {
            "matched": PROSPEO_MATCHED_RESPONSE["matched"],
            "not_matched": PROSPEO_MATCHED_RESPONSE["not_matched"],
            "invalid_datapoints": [],
            "total_cost": 2,
        },
    }

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=adapter_result), \
         patch("app.services.company_operations.get_settings") as mock_settings:
        mock_settings.return_value.prospeo_api_key = "test-key"

        result = await execute_company_enrich_bulk_prospeo(input_data={
            "companies": [
                {"company_website": "intercom.com"},
                {"company_linkedin_url": "https://www.linkedin.com/company/deloitte"},
                {"company_name": "Milka"},
            ]
        })

    assert result["status"] == "found"
    assert result["operation_id"] == "company.enrich.bulk_prospeo"
    output = result["output"]
    assert output["total_submitted"] == 3
    assert output["total_matched"] == 2
    assert output["total_cost"] == 2
    assert output["source_provider"] == "prospeo"
    assert len(output["matched"]) == 2
    assert output["matched"][0]["identifier"] == "0"
    assert output["matched"][0]["company_profile"]["company_name"] == "Intercom"
    assert output["matched"][0]["company_profile"]["company_domain"] == "intercom.com"
    assert output["matched"][1]["company_profile"]["company_name"] == "Deloitte"
    assert output["not_matched"] == ["2"]


@pytest.mark.asyncio
async def test_service_missing_input():
    result = await execute_company_enrich_bulk_prospeo(input_data={})
    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["companies"]

    result2 = await execute_company_enrich_bulk_prospeo(input_data={"companies": []})
    assert result2["status"] == "failed"
    assert result2["missing_inputs"] == ["companies"]


@pytest.mark.asyncio
async def test_service_domain_to_website_mapping():
    adapter_result = {
        "attempt": {"provider": "prospeo", "action": "bulk_company_enrich", "status": "not_found", "duration_ms": 100, "raw_response": {}},
        "mapped": {"matched": [], "not_matched": ["0"], "invalid_datapoints": [], "total_cost": 0},
    }

    with patch("app.services.company_operations.prospeo.bulk_enrich_companies", new_callable=AsyncMock, return_value=adapter_result) as mock_adapter, \
         patch("app.services.company_operations.get_settings") as mock_settings:
        mock_settings.return_value.prospeo_api_key = "test-key"

        await execute_company_enrich_bulk_prospeo(input_data={
            "companies": [{"company_domain": "example.com"}]
        })

    call_kwargs = mock_adapter.call_args.kwargs
    assert call_kwargs["records"][0]["company_website"] == "example.com"
    assert "company_domain" not in call_kwargs["records"][0]
