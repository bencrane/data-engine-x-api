from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def deep_find_first_str(data: Any, keys: set[str]) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and isinstance(value, str) and value.strip():
                return value.strip()
            nested = deep_find_first_str(value, keys)
            if nested:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = deep_find_first_str(item, keys)
            if nested:
                return nested
    return None


async def findability_email(
    *,
    api_key: str | None,
    full_name: str,
    company: str,
    processor: str,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "parallel",
                "action": "findability_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    task_input = {"full_name": full_name, "company": company}
    payload = {
        "input": json.dumps(task_input),
        "processor": processor,
        "task_spec": {
            "input_schema": {
                "type": "json",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string", "description": "Full name of the person"},
                        "company": {"type": "string", "description": "Company where the person works"},
                    },
                },
            },
            "output_schema": {
                "type": "json",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "Work email address"},
                        "linkedin_url": {"type": "string", "description": "LinkedIn profile URL"},
                    },
                },
            },
        },
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.parallel.ai/v1/tasks/runs",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "parallel",
                "action": "findability_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    email = deep_find_first_str(body, {"email"})
    return {
        "attempt": {
            "provider": "parallel",
            "action": "findability_email",
            "status": "found" if email else "not_found",
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"email": email},
    }
