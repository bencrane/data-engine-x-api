from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ShovelsPermitItem(BaseModel):
    permit_id: str | None = None
    number: str | None = None
    description: str | None = None
    status: str | None = None
    file_date: str | None = None
    issue_date: str | None = None
    final_date: str | None = None
    job_value: int | None = None
    fees: int | None = None
    contractor_id: str | None = None
    contractor_name: str | None = None
    address: str | None = None
    property_type: str | None = None
    source_provider: str = "shovels"


class ShovelsPermitSearchOutput(BaseModel):
    results: list[ShovelsPermitItem]
    result_count: int
    next_cursor: str | None = None
    source_provider: str = "shovels"


class ShovelsContractorOutput(BaseModel):
    id: str | None = None
    name: str | None = None
    business_name: str | None = None
    business_type: str | None = None
    classification: str | None = None
    classification_derived: str | None = None
    primary_email: str | None = None
    primary_phone: str | None = None
    email: str | None = None
    phone: str | None = None
    website: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    state: str | None = None
    zipcode: str | None = None
    county: str | None = None
    license: str | None = None
    employee_count: str | None = None
    revenue: str | None = None
    rating: float | None = None
    review_count: int | None = None
    permit_count: int | None = None
    total_job_value: int | None = None
    avg_job_value: int | None = None
    avg_inspection_pass_rate: int | None = None
    primary_industry: str | None = None
    source_provider: str = "shovels"


class ShovelsContractorSearchOutput(BaseModel):
    results: list[ShovelsContractorOutput]
    result_count: int
    next_cursor: str | None = None
    source_provider: str = "shovels"


class ShovelsEmployeeItem(BaseModel):
    id: str | None = None
    name: str | None = None
    email: str | None = None
    business_email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    source_provider: str = "shovels"


class ShovelsEmployeesOutput(BaseModel):
    employees: list[ShovelsEmployeeItem]
    employee_count: int
    source_provider: str = "shovels"


class ShovelsResidentItem(BaseModel):
    name: str | None = None
    personal_emails: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    net_worth: str | None = None
    income_range: str | None = None
    is_homeowner: bool | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    source_provider: str = "shovels"


class ShovelsResidentsOutput(BaseModel):
    residents: list[ShovelsResidentItem]
    resident_count: int
    source_provider: str = "shovels"


class ShovelsGeoSearchItem(BaseModel):
    geo_id: str
    name: str | None = None
    state: str | None = None
    source_provider: str = "shovels"


class ShovelsGeoSearchOutput(BaseModel):
    results: list[ShovelsGeoSearchItem]
    result_count: int
    source_provider: str = "shovels"


class ShovelsMetricsMonthlyPoint(BaseModel):
    month: str | None = None
    value: float | int | None = None


class ShovelsMetricsMonthlyOutput(BaseModel):
    geo_id: str
    metric: str | None = None
    data_points: list[ShovelsMetricsMonthlyPoint]
    source_provider: str = "shovels"


class ShovelsMetricsCurrentOutput(BaseModel):
    geo_id: str
    metrics: dict[str, Any]
    source_provider: str = "shovels"


class ShovelsGeoDetailOutput(BaseModel):
    geo_id: str
    name: str | None = None
    state: str | None = None
    details: dict[str, Any]
    source_provider: str = "shovels"


class ShovelsAddressSearchItem(BaseModel):
    geo_id: str | None = None
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    property_type: str | None = None
    source_provider: str = "shovels"


class ShovelsAddressSearchOutput(BaseModel):
    results: list[ShovelsAddressSearchItem]
    result_count: int
    source_provider: str = "shovels"
