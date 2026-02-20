from __future__ import annotations

import re
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from app.services import entity_state


def test_resolve_job_posting_entity_id_by_theirstack_id():
    org_id = "11111111-1111-1111-1111-111111111111"
    payload = {"theirstack_job_id": 987654321, "job_url": "https://jobs.example.com/123"}
    resolved = entity_state.resolve_job_posting_entity_id(org_id=org_id, canonical_fields=payload)
    expected = str(uuid5(NAMESPACE_URL, f"job:{org_id}:theirstack:987654321"))
    assert resolved == expected


def test_resolve_job_posting_entity_id_by_url():
    org_id = "11111111-1111-1111-1111-111111111111"
    payload = {"job_url": "https://jobs.example.com/role/abc"}
    resolved = entity_state.resolve_job_posting_entity_id(org_id=org_id, canonical_fields=payload)
    expected = str(uuid5(NAMESPACE_URL, f"job:{org_id}:url:https://jobs.example.com/role/abc"))
    assert resolved == expected


def test_resolve_job_posting_entity_id_by_title_domain():
    org_id = "11111111-1111-1111-1111-111111111111"
    payload = {"job_title": "Senior Data Engineer", "company_domain": "example.com"}
    resolved = entity_state.resolve_job_posting_entity_id(org_id=org_id, canonical_fields=payload)
    expected = str(
        uuid5(
            NAMESPACE_URL,
            f"job:{org_id}:title_domain:senior data engineer:example.com",
        )
    )
    assert resolved == expected


def test_resolve_job_posting_entity_id_deterministic():
    org_id = "11111111-1111-1111-1111-111111111111"
    payload = {
        "job_title": "Platform Engineer",
        "company_domain": "acme.com",
        "country_code": "US",
    }
    first = entity_state.resolve_job_posting_entity_id(org_id=org_id, canonical_fields=payload)
    second = entity_state.resolve_job_posting_entity_id(org_id=org_id, canonical_fields=payload)
    assert first == second


def test_job_posting_fields_from_context_full():
    fields = entity_state._job_posting_fields_from_context(
        {
            "job_id": "123456",
            "url": "https://jobs.example.com/roles/data-engineer",
            "job_title": "Data Engineer",
            "normalized_title": "data engineer",
            "company_name": "Example Corp",
            "domain": "www.example.com",
            "location": "San Francisco, CA",
            "short_location": "SF Bay Area",
            "state_code": "CA",
            "country_code": "US",
            "remote": True,
            "hybrid": False,
            "seniority": "mid",
            "employment_statuses": ["full-time", "permanent"],
            "date_posted": "2026-02-18",
            "discovered_at": "2026-02-19T10:00:00Z",
            "salary_string": "$140k-$180k",
            "min_annual_salary_usd": "140000",
            "max_annual_salary_usd": 180000,
            "description": "Build data systems",
            "technology_slugs": ["python", "postgres"],
            "source_providers": ["theirstack"],
            "confidence": "0.87",
        }
    )

    assert fields["theirstack_job_id"] == 123456
    assert fields["job_url"] == "https://jobs.example.com/roles/data-engineer"
    assert fields["job_title"] == "Data Engineer"
    assert fields["normalized_title"] == "data engineer"
    assert fields["company_name"] == "Example Corp"
    assert fields["company_domain"] == "example.com"
    assert fields["location"] == "San Francisco, CA"
    assert fields["short_location"] == "SF Bay Area"
    assert fields["state_code"] == "CA"
    assert fields["country_code"] == "US"
    assert fields["remote"] is True
    assert fields["hybrid"] is False
    assert fields["seniority"] == "mid"
    assert fields["employment_statuses"] == ["full-time", "permanent"]
    assert fields["date_posted"] == "2026-02-18"
    assert fields["discovered_at"] == "2026-02-19T10:00:00Z"
    assert fields["salary_string"] == "$140k-$180k"
    assert fields["min_annual_salary_usd"] == 140000.0
    assert fields["max_annual_salary_usd"] == 180000.0
    assert fields["description"] == "Build data systems"
    assert fields["technology_slugs"] == ["python", "postgres"]
    assert fields["source_providers"] == ["theirstack"]
    assert fields["enrichment_confidence"] == 0.87


def test_job_posting_fields_from_context_minimal():
    fields = entity_state._job_posting_fields_from_context({})
    assert all(value is None for value in fields.values())


def test_job_posting_fields_boolean_handling():
    truthy_string = entity_state._job_posting_fields_from_context({"remote": "true", "hybrid": "false"})
    proper_bools = entity_state._job_posting_fields_from_context({"remote": True, "hybrid": False})
    null_values = entity_state._job_posting_fields_from_context({"remote": None, "hybrid": None})

    assert truthy_string["remote"] is None
    assert truthy_string["hybrid"] is None
    assert proper_bools["remote"] is True
    assert proper_bools["hybrid"] is False
    assert null_values["remote"] is None
    assert null_values["hybrid"] is None


def test_entity_type_from_job_operation_id():
    trigger_task_path = Path(__file__).resolve().parents[1] / "trigger" / "src" / "tasks" / "run-pipeline.ts"
    source = trigger_task_path.read_text(encoding="utf-8")
    assert re.search(r'if \(operationId\.startsWith\("job\."\)\) return "job";', source)
