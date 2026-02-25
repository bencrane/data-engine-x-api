from __future__ import annotations

import json
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_PROVIDER = "modal_anthropic"
_ACTION = "extract_icp_titles"
_ENDPOINT = "https://bencrane--hq-master-data-ingest-extract-icp-titles.modal.run"
_TIMEOUT_SECONDS = 60.0


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_raw_parallel_output(value: dict[str, Any] | str) -> str | None:
    if isinstance(value, dict):
        if not value:
            return None
        return json.dumps(value)
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    return None


async def extract_icp_titles(
    *,
    company_domain: str,
    raw_parallel_output: dict[str, Any] | str,
    raw_parallel_icp_id: str | None = None,
) -> ProviderAdapterResult:
    normalized_company_domain = _as_str(company_domain)
    normalized_raw_parallel_output = _normalize_raw_parallel_output(raw_parallel_output)
    normalized_raw_parallel_icp_id = _as_str(raw_parallel_icp_id)

    if not normalized_company_domain or not normalized_raw_parallel_output:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload: dict[str, Any] = {
        "company_domain": normalized_company_domain,
        "raw_parallel_output": normalized_raw_parallel_output,
        "raw_parallel_icp_id": normalized_raw_parallel_icp_id,
    }
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_ENDPOINT, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "failed",
                "error": "timeout",
                "duration_ms": now_ms() - start_ms,
            },
            "mapped": None,
        }
    except httpx.HTTPError as exc:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "failed",
                "error": f"http_error:{exc.__class__.__name__}",
                "duration_ms": now_ms() - start_ms,
            },
            "mapped": None,
        }

    duration_ms = now_ms() - start_ms
    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    if not isinstance(body, dict):
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    if not bool(body.get("success")):
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": _ACTION,
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "error": _as_str(body.get("error")) or "provider_returned_failure",
                "raw_response": body,
            },
            "mapped": None,
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": _ACTION,
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "company_domain": body.get("company_domain"),
            "company_name": body.get("company_name"),
            "titles": body.get("titles", []),
            "title_count": body.get("title_count", 0),
            "usage": body.get("usage"),
        },
    }
