from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from app.auth.models import AuthContext, SuperAdminContext
from app.routers import super_admin_api, tenant_blueprints


class _ImmediateResult:
    def __init__(self, data: Any):
        self._data = data

    def execute(self):
        return SimpleNamespace(data=self._data)


class _Query:
    def __init__(self, db: "_SupabaseStub", table_name: str, fields: str | None = None):
        self._db = db
        self._table_name = table_name
        self._fields = fields
        self._filters: list[tuple[str, Any]] = []
        self._limit: int | None = None
        self._single = False

    def eq(self, field: str, value: Any):
        self._filters.append((field, value))
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        rows = [row for row in self._db.tables[self._table_name] if all(row.get(k) == v for k, v in self._filters)]
        if self._limit is not None:
            rows = rows[: self._limit]

        if self._table_name == "blueprints" and self._fields and "blueprint_steps" in self._fields:
            hydrated_rows: list[dict[str, Any]] = []
            for row in rows:
                row_copy = dict(row)
                row_copy["blueprint_steps"] = [
                    dict(step)
                    for step in self._db.tables["blueprint_steps"]
                    if step.get("blueprint_id") == row_copy.get("id")
                ]
                hydrated_rows.append(row_copy)
            rows = hydrated_rows
        else:
            rows = [dict(row) for row in rows]

        if self._single:
            return SimpleNamespace(data=(rows[0] if rows else None))
        return SimpleNamespace(data=rows)


class _Table:
    def __init__(self, db: "_SupabaseStub", table_name: str):
        self._db = db
        self._table_name = table_name

    def insert(self, payload: dict[str, Any] | list[dict[str, Any]]):
        rows = payload if isinstance(payload, list) else [payload]
        inserted: list[dict[str, Any]] = []
        for row in rows:
            stored = dict(row)
            if "id" not in stored:
                stored["id"] = self._db.next_id(self._table_name)
            self._db.tables[self._table_name].append(stored)
            inserted.append(dict(stored))
        return _ImmediateResult(inserted)

    def select(self, fields: str = "*"):
        return _Query(self._db, self._table_name, fields=fields)


class _SupabaseStub:
    def __init__(self):
        self.tables: dict[str, list[dict[str, Any]]] = {
            "blueprints": [],
            "blueprint_steps": [],
        }
        self._counters = {"blueprints": 0, "blueprint_steps": 0}

    def next_id(self, table_name: str) -> str:
        self._counters[table_name] += 1
        return f"{table_name}-{self._counters[table_name]}"

    def table(self, table_name: str):
        if table_name not in self.tables:
            raise AssertionError(f"Unexpected table requested: {table_name}")
        return _Table(self, table_name)


@pytest.mark.asyncio
async def test_tenant_blueprint_create_persists_condition(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    monkeypatch.setattr(tenant_blueprints, "get_supabase_client", lambda: supabase)

    auth = AuthContext(
        user_id="44444444-4444-4444-4444-444444444444",
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        role="org_admin",
        auth_method="jwt",
    )
    payload = tenant_blueprints.BlueprintCreateRequest(
        name="Conditional tenant blueprint",
        description="Tenant condition persistence test",
        steps=[
            tenant_blueprints.BlueprintStepInput(
                position=1,
                operation_id="company.enrich.profile",
            ),
            tenant_blueprints.BlueprintStepInput(
                position=2,
                operation_id="company.derive.pricing_intelligence",
                step_config={"condition": {"field": "pricing_page_url", "op": "exists"}},
            ),
        ],
    )

    response = await tenant_blueprints.create_blueprint(payload, auth)

    assert response.data["blueprint_steps"][1]["step_config"]["condition"] == {
        "field": "pricing_page_url",
        "op": "exists",
    }


@pytest.mark.asyncio
async def test_super_admin_blueprint_create_persists_condition(monkeypatch: pytest.MonkeyPatch):
    supabase = _SupabaseStub()
    monkeypatch.setattr(super_admin_api, "get_supabase_client", lambda: supabase)
    monkeypatch.setattr(super_admin_api, "_org_exists", lambda _org_id: True)

    context = SuperAdminContext(
        super_admin_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        email="admin@example.com",
    )
    payload = super_admin_api.BlueprintCreateRequest(
        org_id="11111111-1111-1111-1111-111111111111",
        name="Conditional admin blueprint",
        description="Super-admin condition persistence test",
        steps=[
            super_admin_api.BlueprintStepInput(
                position=1,
                operation_id="person.search",
                fan_out=True,
            ),
            super_admin_api.BlueprintStepInput(
                position=2,
                operation_id="person.contact.resolve_mobile_phone",
                step_config={
                    "condition": {
                        "any": [
                            {"field": "current_job_title", "op": "icontains", "value": "vp"},
                            {"field": "current_job_title", "op": "icontains", "value": "director"},
                        ]
                    }
                },
            ),
        ],
    )

    response = await super_admin_api.super_admin_create_blueprint(payload, context)

    assert response.data["blueprint_steps"][1]["step_config"]["condition"] == {
        "any": [
            {"field": "current_job_title", "op": "icontains", "value": "vp"},
            {"field": "current_job_title", "op": "icontains", "value": "director"},
        ]
    }
