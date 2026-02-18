from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import submission_flow
from app.services.entity_state import check_entity_freshness


class _Query:
    def __init__(self, data):
        self._data = data

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _PipelineRunsTable:
    def __init__(self):
        self.pending_update_payload = None

    def update(self, payload):
        self.pending_update_payload = payload
        return _Query(
            [
                {
                    "id": "unused",
                    "status": payload.get("status"),
                    "trigger_run_id": payload.get("trigger_run_id"),
                }
            ]
        )


class _SupabaseStub:
    def __init__(self):
        self.pipeline_runs = _PipelineRunsTable()

    def table(self, table_name: str):
        if table_name == "pipeline_runs":
            return self.pipeline_runs
        raise AssertionError(f"Unexpected table: {table_name}")


def _build_blueprint_snapshot() -> dict:
    return {
        "blueprint": {"id": "blueprint-1"},
        "steps": [
            {"id": "bs-1", "position": 1, "operation_id": "person.search"},
            {"id": "bs-2", "position": 2, "operation_id": "person.enrich.profile"},
        ],
    }


@pytest.mark.asyncio
async def test_fan_out_dedup_duplicate_linkedin_urls(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    create_calls: list[dict] = []
    async_trigger = AsyncMock(side_effect=["trigger-1"])

    def _create_pipeline_run_row(**kwargs):
        create_calls.append(kwargs)
        return {"id": f"run-{len(create_calls)}", "status": "queued"}

    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(submission_flow, "_create_pipeline_run_row", _create_pipeline_run_row)
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", lambda **_: None)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    result = await submission_flow.create_fan_out_child_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="submission-1",
        parent_pipeline_run_id="parent-run-1",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        blueprint_snapshot=_build_blueprint_snapshot(),
        fan_out_entities=[
            {"entity_type": "person", "linkedin_url": "https://linkedin.com/in/alex"},
            {"entity_type": "person", "linkedin_url": "https://linkedin.com/in/alex/"},
        ],
        start_from_position=2,
        parent_cumulative_context={"company_domain": "acme.com"},
    )

    assert len(result["child_runs"]) == 1
    assert result["skipped_duplicates_count"] == 1
    assert result["skipped_duplicate_identifiers"] == ["person:linkedin:https://linkedin.com/in/alex"]
    assert async_trigger.await_count == 1


@pytest.mark.asyncio
async def test_fan_out_dedup_duplicate_company_domains(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    create_calls: list[dict] = []
    async_trigger = AsyncMock(side_effect=["trigger-1"])

    def _create_pipeline_run_row(**kwargs):
        create_calls.append(kwargs)
        return {"id": f"run-{len(create_calls)}", "status": "queued"}

    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(submission_flow, "_create_pipeline_run_row", _create_pipeline_run_row)
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", lambda **_: None)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    result = await submission_flow.create_fan_out_child_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="submission-1",
        parent_pipeline_run_id="parent-run-1",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        blueprint_snapshot=_build_blueprint_snapshot(),
        fan_out_entities=[
            {"entity_type": "company", "company_domain": "acme.com"},
            {"entity_type": "company", "domain": "www.acme.com"},
        ],
        start_from_position=2,
        parent_cumulative_context={},
    )

    assert len(result["child_runs"]) == 1
    assert result["skipped_duplicates_count"] == 1
    assert result["skipped_duplicate_identifiers"] == ["company:domain:acme.com"]
    assert async_trigger.await_count == 1


@pytest.mark.asyncio
async def test_fan_out_dedup_no_duplicates(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    async_trigger = AsyncMock(side_effect=["trigger-1", "trigger-2", "trigger-3"])

    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(
        submission_flow,
        "_create_pipeline_run_row",
        lambda **kwargs: {"id": f"run-{kwargs['blueprint_snapshot']['entity']['index']}", "status": "queued"},
    )
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", lambda **_: None)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    result = await submission_flow.create_fan_out_child_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="submission-1",
        parent_pipeline_run_id="parent-run-1",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        blueprint_snapshot=_build_blueprint_snapshot(),
        fan_out_entities=[
            {"entity_type": "person", "linkedin_url": "https://linkedin.com/in/alex"},
            {"entity_type": "person", "linkedin_url": "https://linkedin.com/in/sam"},
            {"entity_type": "person", "linkedin_url": "https://linkedin.com/in/taylor"},
        ],
        start_from_position=2,
        parent_cumulative_context={},
    )

    assert len(result["child_runs"]) == 3
    assert result["skipped_duplicates_count"] == 0
    assert result["skipped_duplicate_identifiers"] == []
    assert async_trigger.await_count == 3


@pytest.mark.asyncio
async def test_fan_out_dedup_mixed_identifiers(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    async_trigger = AsyncMock(side_effect=["trigger-1", "trigger-2"])

    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(
        submission_flow,
        "_create_pipeline_run_row",
        lambda **kwargs: {"id": f"run-{kwargs['blueprint_snapshot']['entity']['index']}", "status": "queued"},
    )
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", lambda **_: None)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    result = await submission_flow.create_fan_out_child_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="submission-1",
        parent_pipeline_run_id="parent-run-1",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        blueprint_snapshot=_build_blueprint_snapshot(),
        fan_out_entities=[
            {
                "entity_type": "person",
                "linkedin_url": "https://linkedin.com/in/alex",
                "work_email": "alex@acme.com",
            },
            {"entity_type": "person", "work_email": "alex@acme.com"},
            {"entity_type": "person", "work_email": "sam@acme.com"},
        ],
        start_from_position=2,
        parent_cumulative_context={},
    )

    assert len(result["child_runs"]) == 2
    assert result["skipped_duplicates_count"] == 1
    assert result["skipped_duplicate_identifiers"] == ["person:email:alex@acme.com"]
    assert async_trigger.await_count == 2


def test_check_entity_freshness_returns_fresh_with_payload(monkeypatch: pytest.MonkeyPatch):
    fresh_record = {
        "entity_id": "person-1",
        "last_enriched_at": (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat(),
        "canonical_payload": {"linkedin_url": "https://linkedin.com/in/alex", "title": "VP"},
    }
    monkeypatch.setattr(
        "app.services.entity_state._lookup_person_by_natural_key",
        lambda *_args, **_kwargs: fresh_record,
    )

    result = check_entity_freshness(
        org_id="11111111-1111-1111-1111-111111111111",
        entity_type="person",
        identifiers={"linkedin_url": "https://linkedin.com/in/alex"},
        max_age_hours=72,
    )

    assert result["fresh"] is True
    assert result["entity_id"] == "person-1"
    assert result["canonical_payload"]["title"] == "VP"
    assert result["age_hours"] < 72


def test_check_entity_freshness_returns_false_when_stale(monkeypatch: pytest.MonkeyPatch):
    stale_record = {
        "entity_id": "person-2",
        "last_enriched_at": (datetime.now(timezone.utc) - timedelta(hours=120)).isoformat(),
        "canonical_payload": {"linkedin_url": "https://linkedin.com/in/stale"},
    }
    monkeypatch.setattr(
        "app.services.entity_state._lookup_person_by_natural_key",
        lambda *_args, **_kwargs: stale_record,
    )

    result = check_entity_freshness(
        org_id="11111111-1111-1111-1111-111111111111",
        entity_type="person",
        identifiers={"linkedin_url": "https://linkedin.com/in/stale"},
        max_age_hours=72,
    )

    assert result == {"fresh": False, "entity_id": None}


def test_check_entity_freshness_returns_false_when_entity_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "app.services.entity_state._lookup_person_by_natural_key",
        lambda *_args, **_kwargs: None,
    )

    result = check_entity_freshness(
        org_id="11111111-1111-1111-1111-111111111111",
        entity_type="person",
        identifiers={"work_email": "missing@acme.com"},
        max_age_hours=72,
    )

    assert result == {"fresh": False, "entity_id": None}


def test_check_entity_freshness_returns_false_for_missing_identifiers():
    result = check_entity_freshness(
        org_id="11111111-1111-1111-1111-111111111111",
        entity_type="person",
        identifiers={},
        max_age_hours=72,
    )

    assert result == {"fresh": False, "entity_id": None}


def _simulate_runner_step_with_freshness(
    *,
    cumulative_context: dict,
    skip_if_fresh: dict | None,
    freshness_result: dict | None,
) -> tuple[str, dict]:
    context = dict(cumulative_context)
    if not skip_if_fresh:
        return "execute", context

    if freshness_result and freshness_result.get("fresh") is True:
        payload = freshness_result.get("canonical_payload")
        if isinstance(payload, dict):
            context.update(payload)
        return "skipped:entity_state_fresh", context
    return "execute", context


def test_runner_skip_if_fresh_marks_skipped_and_merges_payload():
    action, merged_context = _simulate_runner_step_with_freshness(
        cumulative_context={"linkedin_url": "https://linkedin.com/in/alex"},
        skip_if_fresh={"max_age_hours": 72, "identity_fields": ["linkedin_url"]},
        freshness_result={
            "fresh": True,
            "entity_id": "person-1",
            "canonical_payload": {"title": "VP Engineering", "work_email": "alex@acme.com"},
        },
    )

    assert action == "skipped:entity_state_fresh"
    assert merged_context["title"] == "VP Engineering"
    assert merged_context["work_email"] == "alex@acme.com"


def test_runner_skip_if_fresh_executes_when_entity_stale():
    action, merged_context = _simulate_runner_step_with_freshness(
        cumulative_context={"linkedin_url": "https://linkedin.com/in/alex"},
        skip_if_fresh={"max_age_hours": 72, "identity_fields": ["linkedin_url"]},
        freshness_result={"fresh": False, "entity_id": None},
    )

    assert action == "execute"
    assert merged_context == {"linkedin_url": "https://linkedin.com/in/alex"}
