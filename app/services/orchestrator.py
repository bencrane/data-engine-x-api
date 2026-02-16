# app/services/orchestrator.py — Trigger.dev task trigger/management

from typing import Any

import httpx

from app.config import get_settings


async def trigger_pipeline(
    submission_id: str,
    org_id: str,
    data: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    callback_url: str | None = None,
) -> str:
    """
    Trigger the pipeline task in Trigger.dev.
    Returns the run ID.
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.trigger_api_url}/api/v1/tasks/run-pipeline/trigger",
            headers={
                "Authorization": f"Bearer {settings.trigger_secret_key}",
                "Content-Type": "application/json",
            },
            json={
                "payload": {
                    "submissionId": submission_id,
                    "orgId": org_id,
                    "data": data,
                    "steps": steps,
                    "callbackUrl": callback_url,
                },
            },
        )
        response.raise_for_status()
        result = response.json()
        return result["id"]


async def get_run_status(run_id: str) -> dict:
    """Get the status of a Trigger.dev run."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.trigger_api_url}/api/v1/runs/{run_id}",
            headers={
                "Authorization": f"Bearer {settings.trigger_secret_key}",
            },
        )
        response.raise_for_status()
        return response.json()


async def cancel_run(run_id: str) -> None:
    """Cancel a running Trigger.dev task."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.trigger_api_url}/api/v1/runs/{run_id}/cancel",
            headers={
                "Authorization": f"Bearer {settings.trigger_secret_key}",
            },
        )
        response.raise_for_status()
