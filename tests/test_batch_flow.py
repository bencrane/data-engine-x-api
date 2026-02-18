from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import submission_flow


class _Query:
    def __init__(self, data):
        self._data = data

    def eq(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _SubmissionTable:
    def __init__(self):
        self.insert_payload = None
        self.update_payload = None

    def insert(self, payload):
        self.insert_payload = payload
        return _Query([{"id": "submission-1"}])

    def update(self, payload):
        self.update_payload = payload
        return _Query([{"id": "submission-1", "status": payload.get("status")}])


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
        self.submissions = _SubmissionTable()
        self.pipeline_runs = _PipelineRunsTable()

    def table(self, table_name: str):
        if table_name == "submissions":
            return self.submissions
        if table_name == "pipeline_runs":
            return self.pipeline_runs
        raise AssertionError(f"Unexpected table: {table_name}")


@pytest.mark.asyncio
async def test_create_batch_submission_and_trigger_pipeline_runs(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    run_snapshots: list[dict] = []
    step_row_calls: list[dict] = []

    async_trigger = AsyncMock(side_effect=["trigger-1", "trigger-2"])
    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(submission_flow, "_ensure_company_in_org", lambda *_: True)
    monkeypatch.setattr(
        submission_flow,
        "_load_blueprint_snapshot",
        lambda *_: {
            "blueprint": {"id": "blueprint-1"},
            "steps": [
                {"id": "bs-1", "position": 1, "step_id": "step-1"},
                {"id": "bs-2", "position": 2, "step_id": "step-2"},
            ],
        },
    )

    run_counter = {"value": 0}

    def _create_pipeline_run_row(**kwargs):
        run_counter["value"] += 1
        run_id = f"run-{run_counter['value']}"
        run_snapshots.append(kwargs["blueprint_snapshot"])
        return {"id": run_id, "status": "queued"}

    def _create_step_result_rows(**kwargs):
        step_row_calls.append(kwargs)

    monkeypatch.setattr(submission_flow, "_create_pipeline_run_row", _create_pipeline_run_row)
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", _create_step_result_rows)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    result = await submission_flow.create_batch_submission_and_trigger_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        entities=[
            {"entity_type": "company", "input": {"domain": "acme.com"}},
            {"entity_type": "person", "input": {"linkedin_url": "https://linkedin.com/in/alex"}},
        ],
        source="test",
        metadata={"source": "unit-test"},
        submitted_by_user_id="44444444-4444-4444-4444-444444444444",
    )

    assert result["submission_id"] == "submission-1"
    assert len(result["pipeline_runs"]) == 2
    assert len(step_row_calls) == 2
    assert async_trigger.await_count == 2
    assert run_snapshots[0]["entity"]["input"] == {"domain": "acme.com"}
    assert run_snapshots[1]["entity"]["input"] == {"linkedin_url": "https://linkedin.com/in/alex"}


@pytest.mark.asyncio
async def test_create_fan_out_child_pipeline_runs(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    create_calls: list[dict] = []
    step_row_calls: list[dict] = []
    run_counter = {"value": 0}
    async_trigger = AsyncMock(side_effect=["child-trigger-1", "child-trigger-2"])

    def _create_pipeline_run_row(**kwargs):
        run_counter["value"] += 1
        run_id = f"child-run-{run_counter['value']}"
        create_calls.append(kwargs)
        return {"id": run_id, "status": "queued"}

    def _create_step_result_rows(**kwargs):
        step_row_calls.append(kwargs)

    monkeypatch.setattr(submission_flow, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(submission_flow, "_create_pipeline_run_row", _create_pipeline_run_row)
    monkeypatch.setattr(submission_flow, "_create_step_result_rows", _create_step_result_rows)
    monkeypatch.setattr(submission_flow, "trigger_pipeline_run", async_trigger)

    fan_out_result = await submission_flow.create_fan_out_child_pipeline_runs(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        submission_id="submission-1",
        parent_pipeline_run_id="parent-run-1",
        blueprint_id="33333333-3333-3333-3333-333333333333",
        blueprint_snapshot={
            "blueprint": {"id": "blueprint-1"},
            "steps": [
                {"id": "bs-1", "position": 1, "operation_id": "company.enrich.profile"},
                {"id": "bs-2", "position": 2, "operation_id": "person.search", "fan_out": True},
                {"id": "bs-3", "position": 3, "operation_id": "person.contact.resolve_email"},
            ],
        },
        fan_out_entities=[
            {"entity_type": "person", "full_name": "Alex A", "linkedin_url": "https://linkedin.com/in/alexa"},
            {"entity_type": "person", "full_name": "Sam B", "linkedin_url": "https://linkedin.com/in/samb"},
        ],
        start_from_position=3,
        parent_cumulative_context={"canonical_domain": "acme.com"},
    )

    child_runs = fan_out_result["child_runs"]
    assert len(child_runs) == 2
    assert async_trigger.await_count == 2
    assert all(call["parent_pipeline_run_id"] == "parent-run-1" for call in create_calls)
    assert all(call["start_from_position"] == 3 for call in step_row_calls)
    assert child_runs[0]["entity_input"]["canonical_domain"] == "acme.com"
    assert child_runs[0]["entity_input"]["full_name"] == "Alex A"
    assert fan_out_result["skipped_duplicates_count"] == 0
    assert fan_out_result["skipped_duplicate_identifiers"] == []
