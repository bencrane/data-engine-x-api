from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.routers import entities_v1
from app.services import change_detection, entity_state


class _EntityUpdateQuery:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def eq(self, _key: str, _value: Any):
        return self

    def execute(self):
        return SimpleNamespace(data=[self.payload])


class _EntityInsertQuery:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def execute(self):
        return SimpleNamespace(data=[self.payload])


class _CompanyEntitiesTableStub:
    def __init__(self):
        self.last_update_payload: dict[str, Any] | None = None
        self.last_insert_payload: dict[str, Any] | None = None

    def update(self, payload: dict[str, Any]):
        self.last_update_payload = payload
        return _EntityUpdateQuery(payload)

    def insert(self, payload: dict[str, Any]):
        self.last_insert_payload = payload
        return _EntityInsertQuery(payload)


class _EntitySnapshotsWriteTableStub:
    def __init__(self, *, should_fail: bool = False):
        self.should_fail = should_fail
        self.inserted_rows: list[dict[str, Any]] = []

    def insert(self, payload: dict[str, Any]):
        self.inserted_rows.append(payload)
        return _EntitySnapshotsWriteQuery(payload, should_fail=self.should_fail)


class _EntitySnapshotsWriteQuery:
    def __init__(self, payload: dict[str, Any], *, should_fail: bool):
        self.payload = payload
        self.should_fail = should_fail

    def execute(self):
        if self.should_fail:
            raise RuntimeError("snapshot insert failed")
        return SimpleNamespace(data=[self.payload])


class _EntityStateClientStub:
    def __init__(self, *, snapshot_write_fails: bool = False):
        self.company_entities = _CompanyEntitiesTableStub()
        self.entity_snapshots = _EntitySnapshotsWriteTableStub(should_fail=snapshot_write_fails)

    def table(self, table_name: str):
        if table_name == "company_entities":
            return self.company_entities
        if table_name == "entity_snapshots":
            return self.entity_snapshots
        raise AssertionError(f"Unexpected table: {table_name}")


class _SnapshotsReadQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.filters: dict[str, Any] = {}
        self.limit_count: int | None = None
        self.order_field: str | None = None
        self.order_desc = False

    def eq(self, key: str, value: Any):
        self.filters[key] = value
        return self

    def order(self, field: str, desc: bool = False):
        self.order_field = field
        self.order_desc = desc
        return self

    def limit(self, value: int):
        self.limit_count = value
        return self

    def execute(self):
        filtered = list(self.rows)
        for key, expected in self.filters.items():
            filtered = [row for row in filtered if row.get(key) == expected]
        if self.order_field:
            filtered = sorted(
                filtered,
                key=lambda row: row.get(self.order_field),
                reverse=self.order_desc,
            )
        if self.limit_count is not None:
            filtered = filtered[: self.limit_count]
        return SimpleNamespace(data=filtered)


class _SnapshotsReadTableStub:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def select(self, _fields: str):
        return _SnapshotsReadQuery(self.rows)


class _SnapshotsReadClientStub:
    def __init__(self, rows: list[dict[str, Any]]):
        self.entity_snapshots = _SnapshotsReadTableStub(rows)

    def table(self, table_name: str):
        if table_name != "entity_snapshots":
            raise AssertionError(f"Unexpected table: {table_name}")
        return self.entity_snapshots


def test_snapshot_capture_upsert_writes_previous_state(monkeypatch: pytest.MonkeyPatch):
    existing = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "record_version": 4,
        "canonical_payload": {"employee_count": 50},
    }
    client = _EntityStateClientStub()

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: existing)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    updated = entity_state.upsert_company_entity(
        org_id=existing["org_id"],
        company_id=None,
        entity_id=existing["entity_id"],
        canonical_fields={"employee_count": 65},
        last_run_id="33333333-3333-3333-3333-333333333333",
    )

    assert updated["record_version"] == 5
    assert len(client.entity_snapshots.inserted_rows) == 1
    snapshot = client.entity_snapshots.inserted_rows[0]
    assert snapshot["org_id"] == existing["org_id"]
    assert snapshot["entity_type"] == "company"
    assert snapshot["entity_id"] == existing["entity_id"]
    assert snapshot["record_version"] == 4
    assert snapshot["canonical_payload"] == {"employee_count": 50}
    assert snapshot["source_run_id"] == "33333333-3333-3333-3333-333333333333"


def test_snapshot_not_captured_on_first_insert(monkeypatch: pytest.MonkeyPatch):
    client = _EntityStateClientStub()

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: None)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    created = entity_state.upsert_company_entity(
        org_id="11111111-1111-1111-1111-111111111111",
        company_id=None,
        canonical_fields={"company_domain": "acme.com", "employee_count": 10},
    )

    assert created["record_version"] == 1
    assert client.entity_snapshots.inserted_rows == []


def test_snapshot_failure_does_not_break_upsert(monkeypatch: pytest.MonkeyPatch):
    existing = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "record_version": 2,
        "canonical_payload": {"employee_count": 25},
    }
    client = _EntityStateClientStub(snapshot_write_fails=True)

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: existing)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    updated = entity_state.upsert_company_entity(
        org_id=existing["org_id"],
        company_id=None,
        entity_id=existing["entity_id"],
        canonical_fields={"employee_count": 30},
    )

    assert updated["record_version"] == 3
    assert client.company_entities.last_update_payload is not None


def test_detect_changes_numeric_increase(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"employee_count": 65},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"employee_count": 50},
        },
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["employee_count"],
    )

    assert result["has_changes"] is True
    change = result["changes"][0]
    assert change["change_type"] == "increased"
    assert change["absolute_change"] == 15.0
    assert change["percent_change"] == 30.0


def test_detect_changes_field_added(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"authority_status": "Active"},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"authority_status": None},
        },
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["authority_status"],
    )

    assert result["has_changes"] is True
    assert result["changes"][0]["change_type"] == "added"


def test_detect_changes_field_removed(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"authority_status": None},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"authority_status": "Active"},
        },
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["authority_status"],
    )

    assert result["has_changes"] is True
    assert result["changes"][0]["change_type"] == "removed"


def test_detect_changes_string_changed(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"industry_primary": "Healthcare"},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"industry_primary": "Software"},
        },
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["industry_primary"],
    )

    assert result["has_changes"] is True
    assert result["changes"][0]["change_type"] == "changed"


def test_detect_changes_insufficient_history(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"employee_count": 65},
        }
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["employee_count"],
    )

    assert result == {"has_changes": False, "reason": "insufficient_history"}


def test_detect_changes_no_changes(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"company_name": "Acme"},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"company_name": "Acme"},
        },
    ]
    monkeypatch.setattr(change_detection, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    result = change_detection.detect_entity_changes(
        org_id="org-1",
        entity_type="company",
        entity_id="entity-1",
        fields_to_watch=["company_name"],
    )

    assert result["has_changes"] is False
    assert result["reason"] == "no_changes"
    assert result["changes"] == []


@pytest.mark.asyncio
async def test_snapshot_query_returns_reverse_chronological_order(monkeypatch: pytest.MonkeyPatch):
    rows = [
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-15T00:00:00+00:00",
            "canonical_payload": {"employee_count": 50},
        },
        {
            "org_id": "org-1",
            "entity_type": "company",
            "entity_id": "entity-1",
            "captured_at": "2026-02-18T00:00:00+00:00",
            "canonical_payload": {"employee_count": 65},
        },
    ]
    monkeypatch.setattr(entities_v1, "get_supabase_client", lambda: _SnapshotsReadClientStub(rows))

    response = await entities_v1.get_entity_snapshots(
        payload=entities_v1.EntitySnapshotsRequest(
            entity_type="company",
            entity_id="entity-1",
            limit=2,
        ),
        auth=SimpleNamespace(org_id="org-1"),
    )

    returned = response.data["items"]
    assert len(returned) == 2
    assert returned[0]["captured_at"] == "2026-02-18T00:00:00+00:00"
    assert returned[1]["captured_at"] == "2026-02-15T00:00:00+00:00"
