# app/services/orchestrator.py — Prefect flow trigger/management

import httpx

from app.config import get_settings


async def trigger_pipeline(submission_id: str) -> str:
    """
    Trigger a Prefect flow run for the given submission.
    Returns the flow run ID.
    """
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.prefect_api_url}/deployments/data-engine-x/pipeline-runner/create_flow_run",
            headers={"Authorization": f"Bearer {settings.prefect_api_key}"},
            json={
                "parameters": {"submission_id": submission_id},
            },
        )
        response.raise_for_status()
        data = response.json()
        return data["id"]


async def get_flow_run_status(flow_run_id: str) -> dict:
    """Get the status of a Prefect flow run."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{settings.prefect_api_url}/flow_runs/{flow_run_id}",
            headers={"Authorization": f"Bearer {settings.prefect_api_key}"},
        )
        response.raise_for_status()
        return response.json()


async def cancel_flow_run(flow_run_id: str) -> None:
    """Cancel a running Prefect flow."""
    settings = get_settings()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.prefect_api_url}/flow_runs/{flow_run_id}/set_state",
            headers={"Authorization": f"Bearer {settings.prefect_api_key}"},
            json={"state": {"type": "CANCELLED"}},
        )
        response.raise_for_status()
