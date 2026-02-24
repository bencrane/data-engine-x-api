from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import uuid

import pytest

from app.services import entity_relationships


class _UpsertQuery:
    def __init__(self, table: "_EntityRelationshipsTable", payload: dict):
        self._table = table
        self._payload = payload

    def execute(self):
        key = (
            self._payload["org_id"],
            self._payload["source_identifier"],
            self._payload["relationship"],
            self._payload["target_identifier"],
        )
        existing_index = None
        for idx, row in enumerate(self._table.rows):
            row_key = (
                row["org_id"],
                row["source_identifier"],
                row["relationship"],
                row["target_identifier"],
            )
            if row_key == key:
                existing_index = idx
                break

        if existing_index is None:
            row = deepcopy(self._payload)
            row["id"] = row.get("id") or str(uuid.uuid4())
            row["created_at"] = row.get("created_at") or entity_relationships._utc_now_iso()
            row.setdefault("metadata", {})
            self._table.rows.append(row)
            return SimpleNamespace(data=[deepcopy(row)])

        updated = deepcopy(self._table.rows[existing_index])
        updated.update(deepcopy(self._payload))
        updated.setdefault("metadata", {})
        self._table.rows[existing_index] = updated
        return SimpleNamespace(data=[deepcopy(updated)])


class _UpdateQuery:
    def __init__(self, table: "_EntityRelationshipsTable", payload: dict):
        self._table = table
        self._payload = payload
        self._filters: list[tuple[str, object]] = []

    def eq(self, key: str, value: object):
        self._filters.append((key, value))
        return self

    def execute(self):
        updated_rows: list[dict] = []
        for row in self._table.rows:
            if all(row.get(key) == value for key, value in self._filters):
                row.update(deepcopy(self._payload))
                updated_rows.append(deepcopy(row))
        return SimpleNamespace(data=updated_rows)


class _SelectQuery:
    def __init__(self, table: "_EntityRelationshipsTable"):
        self._table = table
        self._eq_filters: list[tuple[str, object]] = []
        self._is_null_filters: list[str] = []
        self._order_key: str | None = None
        self._order_desc = False
        self._start = 0
        self._end: int | None = None

    def eq(self, key: str, value: object):
        self._eq_filters.append((key, value))
        return self

    def is_(self, key: str, value: object):
        if value == "null":
            self._is_null_filters.append(key)
        return self

    def order(self, key: str, desc: bool = False):
        self._order_key = key
        self._order_desc = desc
        return self

    def range(self, start: int, end: int):
        self._start = start
        self._end = end
        return self

    def execute(self):
        filtered = []
        for row in self._table.rows:
            if not all(row.get(key) == value for key, value in self._eq_filters):
                continue
            if not all(row.get(key) is None for key in self._is_null_filters):
                continue
            filtered.append(deepcopy(row))

        if self._order_key:
            filtered = sorted(
                filtered,
                key=lambda row: row.get(self._order_key) or "",
                reverse=self._order_desc,
            )

        if self._end is None:
            paged = filtered[self._start :]
        else:
            paged = filtered[self._start : self._end + 1]

        return SimpleNamespace(data=paged)


class _EntityRelationshipsTable:
    def __init__(self):
        self.rows: list[dict] = []

    def upsert(self, payload: dict, on_conflict: str):  # noqa: ARG002
        return _UpsertQuery(self, payload)

    def update(self, payload: dict):
        return _UpdateQuery(self, payload)

    def select(self, _fields: str):
        return _SelectQuery(self)


class _SupabaseStub:
    def __init__(self):
        self.entity_relationships = _EntityRelationshipsTable()

    def table(self, table_name: str):
        if table_name != "entity_relationships":
            raise AssertionError(f"Unexpected table: {table_name}")
        return self.entity_relationships


@pytest.fixture
def supabase_stub(monkeypatch: pytest.MonkeyPatch) -> _SupabaseStub:
    stub = _SupabaseStub()
    monkeypatch.setattr(entity_relationships, "get_supabase_client", lambda: stub)
    return stub


def test_record_entity_relationship_creates_new(supabase_stub: _SupabaseStub):
    row = entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
        metadata={"source": "theirstack"},
    )

    assert row["org_id"] == "11111111-1111-1111-1111-111111111111"
    assert row["source_identifier"] == "securitypal.com"
    assert row["relationship"] == "has_customer"
    assert row["target_identifier"] == "snap.com"
    assert row["metadata"] == {"source": "theirstack"}
    assert row["valid_as_of"] is not None
    assert row["id"] is not None
    assert len(supabase_stub.entity_relationships.rows) == 1


def test_record_entity_relationship_dedup_updates(supabase_stub: _SupabaseStub):
    first = entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
        metadata={"source": "first"},
    )
    second = entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
        metadata={"source": "second"},
    )

    assert len(supabase_stub.entity_relationships.rows) == 1
    assert second["id"] == first["id"]
    assert second["metadata"] == {"source": "second"}
    assert second["valid_as_of"] != first["valid_as_of"]


def test_record_entity_relationship_normalizes_identifiers(supabase_stub: _SupabaseStub):
    row = entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="https://www.CoreWeave.com/",
        relationship="has_competitor",
        target_entity_type="company",
        target_identifier="HTTPS://WWW.AWS.AMAZON.COM/",
    )

    assert row["source_identifier"] == "coreweave.com"
    assert row["target_identifier"] == "aws.amazon.com"
    assert len(supabase_stub.entity_relationships.rows) == 1


def test_invalidate_entity_relationship(supabase_stub: _SupabaseStub):
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
    )
    invalidated = entity_relationships.invalidate_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_identifier="snap.com",
    )

    assert invalidated is not None
    assert invalidated["invalidated_at"] is not None


def test_invalidate_revalidates_on_re_record(supabase_stub: _SupabaseStub):
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="person",
        source_identifier="https://www.linkedin.com/in/jhiggins/",
        relationship="works_at",
        target_entity_type="company",
        target_identifier="coreweave.com",
    )
    entity_relationships.invalidate_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="linkedin.com/in/jhiggins/",
        relationship="works_at",
        target_identifier="coreweave.com",
    )
    revalidated = entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="person",
        source_identifier="https://linkedin.com/in/jhiggins/",
        relationship="works_at",
        target_entity_type="company",
        target_identifier="https://www.coreweave.com/",
    )

    assert revalidated["source_identifier"] == "linkedin.com/in/jhiggins"
    assert revalidated["target_identifier"] == "coreweave.com"
    assert revalidated["invalidated_at"] is None


def test_query_filters_by_source(supabase_stub: _SupabaseStub):
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
    )
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="coreweave.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="securitypal.com",
    )
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="aws.amazon.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="coreweave.com",
    )

    results = entity_relationships.query_entity_relationships(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="securitypal.com",
    )
    assert len(results) == 1
    assert results[0]["source_identifier"] == "securitypal.com"
    assert results[0]["target_identifier"] == "snap.com"


def test_query_filters_by_relationship_type(supabase_stub: _SupabaseStub):
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="coreweave.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
    )
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="coreweave.com",
        relationship="has_competitor",
        target_entity_type="company",
        target_identifier="aws.amazon.com",
    )

    customers = entity_relationships.query_entity_relationships(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="coreweave.com",
        relationship="has_customer",
    )
    assert len(customers) == 1
    assert customers[0]["relationship"] == "has_customer"
    assert customers[0]["target_identifier"] == "snap.com"


def test_query_excludes_invalidated_by_default(supabase_stub: _SupabaseStub):
    entity_relationships.record_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_entity_type="company",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_entity_type="company",
        target_identifier="snap.com",
    )
    entity_relationships.invalidate_entity_relationship(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="securitypal.com",
        relationship="has_customer",
        target_identifier="snap.com",
    )

    default_results = entity_relationships.query_entity_relationships(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="securitypal.com",
    )
    with_invalidated = entity_relationships.query_entity_relationships(
        org_id="11111111-1111-1111-1111-111111111111",
        source_identifier="securitypal.com",
        include_invalidated=True,
    )

    assert default_results == []
    assert len(with_invalidated) == 1
    assert with_invalidated[0]["invalidated_at"] is not None


def test_batch_record(supabase_stub: _SupabaseStub):
    relationships = [
        {
            "source_entity_type": "company",
            "source_identifier": "securitypal.com",
            "relationship": "has_customer",
            "target_entity_type": "company",
            "target_identifier": "snap.com",
        },
        {
            "source_entity_type": "company",
            "source_identifier": "coreweave.com",
            "relationship": "has_competitor",
            "target_entity_type": "company",
            "target_identifier": "aws.amazon.com",
        },
        {
            "source_entity_type": "person",
            "source_identifier": "linkedin.com/in/jhiggins",
            "relationship": "works_at",
            "target_entity_type": "company",
            "target_identifier": "coreweave.com",
        },
        {
            "source_entity_type": "company",
            "source_identifier": "snap.com",
            "relationship": "has_customer",
            "target_entity_type": "company",
            "target_identifier": "securitypal.com",
        },
        {
            "source_entity_type": "company",
            "source_identifier": "aws.amazon.com",
            "relationship": "has_competitor",
            "target_entity_type": "company",
            "target_identifier": "coreweave.com",
        },
    ]

    rows = entity_relationships.record_entity_relationships_batch(
        org_id="11111111-1111-1111-1111-111111111111",
        relationships=relationships,
    )

    assert len(rows) == 5
    assert len(supabase_stub.entity_relationships.rows) == 5
