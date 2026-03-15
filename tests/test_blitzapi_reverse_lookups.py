from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.providers.blitzapi import email_to_person, phone_to_person

_MOCK_PERSON_RESPONSE = {
    "found": True,
    "person": {
        "person": {
            "first_name": "Antoine",
            "last_name": "Blitz",
            "full_name": "Antoine Blitz",
            "nickname": None,
            "civility_title": None,
            "headline": "Founder @BlitzAPI",
            "about_me": "Building BlitzAPI",
            "location": {
                "city": None,
                "state_code": "NY",
                "country_code": "US",
                "continent": "North America",
            },
            "linkedin_url": "https://www.linkedin.com/in/antoine-blitz-5581b7373",
            "connections_count": 500,
            "profile_picture_url": "https://media.licdn.com/dms/image/test",
            "experiences": [
                {
                    "job_title": "Founder Blitzapi",
                    "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
                    "company_linkedin_id": "be578414-239f-522e-b2e1-9246e22a52d1",
                    "job_description": "Building BlitzAPI",
                    "job_start_date": "2025-05-01",
                    "job_end_date": None,
                    "job_is_current": True,
                    "job_location": {"city": None, "state_code": None, "country_code": None},
                }
            ],
            "education": [],
            "skills": [],
            "certifications": [],
        }
    },
}

_MOCK_NOT_FOUND_RESPONSE = {"found": False}


def _mock_response(body: dict, status_code: int = 200):
    """Create a mock httpx.Response-like object."""
    import json

    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self.text = json.dumps(body)
            self.headers = {}

        def json(self):
            return body

    return _Resp()


# ---- Adapter tests ----


@pytest.mark.asyncio
async def test_phone_to_person_found():
    mock_resp = _mock_response(_MOCK_PERSON_RESPONSE)
    with patch("app.providers.blitzapi._blitzapi_request_with_retry", new_callable=AsyncMock, return_value=mock_resp):
        result = await phone_to_person(api_key="test-key", phone="+1234567890")

    assert result["attempt"]["status"] == "found"
    assert result["attempt"]["action"] == "phone_to_person"
    mapped = result["mapped"]
    assert mapped is not None
    assert mapped["full_name"] == "Antoine Blitz"
    assert mapped["linkedin_url"] == "https://www.linkedin.com/in/antoine-blitz-5581b7373"
    assert mapped["first_name"] == "Antoine"
    assert mapped["last_name"] == "Blitz"
    assert mapped["source_provider"] == "blitzapi"


@pytest.mark.asyncio
async def test_phone_to_person_not_found():
    mock_resp = _mock_response(_MOCK_NOT_FOUND_RESPONSE)
    with patch("app.providers.blitzapi._blitzapi_request_with_retry", new_callable=AsyncMock, return_value=mock_resp):
        result = await phone_to_person(api_key="test-key", phone="+1234567890")

    assert result["attempt"]["status"] == "not_found"
    assert result["mapped"] is None


@pytest.mark.asyncio
async def test_email_to_person_found():
    mock_resp = _mock_response(_MOCK_PERSON_RESPONSE)
    with patch("app.providers.blitzapi._blitzapi_request_with_retry", new_callable=AsyncMock, return_value=mock_resp):
        result = await email_to_person(api_key="test-key", email="antoine@blitz-agency.com")

    assert result["attempt"]["status"] == "found"
    assert result["attempt"]["action"] == "email_to_person"
    mapped = result["mapped"]
    assert mapped is not None
    assert mapped["full_name"] == "Antoine Blitz"
    assert mapped["linkedin_url"] == "https://www.linkedin.com/in/antoine-blitz-5581b7373"
    assert mapped["source_provider"] == "blitzapi"


@pytest.mark.asyncio
async def test_email_to_person_missing_input():
    result = await email_to_person(api_key="test-key", email=None)

    assert result["attempt"]["status"] == "skipped"
    assert result["attempt"]["skip_reason"] == "missing_required_inputs"
    assert result["mapped"] is None


# ---- Service tests ----


_MOCK_PROVIDER_FOUND_RESULT = {
    "attempt": {"provider": "blitzapi", "action": "phone_to_person", "status": "found", "duration_ms": 100},
    "mapped": {
        "full_name": "Antoine Blitz",
        "first_name": "Antoine",
        "last_name": "Blitz",
        "linkedin_url": "https://www.linkedin.com/in/antoine-blitz-5581b7373",
        "headline": "Founder @BlitzAPI",
        "current_title": "Founder Blitzapi",
        "current_company_name": None,
        "current_company_domain": None,
        "location_name": "US",
        "country_code": "US",
        "source_person_id": None,
        "source_provider": "blitzapi",
        "raw": _MOCK_PERSON_RESPONSE,
    },
}

_MOCK_EMAIL_PROVIDER_FOUND_RESULT = {
    "attempt": {"provider": "blitzapi", "action": "email_to_person", "status": "found", "duration_ms": 100},
    "mapped": {
        "full_name": "Antoine Blitz",
        "first_name": "Antoine",
        "last_name": "Blitz",
        "linkedin_url": "https://www.linkedin.com/in/antoine-blitz-5581b7373",
        "headline": "Founder @BlitzAPI",
        "current_title": "Founder Blitzapi",
        "current_company_name": None,
        "current_company_domain": None,
        "location_name": "US",
        "country_code": "US",
        "source_person_id": None,
        "source_provider": "blitzapi",
        "raw": _MOCK_PERSON_RESPONSE,
    },
}


@pytest.mark.asyncio
async def test_service_resolve_from_phone_success():
    with (
        patch("app.services.blitzapi_person_operations.blitzapi.phone_to_person", new_callable=AsyncMock, return_value=_MOCK_PROVIDER_FOUND_RESULT),
        patch("app.services.blitzapi_person_operations.get_settings") as mock_settings,
    ):
        mock_settings.return_value.blitzapi_api_key = "test-key"
        from app.services.blitzapi_person_operations import execute_person_resolve_from_phone

        result = await execute_person_resolve_from_phone(input_data={"phone": "+1234567890"})

    assert result["status"] == "found"
    assert result["operation_id"] == "person.resolve.from_phone"
    output = result["output"]
    assert output["full_name"] == "Antoine Blitz"
    assert output["linkedin_url"] == "https://www.linkedin.com/in/antoine-blitz-5581b7373"
    assert output["source_provider"] == "blitzapi"


@pytest.mark.asyncio
async def test_service_resolve_from_phone_missing_input():
    from app.services.blitzapi_person_operations import execute_person_resolve_from_phone

    result = await execute_person_resolve_from_phone(input_data={})

    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["phone"]


@pytest.mark.asyncio
async def test_service_resolve_from_email_success():
    with (
        patch("app.services.blitzapi_person_operations.blitzapi.email_to_person", new_callable=AsyncMock, return_value=_MOCK_EMAIL_PROVIDER_FOUND_RESULT),
        patch("app.services.blitzapi_person_operations.get_settings") as mock_settings,
    ):
        mock_settings.return_value.blitzapi_api_key = "test-key"
        from app.services.blitzapi_person_operations import execute_person_resolve_from_email

        result = await execute_person_resolve_from_email(input_data={"email": "antoine@blitz-agency.com"})

    assert result["status"] == "found"
    assert result["operation_id"] == "person.resolve.from_email"
    output = result["output"]
    assert output["full_name"] == "Antoine Blitz"
    assert output["linkedin_url"] == "https://www.linkedin.com/in/antoine-blitz-5581b7373"
    assert output["source_provider"] == "blitzapi"


@pytest.mark.asyncio
async def test_service_resolve_from_email_missing_input():
    from app.services.blitzapi_person_operations import execute_person_resolve_from_email

    result = await execute_person_resolve_from_email(input_data={})

    assert result["status"] == "failed"
    assert result["missing_inputs"] == ["email"]
