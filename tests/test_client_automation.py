from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import company_blueprint_configs
from app.services import company_blueprint_schedules
from app.services.company_entity_associations import record_company_entity_association
from app.auth.models import AuthContext
from app.routers.entities_v1 import CompanyEntitiesListRequest, list_company_entities


class _Query:
    def __init__(self, data):
        self._data = data

    def eq(self, *_args, **_kwargs):
        return self

    def lte(self, *_args, **_kwargs):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return SimpleNamespace(data=self._data)


class _ScheduleRunsTableStub:
    def __init__(self):
        self.insert_calls = 0
        self.update_calls: list[dict] = []

    def insert(self, payload):
        self.insert_calls += 1
        if self.insert_calls == 1:
            return _Query([{"id": "run-1", **payload}])
        # Simulate duplicate fire-window claim conflict.
        raise RuntimeError("duplicate key value violates unique constraint")

    def update(self, payload):
        self.update_calls.append(payload)
        return _Query([payload])


class _SchedulesTableStub:
    def __init__(self):
        self.rows = [
            {
                "id": "schedule-1",
                "org_id": "org-1",
                "company_id": "company-1",
                "config_id": "config-1",
                "cadence_minutes": 15,
                "next_run_at": "2026-03-11T10:00:00+00:00",
            }
        ]
        self.update_calls: list[dict] = []

    def select(self, *_args, **_kwargs):
        return _Query(self.rows)

    def update(self, payload):
        self.update_calls.append(payload)
        return _Query([payload])


class _SubmissionsTableStub:
    def __init__(self):
        self.existing: list[dict] = []

    def select(self, *_args, **_kwargs):
        return _Query(self.existing)


class _ClientStub:
    def __init__(self):
        self.schedules = _SchedulesTableStub()
        self.schedule_runs = _ScheduleRunsTableStub()
        self.submissions = _SubmissionsTableStub()

    def table(self, table_name: str):
        if table_name == "company_blueprint_schedules":
            return self.schedules
        if table_name == "company_blueprint_schedule_runs":
            return self.schedule_runs
        if table_name == "submissions":
            return self.submissions
        raise AssertionError(f"Unexpected table: {table_name}")


@pytest.mark.asyncio
async def test_due_claim_idempotency(monkeypatch: pytest.MonkeyPatch):
    client = _ClientStub()
    monkeypatch.setattr(company_blueprint_schedules, "get_supabase_client", lambda: client)

    first = company_blueprint_schedules._claim_due_schedule_runs(  # noqa: SLF001
        now=company_blueprint_schedules._parse_iso("2026-03-11T10:05:00+00:00"),  # noqa: SLF001
        limit=100,
        scheduler_task_id="scheduler-task",
        scheduler_invoked_at="2026-03-11T10:05:00+00:00",
    )
    second = company_blueprint_schedules._claim_due_schedule_runs(  # noqa: SLF001
        now=company_blueprint_schedules._parse_iso("2026-03-11T10:05:30+00:00"),  # noqa: SLF001
        limit=100,
        scheduler_task_id="scheduler-task",
        scheduler_invoked_at="2026-03-11T10:05:30+00:00",
    )

    assert len(first) == 1
    assert len(second) == 0
    assert len(client.schedules.update_calls) == 1


@pytest.mark.asyncio
async def test_scheduled_submission_includes_provenance(monkeypatch: pytest.MonkeyPatch):
    claimed = [
        {
            "schedule": {
                "id": "schedule-1",
                "org_id": "org-1",
                "company_id": "company-1",
                "config_id": "config-1",
            },
            "schedule_run": {
                "id": "run-1",
                "scheduled_for": "2026-03-11T10:00:00+00:00",
            },
        }
    ]
    client = _ClientStub()
    captured: dict = {}

    monkeypatch.setattr(company_blueprint_schedules, "_claim_due_schedule_runs", lambda **_: claimed)
    monkeypatch.setattr(company_blueprint_schedules, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        company_blueprint_schedules,
        "get_company_blueprint_config",
        lambda **_: {
            "id": "config-1",
            "blueprint_id": "blueprint-1",
            "input_payload": {"domain": "outboundsolutions.com"},
            "is_active": True,
        },
    )

    async def _create_submission_and_trigger_pipeline(**kwargs):
        captured.update(kwargs)
        return {"submission_id": "sub-1", "pipeline_run_id": "run-pipeline-1"}

    monkeypatch.setattr(
        company_blueprint_schedules,
        "create_submission_and_trigger_pipeline",
        _create_submission_and_trigger_pipeline,
    )

    result = await company_blueprint_schedules.evaluate_and_execute_due_schedules(
        max_schedules=10,
        scheduler_task_id="client-automation-scheduler",
        scheduler_invoked_at="2026-03-11T10:15:00+00:00",
    )

    assert result["processed_count"] == 1
    assert captured["source"] == "client_automation_schedule"
    assert captured["metadata"]["company_blueprint_config_id"] == "config-1"
    assert captured["metadata"]["company_blueprint_schedule_id"] == "schedule-1"
    assert captured["metadata"]["schedule_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_schedule_run_recovers_duplicate_submission(monkeypatch: pytest.MonkeyPatch):
    claimed = [
        {
            "schedule": {
                "id": "schedule-1",
                "org_id": "org-1",
                "company_id": "company-1",
                "config_id": "config-1",
            },
            "schedule_run": {
                "id": "run-1",
                "scheduled_for": "2026-03-11T10:00:00+00:00",
            },
        }
    ]
    client = _ClientStub()
    client.submissions.existing = [{"id": "submission-existing"}]

    monkeypatch.setattr(company_blueprint_schedules, "_claim_due_schedule_runs", lambda **_: claimed)
    monkeypatch.setattr(company_blueprint_schedules, "get_supabase_client", lambda: client)
    monkeypatch.setattr(
        company_blueprint_schedules,
        "get_company_blueprint_config",
        lambda **_: {
            "id": "config-1",
            "blueprint_id": "blueprint-1",
            "input_payload": {"domain": "outboundsolutions.com"},
            "is_active": True,
        },
    )

    async def _raise_duplicate(**_kwargs):
        raise RuntimeError("duplicate key value violates unique constraint")

    monkeypatch.setattr(
        company_blueprint_schedules,
        "create_submission_and_trigger_pipeline",
        _raise_duplicate,
    )

    result = await company_blueprint_schedules.evaluate_and_execute_due_schedules(
        scheduler_task_id="client-automation-scheduler",
    )
    assert result["results"][0]["status"] == "succeeded"
    assert result["results"][0]["recovered_from_duplicate"] is True


def test_record_company_entity_association_uses_upsert(monkeypatch: pytest.MonkeyPatch):
    recorded: dict = {}

    class _AssociationTable:
        def upsert(self, payload, on_conflict=None):
            recorded["payload"] = payload
            recorded["on_conflict"] = on_conflict
            return _Query([payload])

    class _AssociationClient:
        def table(self, table_name: str):
            assert table_name == "company_entity_associations"
            return _AssociationTable()

    from app.services import company_entity_associations

    monkeypatch.setattr(company_entity_associations, "get_supabase_client", lambda: _AssociationClient())

    row = record_company_entity_association(
        org_id="org-1",
        company_id="company-1",
        entity_type="person",
        entity_id="00000000-0000-0000-0000-000000000123",
        source_submission_id="submission-1",
        source_pipeline_run_id="pipeline-1",
    )

    assert row["entity_type"] == "person"
    assert recorded["on_conflict"] == "org_id,company_id,entity_type,entity_id"


def test_company_blueprint_config_crud(monkeypatch: pytest.MonkeyPatch):
    state = {
        "row": {
            "id": "config-1",
            "org_id": "org-1",
            "company_id": "company-1",
            "blueprint_id": "blueprint-1",
            "name": "Outbound Solutions Hiring Config",
            "description": "initial",
            "input_payload": {"domain": "outboundsolutions.com"},
            "is_active": True,
        }
    }

    class _ConfigsTable:
        def insert(self, payload):
            state["row"] = {"id": "config-1", **payload}
            return _Query([state["row"]])

        def select(self, *_args, **_kwargs):
            return _Query([state["row"]])

        def update(self, payload):
            state["row"] = {**state["row"], **payload}
            return _Query([state["row"]])

    class _ConfigClient:
        def table(self, table_name: str):
            assert table_name == "company_blueprint_configs"
            return _ConfigsTable()

    monkeypatch.setattr(company_blueprint_configs, "_company_in_org", lambda *_: True)
    monkeypatch.setattr(company_blueprint_configs, "_blueprint_in_org", lambda *_: True)
    monkeypatch.setattr(company_blueprint_configs, "get_supabase_client", lambda: _ConfigClient())

    created = company_blueprint_configs.create_company_blueprint_config(
        org_id="org-1",
        company_id="company-1",
        blueprint_id="blueprint-1",
        name="Outbound Solutions Hiring Config",
        description="initial",
        input_payload={"domain": "outboundsolutions.com"},
        is_active=True,
        actor_user_id="user-1",
    )
    assert created["name"] == "Outbound Solutions Hiring Config"

    listed = company_blueprint_configs.list_company_blueprint_configs(org_id="org-1", company_id="company-1")
    assert len(listed) == 1
    assert listed[0]["id"] == "config-1"

    fetched = company_blueprint_configs.get_company_blueprint_config(org_id="org-1", config_id="config-1")
    assert fetched is not None
    assert fetched["company_id"] == "company-1"

    updated = company_blueprint_configs.update_company_blueprint_config(
        org_id="org-1",
        config_id="config-1",
        actor_user_id="user-2",
        description="updated",
    )
    assert updated is not None
    assert updated["description"] == "updated"


def test_company_blueprint_schedule_crud(monkeypatch: pytest.MonkeyPatch):
    state = {
        "row": {
            "id": "schedule-1",
            "org_id": "org-1",
            "company_id": "company-1",
            "config_id": "config-1",
            "name": "Outbound Solutions Daily Run",
            "timezone": "UTC",
            "cadence_minutes": 60,
            "next_run_at": "2026-03-11T12:00:00+00:00",
            "is_active": True,
        }
    }

    class _SchedulesTable:
        def insert(self, payload):
            state["row"] = {"id": "schedule-1", **payload}
            return _Query([state["row"]])

        def select(self, *_args, **_kwargs):
            return _Query([state["row"]])

        def update(self, payload):
            state["row"] = {**state["row"], **payload}
            return _Query([state["row"]])

    class _ScheduleClient:
        def table(self, table_name: str):
            assert table_name == "company_blueprint_schedules"
            return _SchedulesTable()

    monkeypatch.setattr(
        company_blueprint_schedules,
        "get_company_blueprint_config",
        lambda **_: {"id": "config-1", "company_id": "company-1", "is_active": True},
    )
    monkeypatch.setattr(company_blueprint_schedules, "get_supabase_client", lambda: _ScheduleClient())

    created = company_blueprint_schedules.create_company_blueprint_schedule(
        org_id="org-1",
        company_id="company-1",
        config_id="config-1",
        name="Outbound Solutions Daily Run",
        timezone_name="UTC",
        cadence_minutes=60,
        next_run_at="2026-03-11T12:00:00+00:00",
        is_active=True,
        actor_user_id="user-1",
    )
    assert created["name"] == "Outbound Solutions Daily Run"

    listed = company_blueprint_schedules.list_company_blueprint_schedules(org_id="org-1", company_id="company-1")
    assert len(listed) == 1
    assert listed[0]["id"] == "schedule-1"

    fetched = company_blueprint_schedules.get_company_blueprint_schedule(org_id="org-1", schedule_id="schedule-1")
    assert fetched is not None
    assert fetched["config_id"] == "config-1"

    updated = company_blueprint_schedules.update_company_blueprint_schedule(
        org_id="org-1",
        schedule_id="schedule-1",
        actor_user_id="user-2",
        cadence_minutes=30,
    )
    assert updated is not None
    assert updated["cadence_minutes"] == 30


@pytest.mark.asyncio
async def test_company_entity_query_uses_association_scoping(monkeypatch: pytest.MonkeyPatch):
    class _EntityTable:
        def select(self, *_args, **_kwargs):
            return _Query([])

    class _EntityClient:
        def table(self, table_name: str):
            assert table_name == "company_entities"
            return _EntityTable()

    from app.routers import entities_v1

    monkeypatch.setattr(entities_v1, "get_supabase_client", lambda: _EntityClient())
    monkeypatch.setattr(entities_v1, "list_associated_entity_ids", lambda **_: [])

    response = await list_company_entities(
        CompanyEntitiesListRequest(company_id=None, page=1, per_page=25),
        AuthContext(org_id="org-1", company_id="company-1", role="company_admin", auth_method="jwt"),
    )
    assert response.data["items"] == []
