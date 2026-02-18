from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.auth.models import AuthContext
from app.routers import execute_v1, internal


class _InMemoryQuery:
    def __init__(self, rows: list[dict[str, Any]], mode: str, update_payload: dict[str, Any] | None = None):
        self._rows = rows
        self._mode = mode
        self._update_payload = update_payload or {}
        self._filters: list[tuple[str, Any]] = []
        self._order_key: str | None = None
        self._order_desc = False
        self._limit: int | None = None

    def eq(self, field: str, value: Any):
        self._filters.append((field, value))
        return self

    def order(self, field: str, desc: bool = False):
        self._order_key = field
        self._order_desc = desc
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def execute(self):
        matched = [row for row in self._rows if all(row.get(field) == value for field, value in self._filters)]
        if self._mode == "update":
            updated: list[dict[str, Any]] = []
            for row in matched:
                row.update(self._update_payload)
                updated.append(dict(row))
            return SimpleNamespace(data=updated)

        if self._order_key is not None:
            matched = sorted(matched, key=lambda row: row.get(self._order_key), reverse=self._order_desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        return SimpleNamespace(data=[dict(row) for row in matched])


class _InMemoryTable:
    def __init__(self, rows: list[dict[str, Any]]):
        self._rows = rows

    def select(self, *_args, **_kwargs):
        return _InMemoryQuery(self._rows, mode="select")

    def update(self, payload: dict[str, Any]):
        return _InMemoryQuery(self._rows, mode="update", update_payload=payload)


@dataclass
class _InMemorySupabase:
    tables: dict[str, list[dict[str, Any]]]

    def table(self, table_name: str):
        if table_name not in self.tables:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _InMemoryTable(self.tables[table_name])


@pytest.mark.asyncio
async def test_internal_fan_out_accepts_child_parent_and_returns_grandchildren(monkeypatch: pytest.MonkeyPatch):
    supabase = _InMemorySupabase(
        tables={
            "pipeline_runs": [
                {
                    "id": "child-run-1",
                    "org_id": "11111111-1111-1111-1111-111111111111",
                    "company_id": "22222222-2222-2222-2222-222222222222",
                    "submission_id": "submission-1",
                    "blueprint_id": "blueprint-1",
                    "blueprint_snapshot": {"entity": {"entity_type": "company", "input": {"domain": "acme.com"}}},
                    "parent_pipeline_run_id": "root-run-1",
                }
            ]
        }
    )
    mocked_child_creation = AsyncMock(
        return_value={
            "child_runs": [
                {
                    "pipeline_run_id": "grandchild-run-1",
                    "pipeline_run_status": "queued",
                    "trigger_run_id": "trigger-grandchild-1",
                    "entity_type": "person",
                    "entity_input": {"full_name": "Alex Doe"},
                }
            ],
            "skipped_duplicates_count": 0,
            "skipped_duplicate_identifiers": [],
        }
    )

    monkeypatch.setattr(internal, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(internal, "create_fan_out_child_pipeline_runs", mocked_child_creation)
    monkeypatch.setattr(internal, "record_entity_event", lambda **_kwargs: None)
    monkeypatch.setattr(internal, "resolve_company_entity_id", lambda **_kwargs: "company-entity-id")
    monkeypatch.setattr(internal, "resolve_person_entity_id", lambda **_kwargs: "person-entity-id")

    payload = internal.InternalPipelineRunFanOutRequest(
        parent_pipeline_run_id="child-run-1",
        submission_id="submission-1",
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        blueprint_snapshot={
            "blueprint": {"id": "blueprint-1"},
            "steps": [
                {"id": "bs-3", "position": 3, "operation_id": "person.search", "fan_out": True},
                {"id": "bs-4", "position": 4, "operation_id": "person.contact.resolve_email"},
            ],
        },
        fan_out_entities=[{"full_name": "Alex Doe", "linkedin_url": "https://linkedin.com/in/alex"}],
        start_from_position=4,
        parent_cumulative_context={"domain": "acme.com"},
        fan_out_operation_id="person.search",
        provider="leadmagic",
        provider_attempts=[{"provider": "leadmagic", "status": "found"}],
    )
    result = await internal.internal_fan_out_pipeline_runs(payload, None)

    assert mocked_child_creation.await_count == 1
    assert result.data["parent_pipeline_run_id"] == "child-run-1"
    assert result.data["child_run_ids"] == ["grandchild-run-1"]


@pytest.mark.asyncio
async def test_batch_status_nests_grandchildren_recursively(monkeypatch: pytest.MonkeyPatch):
    org_id = "11111111-1111-1111-1111-111111111111"
    submission_id = "submission-1"
    root_run_id = "root-run-1"
    child_run_id = "child-run-1"
    grandchild_run_id = "grandchild-run-1"

    supabase = _InMemorySupabase(
        tables={
            "submissions": [
                {
                    "id": submission_id,
                    "org_id": org_id,
                    "company_id": "22222222-2222-2222-2222-222222222222",
                    "blueprint_id": "blueprint-1",
                    "status": "running",
                    "source": "test",
                    "metadata": {},
                    "created_at": "2026-02-17T00:00:00Z",
                    "updated_at": "2026-02-17T00:00:01Z",
                }
            ],
            "pipeline_runs": [
                {
                    "id": root_run_id,
                    "submission_id": submission_id,
                    "org_id": org_id,
                    "status": "succeeded",
                    "trigger_run_id": "trigger-root",
                    "parent_pipeline_run_id": None,
                    "created_at": "2026-02-17T00:00:00Z",
                    "blueprint_snapshot": {"entity": {"entity_type": "company", "index": 0}},
                },
                {
                    "id": child_run_id,
                    "submission_id": submission_id,
                    "org_id": org_id,
                    "status": "succeeded",
                    "trigger_run_id": "trigger-child",
                    "parent_pipeline_run_id": root_run_id,
                    "created_at": "2026-02-17T00:00:02Z",
                    "blueprint_snapshot": {"entity": {"entity_type": "company", "index": 0}},
                },
                {
                    "id": grandchild_run_id,
                    "submission_id": submission_id,
                    "org_id": org_id,
                    "status": "succeeded",
                    "trigger_run_id": "trigger-grandchild",
                    "parent_pipeline_run_id": child_run_id,
                    "created_at": "2026-02-17T00:00:03Z",
                    "blueprint_snapshot": {"entity": {"entity_type": "person", "index": 0}},
                },
            ],
            "step_results": [
                {
                    "id": "sr-1",
                    "pipeline_run_id": root_run_id,
                    "org_id": org_id,
                    "step_position": 1,
                    "status": "succeeded",
                    "output_payload": {"cumulative_context": {"domain": "acme.com"}},
                },
                {
                    "id": "sr-2",
                    "pipeline_run_id": child_run_id,
                    "org_id": org_id,
                    "step_position": 3,
                    "status": "succeeded",
                    "output_payload": {"cumulative_context": {"full_name": "Alex Doe"}},
                },
                {
                    "id": "sr-3",
                    "pipeline_run_id": grandchild_run_id,
                    "org_id": org_id,
                    "step_position": 4,
                    "status": "succeeded",
                    "output_payload": {"cumulative_context": {"work_email": "alex@example.com"}},
                },
            ],
        }
    )

    auth = AuthContext(
        user_id="33333333-3333-3333-3333-333333333333",
        org_id=org_id,
        company_id="22222222-2222-2222-2222-222222222222",
        role="org_admin",
        auth_method="jwt",
    )
    payload = execute_v1.BatchStatusRequest(submission_id=submission_id)
    monkeypatch.setattr(execute_v1, "get_supabase_client", lambda: supabase)

    response = await execute_v1.batch_status(payload, auth)

    root = response.data["runs"][0]
    child = root["children"][0]
    grandchild = child["children"][0]
    assert root["pipeline_run_id"] == root_run_id
    assert child["pipeline_run_id"] == child_run_id
    assert grandchild["pipeline_run_id"] == grandchild_run_id
    assert grandchild["entity_type"] == "person"
    assert response.data["summary"]["total"] == 3
    assert response.data["summary"]["completed"] == 3


@pytest.mark.asyncio
async def test_submission_sync_status_uses_all_run_depths(monkeypatch: pytest.MonkeyPatch):
    submission_id = "submission-1"
    supabase = _InMemorySupabase(
        tables={
            "submissions": [{"id": submission_id, "status": "queued"}],
            "pipeline_runs": [
                {"id": "root-run-1", "submission_id": submission_id, "status": "succeeded"},
                {"id": "child-run-1", "submission_id": submission_id, "status": "succeeded"},
                {"id": "grandchild-run-1", "submission_id": submission_id, "status": "failed"},
            ],
        }
    )
    payload = internal.InternalSubmissionSyncStatusRequest(submission_id=submission_id)
    monkeypatch.setattr(internal, "get_supabase_client", lambda: supabase)

    response = await internal.internal_sync_submission_status(payload, None)

    assert response.data["status"] == "failed"
