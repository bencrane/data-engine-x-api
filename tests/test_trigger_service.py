from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import trigger


class _ResponseStub:
    def __init__(self, body: dict[str, Any]):
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._body


class _AsyncClientStub:
    def __init__(self, recorder: list[dict[str, Any]], response_body: dict[str, Any]):
        self._recorder = recorder
        self._response_body = response_body

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, Any]):
        self._recorder.append({"url": url, "headers": headers, "json": json})
        return _ResponseStub(self._response_body)


@pytest.mark.asyncio
async def test_trigger_pipeline_run_targets_pipeline_router(monkeypatch: pytest.MonkeyPatch):
    requests: list[dict[str, Any]] = []

    monkeypatch.setattr(
        trigger,
        "get_settings",
        lambda: SimpleNamespace(
            api_url="https://api.example.com",
            trigger_api_url="https://trigger.example.com",
            trigger_secret_key="trigger-secret",
            internal_api_key="internal-secret",
        ),
    )
    monkeypatch.setattr(
        trigger.httpx,
        "AsyncClient",
        lambda timeout=20.0: _AsyncClientStub(requests, {"id": "trigger-run-1"}),
    )

    trigger_run_id = await trigger.trigger_pipeline_run(
        pipeline_run_id="pipeline-1",
        org_id="org-1",
        company_id="company-1",
    )

    assert trigger_run_id == "trigger-run-1"
    assert len(requests) == 1
    assert requests[0]["url"] == "https://trigger.example.com/api/v1/tasks/pipeline-run-router/trigger"
    assert requests[0]["json"]["payload"]["pipeline_run_id"] == "pipeline-1"
    assert requests[0]["json"]["payload"]["org_id"] == "org-1"
    assert requests[0]["json"]["payload"]["company_id"] == "company-1"
