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

_LOOKUP_COMPANY_BY_NAME_TIMEOUT_SECONDS = 30.0


async def lookup_company_by_name(
    *,
    base_url: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_company_name = _as_str(company_name)
    action = "lookup_company_by_name"

    if not normalized_company_name:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/run/lookup-company-by-name"
    payload: dict[str, Any] = {"company_name": normalized_company_name}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_LOOKUP_COMPANY_BY_NAME_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
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
                "action": action,
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
                "action": action,
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    found = bool(body.get("found")) if isinstance(body, dict) else False
    if not found:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": action,
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "company_domain": body.get("domain") if isinstance(body, dict) else None,
            "company_linkedin_url": body.get("linkedin_url") if isinstance(body, dict) else None,
            "match_type": body.get("match_type") if isinstance(body, dict) else None,
            "matched_name": body.get("matched_name") if isinstance(body, dict) else None,
            "source_provider": "revenueinfra",
        },
    }
