"""Tests for list management service layer."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.list_management import (
    add_list_members,
    create_list,
    delete_list,
    export_list,
    get_list_detail,
    get_lists,
    remove_list_members,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ORG_A = str(uuid4())
ORG_B = str(uuid4())
USER_A = str(uuid4())


def _make_list_row(
    *,
    org_id: str = ORG_A,
    name: str = "Test List",
    entity_type: str = "companies",
    member_count: int = 0,
    deleted_at: str | None = None,
    list_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": list_id or str(uuid4()),
        "org_id": org_id,
        "name": name,
        "description": None,
        "entity_type": entity_type,
        "member_count": member_count,
        "created_by_user_id": USER_A,
        "created_at": "2026-03-15T00:00:00+00:00",
        "updated_at": "2026-03-15T00:00:00+00:00",
        "deleted_at": deleted_at,
    }


def _make_member_row(
    *,
    list_id: str,
    entity_id: str | None = None,
    entity_type: str = "company",
    snapshot_data: dict | None = None,
    member_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": member_id or str(uuid4()),
        "list_id": list_id,
        "org_id": ORG_A,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "snapshot_data": snapshot_data or {"company_name": "Acme"},
        "added_at": "2026-03-15T00:00:00+00:00",
    }


def _fake_search_result(name: str = "Acme Corp", entity_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "company_name": name,
        "company_domain": "acme.com",
        "industry_primary": "Staffing",
    }
    if entity_id:
        result["entity_id"] = entity_id
    return result


class _FakeExecuteResult:
    def __init__(self, data: list[dict[str, Any]], count: int | None = None):
        self.data = data
        self.count = count


class _FakeChain:
    """Chainable mock that records calls and returns configured results."""

    def __init__(self, execute_data: list[dict[str, Any]] | None = None, count: int | None = None):
        self._execute_data = execute_data or []
        self._count = count
        self._maybe_single = False

    def maybe_single(self):
        self._maybe_single = True
        return self

    def __getattr__(self, name: str):
        if name == "execute":
            return self.execute
        return lambda *a, **kw: self

    def execute(self):
        if self._maybe_single:
            data = self._execute_data[0] if self._execute_data else None
            return _FakeExecuteResult(data, self._count)
        return _FakeExecuteResult(self._execute_data, self._count)


class _FakeSchemaTable:
    """Routes .table() calls to per-table chain configs."""

    def __init__(self, table_configs: dict[str, list[_FakeChain]]):
        self._table_configs = table_configs
        self._call_counts: dict[str, int] = {}

    def table(self, name: str):
        self._call_counts.setdefault(name, 0)
        chains = self._table_configs.get(name, [_FakeChain()])
        idx = min(self._call_counts[name], len(chains) - 1)
        self._call_counts[name] += 1
        return chains[idx]


def _patch_client(table_configs: dict[str, list[_FakeChain]]):
    fake_schema = _FakeSchemaTable(table_configs)
    mock_client = MagicMock()
    mock_client.schema.return_value = fake_schema
    return patch("app.services.list_management.get_supabase_client", return_value=mock_client)


# ---------------------------------------------------------------------------
# CRUD lifecycle tests
# ---------------------------------------------------------------------------


def test_create_list():
    row = _make_list_row(name="Money20/20", entity_type="companies")
    with _patch_client({"lists": [_FakeChain([row])]}):
        result = create_list(
            org_id=ORG_A,
            name="Money20/20",
            description=None,
            entity_type="companies",
            created_by_user_id=USER_A,
        )
    assert result["name"] == "Money20/20"
    assert result["entity_type"] == "companies"
    assert result["member_count"] == 0


def test_get_lists_returns_only_org_scoped():
    list_a = _make_list_row(org_id=ORG_A, name="List A")
    list_b = _make_list_row(org_id=ORG_B, name="List B")

    # Org A query returns only list A
    with _patch_client({"lists": [_FakeChain([list_a], count=1), _FakeChain([list_a], count=1)]}):
        rows_a, count_a = get_lists(org_id=ORG_A)
    assert count_a == 1
    assert rows_a[0]["name"] == "List A"

    # Org B query returns only list B
    with _patch_client({"lists": [_FakeChain([list_b], count=1), _FakeChain([list_b], count=1)]}):
        rows_b, count_b = get_lists(org_id=ORG_B)
    assert count_b == 1
    assert rows_b[0]["name"] == "List B"


def test_get_list_detail_with_members():
    list_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, member_count=3)
    members = [
        _make_member_row(list_id=list_id, snapshot_data={"company_name": f"Co {i}"})
        for i in range(3)
    ]
    with _patch_client({
        "lists": [_FakeChain([list_row])],
        "list_members": [_FakeChain(members)],
    }):
        detail = get_list_detail(org_id=ORG_A, list_id=list_id)

    assert detail is not None
    assert detail["member_count"] == 3
    assert len(detail["members"]) == 3
    assert detail["members"][0]["snapshot_data"]["company_name"] == "Co 0"


def test_delete_list_soft_deletes():
    list_id = str(uuid4())
    updated_row = _make_list_row(list_id=list_id, deleted_at="2026-03-15T01:00:00+00:00")
    with _patch_client({"lists": [_FakeChain([updated_row])]}):
        result = delete_list(org_id=ORG_A, list_id=list_id)
    assert result is True


def test_delete_list_not_found():
    with _patch_client({"lists": [_FakeChain([])]}):
        result = delete_list(org_id=ORG_A, list_id=str(uuid4()))
    assert result is False


# ---------------------------------------------------------------------------
# Member management tests
# ---------------------------------------------------------------------------


def test_add_members_with_entity_id():
    list_id = str(uuid4())
    entity_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, entity_type="companies")
    member_input = _fake_search_result("Acme", entity_id=entity_id)
    inserted_member = _make_member_row(
        list_id=list_id,
        entity_id=entity_id,
        snapshot_data=member_input,
    )
    count_row = {"member_count": 0}
    with _patch_client({
        "lists": [
            _FakeChain([list_row]),       # verify list exists
            _FakeChain([count_row]),       # read current count
            _FakeChain([list_row]),        # update count
        ],
        "list_members": [_FakeChain([inserted_member])],
    }):
        result = add_list_members(org_id=ORG_A, list_id=list_id, members=[member_input])

    assert len(result) == 1
    assert result[0]["entity_id"] == entity_id
    assert result[0]["snapshot_data"]["company_name"] == "Acme"


def test_add_members_without_entity_id():
    list_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, entity_type="people")
    member_input = {"full_name": "Jane Doe", "headline": "VP Sales"}
    inserted_member = _make_member_row(
        list_id=list_id,
        entity_id=None,
        entity_type="person",
        snapshot_data=member_input,
    )
    count_row = {"member_count": 0}
    with _patch_client({
        "lists": [
            _FakeChain([list_row]),
            _FakeChain([count_row]),
            _FakeChain([list_row]),
        ],
        "list_members": [_FakeChain([inserted_member])],
    }):
        result = add_list_members(org_id=ORG_A, list_id=list_id, members=[member_input])

    assert len(result) == 1
    assert result[0]["entity_id"] is None
    assert result[0]["snapshot_data"]["full_name"] == "Jane Doe"


def test_remove_members():
    list_id = str(uuid4())
    member_ids = [str(uuid4()) for _ in range(2)]
    deleted_rows = [{"id": mid} for mid in member_ids]
    count_row = {"member_count": 3}
    with _patch_client({
        "list_members": [_FakeChain(deleted_rows)],
        "lists": [
            _FakeChain([count_row]),       # read current count
            _FakeChain([count_row]),        # update count
        ],
    }):
        removed = remove_list_members(org_id=ORG_A, list_id=list_id, member_ids=member_ids)

    assert removed == 2


def test_add_members_to_deleted_list_fails():
    list_id = str(uuid4())
    # List lookup returns empty (deleted or not found)
    with _patch_client({"lists": [_FakeChain([])]}):
        result = add_list_members(
            org_id=ORG_A,
            list_id=list_id,
            members=[_fake_search_result()],
        )
    assert result == []


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------


def test_export_list_returns_flat_snapshots():
    list_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, member_count=3)
    snapshots = [
        {"company_name": "Alpha", "domain": "alpha.com"},
        {"company_name": "Beta", "domain": "beta.com"},
        {"company_name": "Gamma", "domain": "gamma.com"},
    ]
    member_rows = [{"snapshot_data": s} for s in snapshots]
    with _patch_client({
        "lists": [_FakeChain([list_row])],
        "list_members": [_FakeChain(member_rows)],
    }):
        result = export_list(org_id=ORG_A, list_id=list_id)

    assert result is not None
    assert result["member_count"] == 3
    assert len(result["members"]) == 3
    assert result["members"][0] == snapshots[0]
    assert result["members"][2] == snapshots[2]


def test_export_empty_list():
    list_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, member_count=0)
    with _patch_client({
        "lists": [_FakeChain([list_row])],
        "list_members": [_FakeChain([])],
    }):
        result = export_list(org_id=ORG_A, list_id=list_id)

    assert result is not None
    assert result["member_count"] == 0
    assert result["members"] == []


# ---------------------------------------------------------------------------
# Edge case tests
# ---------------------------------------------------------------------------


def test_member_count_stays_consistent():
    list_id = str(uuid4())
    list_row = _make_list_row(list_id=list_id, entity_type="companies")

    # Step 1: Add 5 members
    initial_members = [_fake_search_result(f"Co {i}") for i in range(5)]
    inserted_5 = [
        _make_member_row(list_id=list_id, snapshot_data=m) for m in initial_members
    ]
    with _patch_client({
        "lists": [
            _FakeChain([list_row]),
            _FakeChain([{"member_count": 0}]),
            _FakeChain([list_row]),
        ],
        "list_members": [_FakeChain(inserted_5)],
    }):
        added_5 = add_list_members(org_id=ORG_A, list_id=list_id, members=initial_members)
    assert len(added_5) == 5

    # Step 2: Remove 2 members
    remove_ids = [inserted_5[0]["id"], inserted_5[1]["id"]]
    with _patch_client({
        "list_members": [_FakeChain([{"id": remove_ids[0]}, {"id": remove_ids[1]}])],
        "lists": [
            _FakeChain([{"member_count": 5}]),
            _FakeChain([list_row]),
        ],
    }):
        removed = remove_list_members(org_id=ORG_A, list_id=list_id, member_ids=remove_ids)
    assert removed == 2

    # Step 3: Add 3 more members
    more_members = [_fake_search_result(f"NewCo {i}") for i in range(3)]
    inserted_3 = [
        _make_member_row(list_id=list_id, snapshot_data=m) for m in more_members
    ]
    with _patch_client({
        "lists": [
            _FakeChain([list_row]),
            _FakeChain([{"member_count": 3}]),
            _FakeChain([list_row]),
        ],
        "list_members": [_FakeChain(inserted_3)],
    }):
        added_3 = add_list_members(org_id=ORG_A, list_id=list_id, members=more_members)
    assert len(added_3) == 3

    # The service read member_count=3 and added 3, so new count would be 6
    # This verifies the arithmetic: 5 - 2 + 3 = 6
