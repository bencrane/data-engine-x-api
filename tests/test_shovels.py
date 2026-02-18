from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.contracts.shovels import (
    ShovelsContractorOutput,
    ShovelsContractorSearchOutput,
    ShovelsEmployeesOutput,
    ShovelsPermitSearchOutput,
    ShovelsResidentsOutput,
)
from app.services import shovels_operations
from app.services.shovels_operations import (
    execute_address_residents,
    execute_contractor_employees,
    execute_contractor_enrich,
    execute_contractor_search,
    execute_permit_search,
)


def _set_shovels_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        shovels_operations,
        "get_settings",
        lambda: SimpleNamespace(shovels_api_key="test-shovels-key"),
    )


@pytest.mark.asyncio
async def test_execute_permit_search_missing_required_filters_failed():
    result = await execute_permit_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "permit_tags": ["solar"],
            },
            "noise": {"irrelevant": True},
        }
    )

    assert result["operation_id"] == "permit.search"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["permit_to", "geo_id"]


@pytest.mark.asyncio
async def test_execute_permit_search_success_validates_contract(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_search_permits(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["permit_from"] == "2026-01-01"
        assert filters["permit_to"] == "2026-01-31"
        assert filters["geo_id"] == "geo_123"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "permit_search_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "permit_id": "permit_1",
                        "number": "A-123",
                        "description": "Solar install",
                        "status": "active",
                        "file_date": "2026-01-02",
                        "issue_date": "2026-01-04",
                        "final_date": None,
                        "job_value": 120000,
                        "fees": 1300,
                        "contractor_id": "ctr_1",
                        "contractor_name": "Acme Electric",
                        "address": "100 Main St, Austin, TX, 78701",
                        "property_type": "residential",
                    }
                ],
                "result_count": 1,
                "next_cursor": "cursor_2",
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_permits", _fake_search_permits)

    result = await execute_permit_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "permit_to": "2026-01-31",
                "geo_id": "geo_123",
                "permit_tags": ["solar"],
                "size": 25,
            },
            "cumulative_context": {"noise": {"nested": [1, 2, 3]}},
        }
    )

    validated = ShovelsPermitSearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.results[0].permit_id == "permit_1"
    assert validated.next_cursor == "cursor_2"


@pytest.mark.asyncio
async def test_execute_contractor_enrich_missing_contractor_id_failed():
    result = await execute_contractor_enrich(
        input_data={
            "cumulative_context": {"company_profile": {"company_name": "Acme"}},
            "noise": [1, 2, 3],
        }
    )

    assert result["operation_id"] == "contractor.enrich"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["contractor_id"]


@pytest.mark.asyncio
async def test_execute_contractor_enrich_success_validates_full_profile(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_get_contractor(*, api_key: str | None, contractor_id: str | None):
        assert api_key == "test-shovels-key"
        assert contractor_id == "ctr_42"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "contractor_enrich_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "id": "ctr_42",
                "name": "Acme Electric LLC",
                "business_name": "Acme Electric LLC",
                "business_type": "Corporation",
                "classification": "C10",
                "classification_derived": "electrical",
                "primary_email": "ops@acme-electric.com",
                "primary_phone": "(512) 555-0199",
                "email": "ops@acme-electric.com,sales@acme-electric.com",
                "phone": "(512) 555-0199,(512) 555-0110",
                "website": "acme-electric.com",
                "linkedin_url": "https://www.linkedin.com/company/acme-electric",
                "city": "Austin",
                "state": "TX",
                "zipcode": "78701",
                "county": "Travis",
                "license": "TX-EL-1001",
                "employee_count": "10-49",
                "revenue": "$1M-$5M",
                "rating": 4.7,
                "review_count": 19,
                "permit_count": 144,
                "total_job_value": 55000000,
                "avg_job_value": 381944,
                "avg_inspection_pass_rate": 91,
                "primary_industry": "Electrical Contractor",
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "get_contractor", _fake_get_contractor)

    result = await execute_contractor_enrich(
        input_data={
            "cumulative_context": {
                "results": [{"contractor_id": "ctr_42"}],
                "noise": {"pipeline": "abc"},
            }
        }
    )

    validated = ShovelsContractorOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.id == "ctr_42"
    assert validated.classification_derived == "electrical"
    assert validated.permit_count == 144


@pytest.mark.asyncio
async def test_execute_contractor_search_missing_required_filters_failed():
    result = await execute_contractor_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "contractor_name": "Acme",
            }
        }
    )

    assert result["operation_id"] == "contractor.search"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["permit_to", "geo_id"]


@pytest.mark.asyncio
async def test_execute_contractor_search_success_validates_list(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_search_contractors(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["permit_from"] == "2026-01-01"
        assert filters["permit_to"] == "2026-01-31"
        assert filters["geo_id"] == "geo_123"
        return {
            "attempt": {
                "provider": "shovels",
                "action": "contractor_search_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "results": [
                    {
                        "id": "ctr_10",
                        "name": "Builder One",
                        "business_name": "Builder One Inc",
                        "classification_derived": "general_building_contractor",
                        "primary_email": "hello@builderone.com",
                        "city": "San Diego",
                        "state": "CA",
                        "zipcode": "92101",
                        "permit_count": 50,
                        "total_job_value": 10000000,
                        "avg_job_value": 200000,
                        "avg_inspection_pass_rate": 88,
                    }
                ],
                "result_count": 1,
                "next_cursor": "next_ctr_cursor",
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_contractors", _fake_search_contractors)

    result = await execute_contractor_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "permit_to": "2026-01-31",
                "geo_id": "geo_123",
                "contractor_classification_derived": ["general_building_contractor"],
            },
            "cumulative_context": {"noise": {"entity": "company"}},
        }
    )

    validated = ShovelsContractorSearchOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.result_count == 1
    assert validated.results[0].id == "ctr_10"
    assert validated.next_cursor == "next_ctr_cursor"


@pytest.mark.asyncio
async def test_execute_contractor_employees_missing_contractor_id_failed():
    result = await execute_contractor_employees(input_data={"step_config": {"size": 10}})

    assert result["operation_id"] == "contractor.search.employees"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["contractor_id"]


@pytest.mark.asyncio
async def test_execute_contractor_employees_success_validates_employee_list(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_get_contractor_employees(
        *,
        api_key: str | None,
        contractor_id: str | None,
        size: int | None = None,
        cursor: str | None = None,
    ):
        assert api_key == "test-shovels-key"
        assert contractor_id == "ctr_emp_1"
        assert size == 20
        assert cursor is None
        return {
            "attempt": {
                "provider": "shovels",
                "action": "contractor_search_employees_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "employees": [
                    {
                        "id": "emp_1",
                        "name": "Taylor Smith",
                        "email": "taylor@example.com",
                        "business_email": "taylor@acme.com",
                        "phone": "(415) 555-0111",
                        "linkedin_url": "https://www.linkedin.com/in/taylor-smith",
                        "city": "San Francisco",
                        "state": "CA",
                        "zip_code": "94105",
                    }
                ],
                "employee_count": 1,
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "get_contractor_employees", _fake_get_contractor_employees)

    result = await execute_contractor_employees(
        input_data={
            "step_config": {"size": 20},
            "cumulative_context": {"output": {"contractor_id": "ctr_emp_1"}, "noise": {"x": True}},
        }
    )

    validated = ShovelsEmployeesOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.employee_count == 1
    assert validated.employees[0].id == "emp_1"


@pytest.mark.asyncio
async def test_execute_address_residents_missing_geo_id_failed():
    result = await execute_address_residents(input_data={"step_config": {"size": 10}})

    assert result["operation_id"] == "address.search.residents"
    assert result["status"] == "failed"
    assert result["provider_attempts"] == []
    assert result["missing_inputs"] == ["geo_id"]


@pytest.mark.asyncio
async def test_execute_address_residents_success_validates_resident_list(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_get_address_residents(
        *,
        api_key: str | None,
        geo_id: str | None,
        size: int | None = None,
        cursor: str | None = None,
    ):
        assert api_key == "test-shovels-key"
        assert geo_id == "geo_addr_1"
        assert size == 50
        assert cursor is None
        return {
            "attempt": {
                "provider": "shovels",
                "action": "address_search_residents_shovels",
                "status": "found",
                "http_status": 200,
            },
            "mapped": {
                "residents": [
                    {
                        "name": "Jordan Lee",
                        "personal_emails": "jordan@example.com",
                        "phone": "(646) 555-0202",
                        "linkedin_url": "https://www.linkedin.com/in/jordan-lee",
                        "net_worth": "$500,000 to $749,999",
                        "income_range": "$150,000 to $299,999",
                        "is_homeowner": True,
                        "city": "New York",
                        "state": "NY",
                        "zip_code": "10001",
                    }
                ],
                "resident_count": 1,
            },
        }

    monkeypatch.setattr(shovels_operations.shovels, "get_address_residents", _fake_get_address_residents)

    result = await execute_address_residents(
        input_data={
            "cumulative_context": {
                "results": [{"geo_id": "geo_addr_1"}],
                "noise": {"upstream": "permit.search"},
            }
        }
    )

    validated = ShovelsResidentsOutput.model_validate(result["output"])
    assert result["status"] == "found"
    assert validated.resident_count == 1
    assert validated.residents[0].name == "Jordan Lee"


@pytest.mark.asyncio
async def test_shovels_operations_handle_noisy_input_across_all_operations(monkeypatch: pytest.MonkeyPatch):
    _set_shovels_key(monkeypatch)

    async def _fake_search_permits(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["permit_from"] == "2026-01-01"
        return {
            "attempt": {"provider": "shovels", "action": "permit_search_shovels", "status": "found"},
            "mapped": {
                "results": [{"permit_id": "permit_noise_1", "contractor_id": "ctr_noise_1", "geo_id": "geo_noise_1"}],
                "result_count": 1,
                "next_cursor": None,
            },
        }

    async def _fake_get_contractor(*, api_key: str | None, contractor_id: str | None):
        assert api_key == "test-shovels-key"
        assert contractor_id == "ctr_noise_1"
        return {
            "attempt": {"provider": "shovels", "action": "contractor_enrich_shovels", "status": "found"},
            "mapped": {"id": "ctr_noise_1", "name": "Noise Contractor"},
        }

    async def _fake_search_contractors(*, api_key: str | None, filters: dict):
        assert api_key == "test-shovels-key"
        assert filters["geo_id"] == "geo_noise_1"
        return {
            "attempt": {"provider": "shovels", "action": "contractor_search_shovels", "status": "found"},
            "mapped": {"results": [{"id": "ctr_noise_2", "name": "Noise Builder"}], "result_count": 1, "next_cursor": None},
        }

    async def _fake_get_contractor_employees(
        *,
        api_key: str | None,
        contractor_id: str | None,
        size: int | None = None,
        cursor: str | None = None,
    ):
        assert api_key == "test-shovels-key"
        assert contractor_id == "ctr_noise_1"
        assert size == 50
        assert cursor is None
        return {
            "attempt": {"provider": "shovels", "action": "contractor_search_employees_shovels", "status": "found"},
            "mapped": {"employees": [{"id": "emp_noise_1", "name": "Noise Person"}], "employee_count": 1},
        }

    async def _fake_get_address_residents(
        *,
        api_key: str | None,
        geo_id: str | None,
        size: int | None = None,
        cursor: str | None = None,
    ):
        assert api_key == "test-shovels-key"
        assert geo_id == "geo_noise_1"
        assert size == 50
        assert cursor is None
        return {
            "attempt": {"provider": "shovels", "action": "address_search_residents_shovels", "status": "found"},
            "mapped": {"residents": [{"name": "Noise Resident", "is_homeowner": True}], "resident_count": 1},
        }

    monkeypatch.setattr(shovels_operations.shovels, "search_permits", _fake_search_permits)
    monkeypatch.setattr(shovels_operations.shovels, "get_contractor", _fake_get_contractor)
    monkeypatch.setattr(shovels_operations.shovels, "search_contractors", _fake_search_contractors)
    monkeypatch.setattr(shovels_operations.shovels, "get_contractor_employees", _fake_get_contractor_employees)
    monkeypatch.setattr(shovels_operations.shovels, "get_address_residents", _fake_get_address_residents)

    noisy_context = {
        "history": [{"step": "x"}, {"step": "y"}],
        "output": {"results": [{"contractor_id": "ctr_noise_1"}], "geo_id": "geo_noise_1"},
        "results": [{"contractor_id": "ctr_noise_1"}, {"geo_id": "geo_noise_1"}],
        "noise_blob": {"a": [1, {"b": True}]},
    }

    permit_result = await execute_permit_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "permit_to": "2026-01-31",
                "geo_id": "geo_noise_1",
            },
            "cumulative_context": noisy_context,
        }
    )
    contractor_enrich_result = await execute_contractor_enrich(input_data={"cumulative_context": noisy_context})
    contractor_search_result = await execute_contractor_search(
        input_data={
            "step_config": {
                "permit_from": "2026-01-01",
                "permit_to": "2026-01-31",
                "geo_id": "geo_noise_1",
            },
            "cumulative_context": noisy_context,
        }
    )
    employee_result = await execute_contractor_employees(input_data={"cumulative_context": noisy_context})
    resident_result = await execute_address_residents(input_data={"cumulative_context": noisy_context})

    assert permit_result["status"] == "found"
    assert contractor_enrich_result["status"] == "found"
    assert contractor_search_result["status"] == "found"
    assert employee_result["status"] == "found"
    assert resident_result["status"] == "found"
