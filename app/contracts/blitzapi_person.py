from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WaterfallIcpSearchOutput(BaseModel):
    results: list[Any]
    results_count: int
    source_provider: str = "blitzapi"


class EmployeeFinderOutput(BaseModel):
    results: list[Any]
    results_count: int
    pagination: dict[str, Any] | None = None
    source_provider: str = "blitzapi"


class FindWorkEmailOutput(BaseModel):
    work_email: str | None = None
    all_emails: list[Any] | None = None
    source_provider: str = "blitzapi"


class ResolveMobilePhoneBlitzapiOutput(BaseModel):
    mobile_phone: str | None = None
    source_provider: str = "blitzapi"


class ValidateEmailBlitzapiOutput(BaseModel):
    email: str | None = None
    valid: bool | None = None
    deliverable: bool | None = None
    catch_all: bool | None = None
    disposable: bool | None = None
    source_provider: str = "blitzapi"


class ReversePersonLookupOutput(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    headline: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    current_company_domain: str | None = None
    location_name: str | None = None
    country_code: str | None = None
    source_person_id: str | None = None
    source_provider: str = "blitzapi"
