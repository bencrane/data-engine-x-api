# app/services/trigger.py — Trigger.dev HTTP integration

from typing import Any

import httpx

from app.config import get_settings


async def trigger_pipeline_run(
    *,
    pipeline_run_id: str,
    org_id: str,
    company_id: str,
) -> str:
    """
    Trigger the run-pipeline task in Trigger.dev and return Trigger run ID.
    """
    settings = get_settings()
    task_id = "run-pipeline"
    if not settings.api_url:
        raise RuntimeError("DATA_ENGINE_API_URL must be configured")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            f"{settings.trigger_api_url}/api/v1/tasks/{task_id}/trigger",
            headers={
                "Authorization": f"Bearer {settings.trigger_secret_key}",
                "Content-Type": "application/json",
            },
            json={
                "payload": {
                    "pipeline_run_id": pipeline_run_id,
                    "org_id": org_id,
                    "company_id": company_id,
                    "api_url": settings.api_url,
                    "internal_api_key": settings.internal_api_key,
                }
            },
        )
        response.raise_for_status()
        body: dict[str, Any] = response.json()
        run_id = body.get("id")
        if not run_id:
            raise RuntimeError("Trigger.dev response missing run id")
        return run_id
