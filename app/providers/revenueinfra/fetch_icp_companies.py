from __future__ import annotations

from typing import Any

import httpx

from app.providers.revenueinfra._common import (
    _PROVIDER,
    _as_str,
    _configured_base_url,
    now_ms,
    parse_json_or_raw,
    ProviderAdapterResult,
)

_FETCH_ICP_COMPANIES_TIMEOUT_SECONDS = 30.0


async def fetch_icp_companies(
    *,
    base_url: str,
    limit: int | None = None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    url = f"{normalized_base_url.rstrip('/')}/api/admin/temp/companies-for-parallel-icp"
    payload: dict[str, Any] = {"limit": limit} if limit is not None else {}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_FETCH_ICP_COMPANIES_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "fetch_icp_companies",
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
                "action": "fetch_icp_companies",
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
                "action": "fetch_icp_companies",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    data = body.get("data", []) if isinstance(body, dict) else []
    if not isinstance(data, list) or len(data) == 0:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "fetch_icp_companies",
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": {
                "company_count": body.get("count", 0) if isinstance(body, dict) else 0,
                "results": [],
            },
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": "fetch_icp_companies",
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "company_count": body.get("count", 0) if isinstance(body, dict) else 0,
            "results": [
                {
                    "company_name": item.get("company_name"),
                    "domain": item.get("domain"),
                    "company_description": item.get("description"),
                }
                for item in data
                if isinstance(item, dict)
            ],
        },
    }
