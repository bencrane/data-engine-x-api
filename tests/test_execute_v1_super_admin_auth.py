from __future__ import annotations

from uuid import UUID
from unittest.mock import AsyncMock

import pytest

from app.auth.models import SuperAdminContext
from app.routers import execute_v1


@pytest.mark.asyncio
async def test_execute_v1_super_admin_requires_org_and_company():
    payload = execute_v1.ExecuteV1Request(
        operation_id="person.search",
        entity_type="person",
        input={"full_name": "Alex Doe"},
    )
    auth = SuperAdminContext(
        super_admin_id=UUID("00000000-0000-0000-0000-000000000000"),
        email="api-key@super-admin",
    )

    response = await execute_v1.execute_v1(payload, auth)

    assert response.status_code == 400
    assert response.body == b'{"error":"org_id is required for super-admin execute"}'


@pytest.mark.asyncio
async def test_execute_v1_super_admin_with_org_and_company_executes(monkeypatch: pytest.MonkeyPatch):
    fake_result = {
        "run_id": "11111111-1111-1111-1111-111111111111",
        "status": "succeeded",
        "output": {"persons": [{"full_name": "Alex Doe"}]},
        "provider_attempts": [],
    }
    execute_person_search = AsyncMock(return_value=fake_result)
    persist_calls: list[dict] = []

    def _persist_operation_execution(**kwargs):
        persist_calls.append(kwargs)

    monkeypatch.setattr(execute_v1, "execute_person_search", execute_person_search)
    monkeypatch.setattr(execute_v1, "persist_operation_execution", _persist_operation_execution)

    payload = execute_v1.ExecuteV1Request(
        operation_id="person.search",
        entity_type="person",
        input={"full_name": "Alex Doe"},
        org_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
    )
    auth = SuperAdminContext(
        super_admin_id=UUID("00000000-0000-0000-0000-000000000000"),
        email="api-key@super-admin",
    )

    response = await execute_v1.execute_v1(payload, auth)

    assert response.data == fake_result
    assert execute_person_search.await_count == 1
    assert len(persist_calls) == 1
    persisted = persist_calls[0]
    assert persisted["auth"].org_id == "11111111-1111-1111-1111-111111111111"
    assert persisted["auth"].company_id == "22222222-2222-2222-2222-222222222222"
    assert persisted["auth"].role == "org_admin"
    assert persisted["auth"].auth_method == "api_token"
