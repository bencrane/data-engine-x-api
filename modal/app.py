import asyncio
import json
import os
import time
from typing import Any

import httpx
import modal
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

app = modal.App("data-engine-x-micro")

image = modal.Image.debian_slim().pip_install("fastapi", "httpx")
auth_scheme = HTTPBearer(auto_error=False)
parallel_base_url = "https://api.parallel.ai/v1/tasks/runs"
parallel_poll_timeout_seconds = 90
parallel_poll_interval_seconds = 2

parallel_find_company_linkedin_task_spec = {
    "input_schema": {
        "json_schema": {
            "properties": {
                "company_domain": {
                    "description": "The domain of the company to find the LinkedIn URL for",
                    "type": "string",
                }
            },
            "type": "object",
        },
        "type": "json",
    },
    "output_schema": {
        "json_schema": {
            "additionalProperties": False,
            "properties": {
                "linkedin_url": {
                    "description": (
                        "The official LinkedIn profile URL for the company. "
                        "If a LinkedIn profile cannot be found or verified, return null."
                    ),
                    "type": "string",
                }
            },
            "required": ["linkedin_url"],
            "type": "object",
        },
        "type": "json",
    },
}


class CompanyDomainRequest(BaseModel):
    company_domain: str


def _deep_find_first(data: Any, keys: set[str]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys:
                return value
            nested = _deep_find_first(value, keys)
            if nested is not None:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _deep_find_first(item, keys)
            if nested is not None:
                return nested
    return None


def _as_output_dict(raw_output: Any) -> dict[str, Any] | None:
    if isinstance(raw_output, dict):
        return raw_output
    if isinstance(raw_output, str):
        try:
            parsed = json.loads(raw_output)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_parallel_output(response_body: Any) -> dict[str, Any] | None:
    output_candidate = _deep_find_first(response_body, {"output", "result", "data"})
    parsed_output = _as_output_dict(output_candidate)
    if parsed_output is not None:
        return parsed_output
    if isinstance(response_body, dict) and "linkedin_url" in response_body:
        return response_body
    return None


def _extract_run_id(response_body: Any) -> str | None:
    run_id = _deep_find_first(response_body, {"run_id", "id"})
    if isinstance(run_id, str) and run_id.strip():
        return run_id.strip()
    return None


def _extract_status(response_body: Any) -> str | None:
    status_value = _deep_find_first(response_body, {"status", "state"})
    if isinstance(status_value, str):
        return status_value.strip().lower()
    return None


def _extract_error_message(response_body: Any) -> str | None:
    message = _deep_find_first(response_body, {"error", "message", "detail"})
    if isinstance(message, str) and message.strip():
        return message.strip()
    return None


async def run_parallel_task(
    *,
    task_spec: dict[str, Any],
    input_data: dict[str, Any],
    processor: str,
) -> dict[str, Any]:
    api_key = os.environ.get("PARALLEL_API_KEY")
    if not api_key:
        raise RuntimeError("PARALLEL_API_KEY is not configured")

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "input": json.dumps(input_data),
        "processor": processor,
        "task_spec": task_spec,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        create_response = await client.post(parallel_base_url, headers=headers, json=payload)
        create_body: Any
        try:
            create_body = create_response.json()
        except Exception:
            create_body = {"raw_text": create_response.text}

        if create_response.status_code >= 400:
            error_message = _extract_error_message(create_body) or (
                f"Parallel create call failed with HTTP {create_response.status_code}"
            )
            raise RuntimeError(error_message)

        initial_output = _extract_parallel_output(create_body)
        initial_status = _extract_status(create_body)
        if initial_output is not None and initial_status not in {"pending", "running"}:
            return initial_output

        run_id = _extract_run_id(create_body)
        if not run_id:
            raise RuntimeError("Parallel response did not include a run_id for polling")

        deadline = time.monotonic() + parallel_poll_timeout_seconds
        while time.monotonic() < deadline:
            poll_response = await client.get(f"{parallel_base_url}/{run_id}", headers=headers)
            try:
                poll_body = poll_response.json()
            except Exception:
                poll_body = {"raw_text": poll_response.text}

            if poll_response.status_code >= 400:
                error_message = _extract_error_message(poll_body) or (
                    f"Parallel poll failed with HTTP {poll_response.status_code}"
                )
                raise RuntimeError(error_message)

            poll_status = _extract_status(poll_body)
            poll_output = _extract_parallel_output(poll_body)

            if poll_status in {"completed", "complete", "succeeded", "success", "finished"}:
                if poll_output is None:
                    raise RuntimeError("Parallel run completed without output payload")
                return poll_output

            if poll_status in {"failed", "error", "cancelled", "canceled"}:
                error_message = _extract_error_message(poll_body) or "Parallel task failed"
                raise RuntimeError(error_message)

            if poll_output is not None and poll_status not in {"pending", "running"}:
                return poll_output

            await asyncio.sleep(parallel_poll_interval_seconds)

    raise RuntimeError("Parallel task timed out after 90 seconds")


def require_internal_auth(
    credentials: HTTPAuthorizationCredentials | None = Depends(auth_scheme),
) -> None:
    expected_key = os.environ.get("MODAL_INTERNAL_AUTH_KEY")
    if not expected_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MODAL_INTERNAL_AUTH_KEY is not configured",
        )

    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or credentials.credentials != expected_key
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


web_app = FastAPI(
    title="data-engine-x-micro",
    dependencies=[Depends(require_internal_auth)],
)


@web_app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@web_app.post("/company/find-linkedin-url-by-domain")
async def find_linkedin_url_by_domain(payload: CompanyDomainRequest) -> dict[str, Any]:
    company_domain = payload.company_domain.strip()
    if not company_domain:
        return {"success": False, "error": "company_domain is required"}

    try:
        output = await run_parallel_task(
            task_spec=parallel_find_company_linkedin_task_spec,
            input_data={"company_domain": company_domain},
            processor="base",
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    linkedin_url = output.get("linkedin_url") if isinstance(output, dict) else None
    return {"success": True, "data": {"linkedin_url": linkedin_url}}


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("parallel-ai"),
        modal.Secret.from_name("internal-auth"),
    ],
)
@modal.asgi_app()
def fastapi_app() -> FastAPI:
    return web_app
