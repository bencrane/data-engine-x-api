from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import entity_state


class _UpdateQuery:
    def __init__(self, payload: dict):
        self.payload = payload
        self._filters: list[tuple[str, object]] = []

    def eq(self, key: str, value: object):
        self._filters.append((key, value))
        return self

    def execute(self):
        return SimpleNamespace(data=[self.payload])


class _InsertQuery:
    def __init__(self, payload: dict):
        self.payload = payload

    def execute(self):
        return SimpleNamespace(data=[self.payload])


class _TableStub:
    def __init__(self):
        self.last_update_payload: dict | None = None
        self.last_insert_payload: dict | None = None

    def update(self, payload: dict):
        self.last_update_payload = payload
        return _UpdateQuery(payload)

    def insert(self, payload: dict):
        self.last_insert_payload = payload
        return _InsertQuery(payload)


class _ClientStub:
    def __init__(self):
        self.company_entities = _TableStub()

    def table(self, table_name: str):
        if table_name != "company_entities":
            raise AssertionError(f"Unexpected table: {table_name}")
        return self.company_entities


def test_upsert_company_entity_additive_merge(monkeypatch: pytest.MonkeyPatch):
    existing = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "company_id": "33333333-3333-3333-3333-333333333333",
        "canonical_name": "Old Name",
        "industry": "Software",
        "record_version": 3,
        "canonical_payload": {
            "canonical_name": "Old Name",
            "industry": "Software",
            "description": "Old description",
        },
    }
    client = _ClientStub()

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: existing)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    updated = entity_state.upsert_company_entity(
        org_id=existing["org_id"],
        company_id=existing["company_id"],
        entity_id=existing["entity_id"],
        canonical_fields={
            "canonical_name": "New Name",
            "industry": None,
            "description": "Updated description",
        },
    )

    assert updated["record_version"] == 4
    assert updated["canonical_name"] == "New Name"
    assert updated["industry"] == "Software"
    assert updated["canonical_payload"]["description"] == "Updated description"
    assert updated["canonical_payload"]["industry"] == "Software"


def test_upsert_company_entity_increments_record_version(monkeypatch: pytest.MonkeyPatch):
    existing = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "company_id": "33333333-3333-3333-3333-333333333333",
        "record_version": 7,
        "canonical_payload": {},
    }
    client = _ClientStub()

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: existing)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    updated = entity_state.upsert_company_entity(
        org_id=existing["org_id"],
        company_id=existing["company_id"],
        entity_id=existing["entity_id"],
        canonical_fields={},
    )

    assert updated["record_version"] == 8


def test_upsert_company_entity_rejects_lower_record_version(monkeypatch: pytest.MonkeyPatch):
    existing = {
        "org_id": "11111111-1111-1111-1111-111111111111",
        "entity_id": "22222222-2222-2222-2222-222222222222",
        "company_id": "33333333-3333-3333-3333-333333333333",
        "record_version": 5,
        "canonical_payload": {},
    }
    client = _ClientStub()

    monkeypatch.setattr(entity_state, "_load_company_by_id", lambda *_: existing)
    monkeypatch.setattr(entity_state, "_lookup_company_by_natural_key", lambda *_: None)
    monkeypatch.setattr(entity_state, "get_supabase_client", lambda: client)

    with pytest.raises(entity_state.EntityStateVersionError):
        entity_state.upsert_company_entity(
            org_id=existing["org_id"],
            company_id=existing["company_id"],
            entity_id=existing["entity_id"],
            canonical_fields={"canonical_name": "Nope"},
            incoming_record_version=4,
        )
