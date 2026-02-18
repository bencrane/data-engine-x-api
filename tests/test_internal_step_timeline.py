from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from app.auth.models import AuthContext
from app.routers import entities_v1, internal


def _required_step_metadata_keys() -> set[str]:
    return {
        "event_type",
        "step_result_id",
        "step_position",
        "operation_id",
        "step_status",
        "skip_reason",
        "duration_ms",
        "provider_attempts",
        "condition",
        "error_message",
        "error_details",
    }


@pytest.mark.asyncio
async def test_internal_step_timeline_success_records_found(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}

    def _record_entity_event(**kwargs):
        captured.update(kwargs)
        return {"id": "event-1"}

    monkeypatch.setattr(internal, "record_entity_event", _record_entity_event)
    monkeypatch.setattr(internal, "resolve_company_entity_id", lambda **_kwargs: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    payload = internal.InternalRecordStepTimelineEventRequest(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="33333333-3333-3333-3333-333333333333",
        pipeline_run_id="44444444-4444-4444-4444-444444444444",
        entity_type="company",
        cumulative_context={"domain": "acme.com"},
        step_result_id="55555555-5555-5555-5555-555555555555",
        step_position=2,
        operation_id="company.enrich.profile",
        step_status="succeeded",
        duration_ms=345,
        provider_attempts=[
            {"provider": "blitzapi", "status": "failed"},
            {"provider": "leadmagic", "status": "succeeded"},
        ],
        operation_result={"output": {"canonical_name": "Acme", "employee_count": None}},
    )

    response = await internal.internal_record_step_timeline_event(payload, None)

    assert response.data["recorded"] is True
    assert response.data["event_id"] == "event-1"
    assert captured["status"] == "found"
    assert captured["provider"] == "leadmagic"
    assert captured["fields_updated"] == ["canonical_name"]
    assert set(captured["metadata"].keys()) == _required_step_metadata_keys()
    assert captured["metadata"]["event_type"] == "step_execution"


@pytest.mark.asyncio
async def test_internal_step_timeline_failed_maps_failed(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(internal, "record_entity_event", lambda **kwargs: captured.update(kwargs) or {"id": "event-2"})
    monkeypatch.setattr(internal, "resolve_person_entity_id", lambda **_kwargs: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    payload = internal.InternalRecordStepTimelineEventRequest(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="33333333-3333-3333-3333-333333333333",
        pipeline_run_id="44444444-4444-4444-4444-444444444444",
        entity_type="person",
        cumulative_context={"linkedin_url": "https://linkedin.com/in/alex"},
        step_result_id="66666666-6666-6666-6666-666666666666",
        step_position=3,
        operation_id="person.contact.resolve_email",
        step_status="failed",
        error_message="provider timeout",
        error_details={"provider": "leadmagic"},
    )

    response = await internal.internal_record_step_timeline_event(payload, None)

    assert response.data["recorded"] is True
    assert captured["status"] == "failed"
    assert captured["fields_updated"] is None
    assert captured["metadata"]["error_message"] == "provider timeout"


@pytest.mark.asyncio
async def test_internal_step_timeline_skipped_maps_skipped_and_skip_reason(monkeypatch: pytest.MonkeyPatch):
    captured: dict[str, Any] = {}
    monkeypatch.setattr(internal, "record_entity_event", lambda **kwargs: captured.update(kwargs) or {"id": "event-3"})
    monkeypatch.setattr(internal, "resolve_person_entity_id", lambda **_kwargs: "cccccccc-cccc-cccc-cccc-cccccccccccc")

    payload = internal.InternalRecordStepTimelineEventRequest(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="33333333-3333-3333-3333-333333333333",
        pipeline_run_id="44444444-4444-4444-4444-444444444444",
        entity_type="person",
        cumulative_context={"full_name": "Alex Doe"},
        step_result_id="77777777-7777-7777-7777-777777777777",
        step_position=4,
        operation_id="person.contact.resolve_mobile_phone",
        step_status="skipped",
        skip_reason="condition_not_met",
    )

    response = await internal.internal_record_step_timeline_event(payload, None)

    assert response.data["recorded"] is True
    assert captured["status"] == "skipped"
    assert captured["metadata"]["skip_reason"] == "condition_not_met"


def test_internal_provider_selection_logic():
    attempts = [
        {"provider": "blitzapi", "status": "failed"},
        {"provider": "leadmagic", "status": "succeeded"},
        {"provider": "prospeo", "status": "found"},
    ]
    assert internal._select_provider_from_attempts(attempts) == "leadmagic"
    assert internal._select_provider_from_attempts([{"provider": "blitzapi", "status": "failed"}]) == "blitzapi"
    assert internal._select_provider_from_attempts([]) is None


@pytest.mark.asyncio
async def test_internal_step_timeline_invalid_entity_context_is_best_effort(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(internal, "resolve_person_entity_id", lambda **_kwargs: (_ for _ in ()).throw(ValueError("invalid entity context")))
    monkeypatch.setattr(internal, "record_entity_event", lambda **_kwargs: {"id": "unexpected"})

    payload = internal.InternalRecordStepTimelineEventRequest(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="33333333-3333-3333-3333-333333333333",
        pipeline_run_id="44444444-4444-4444-4444-444444444444",
        entity_type="person",
        cumulative_context={},
        step_result_id="88888888-8888-8888-8888-888888888888",
        step_position=5,
        operation_id="person.contact.resolve_email",
        step_status="failed",
    )

    response = await internal.internal_record_step_timeline_event(payload, None)

    assert response.data["attempted"] is True
    assert response.data["recorded"] is False
    assert response.data["event_id"] is None
    assert "invalid entity context" in response.data["error"]


class _TimelineQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows
        self._filters: list[tuple[str, Any]] = []
        self._start = 0
        self._end = None
        self._order_field: str | None = None
        self._order_desc = False

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, field: str, value: Any):
        self._filters.append((field, value))
        return self

    def order(self, field: str, desc: bool = False):
        self._order_field = field
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._start = start
        self._end = end
        return self

    def execute(self):
        rows = self._rows
        for field, value in self._filters:
            if field == "metadata->>event_type":
                rows = [row for row in rows if (row.get("metadata") or {}).get("event_type") == value]
            else:
                rows = [row for row in rows if row.get(field) == value]
        if self._order_field is not None:
            rows = sorted(rows, key=lambda row: row.get(self._order_field), reverse=self._order_desc)
        if self._end is not None:
            rows = rows[self._start : self._end + 1]
        return SimpleNamespace(data=[dict(row) for row in rows])


@dataclass
class _TimelineSupabase:
    rows: list[dict[str, Any]]

    def table(self, table_name: str):
        if table_name != "entity_timeline":
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _TimelineQuery(self.rows)


@pytest.mark.asyncio
async def test_entities_timeline_filters_pipeline_submission_and_event_type(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "id": "evt-1",
            "org_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "22222222-2222-2222-2222-222222222222",
            "entity_type": "person",
            "entity_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "pipeline_run_id": "run-1",
            "submission_id": "sub-1",
            "metadata": {"event_type": "step_execution"},
            "created_at": "2026-02-18T00:00:10Z",
        },
        {
            "id": "evt-2",
            "org_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "22222222-2222-2222-2222-222222222222",
            "entity_type": "person",
            "entity_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            "pipeline_run_id": "run-2",
            "submission_id": "sub-1",
            "metadata": {"event_type": "fan_out_discovery"},
            "created_at": "2026-02-18T00:00:09Z",
        },
    ]
    monkeypatch.setattr(entities_v1, "get_supabase_client", lambda: _TimelineSupabase(rows=rows))

    auth = AuthContext(
        user_id="u1",
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        role="org_admin",
        auth_method="jwt",
    )
    payload = entities_v1.EntityTimelineRequest(
        entity_type="person",
        entity_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        pipeline_run_id="run-1",
        submission_id="sub-1",
        event_type="step_execution",
    )

    response = await entities_v1.get_entity_timeline(payload, auth)
    assert len(response.data["items"]) == 1
    assert response.data["items"][0]["id"] == "evt-1"


@pytest.mark.asyncio
async def test_entities_timeline_tenant_scoping_unchanged_for_company_member(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "id": "evt-1",
            "org_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "company-a",
            "entity_type": "company",
            "entity_id": "company-entity",
            "metadata": {"event_type": "step_execution"},
            "created_at": "2026-02-18T00:00:10Z",
        },
        {
            "id": "evt-2",
            "org_id": "11111111-1111-1111-1111-111111111111",
            "company_id": "company-b",
            "entity_type": "company",
            "entity_id": "company-entity",
            "metadata": {"event_type": "step_execution"},
            "created_at": "2026-02-18T00:00:09Z",
        },
    ]
    monkeypatch.setattr(entities_v1, "get_supabase_client", lambda: _TimelineSupabase(rows=rows))

    auth = AuthContext(
        user_id="u1",
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="company-a",
        role="member",
        auth_method="jwt",
    )
    payload = entities_v1.EntityTimelineRequest(
        entity_type="company",
        entity_id="company-entity",
    )

    response = await entities_v1.get_entity_timeline(payload, auth)
    assert len(response.data["items"]) == 1
    assert response.data["items"][0]["company_id"] == "company-a"
