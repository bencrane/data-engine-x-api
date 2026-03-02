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

_SALESNAV_URL_TIMEOUT_SECONDS = 60.0


async def build_salesnav_url(
    *,
    base_url: str | None,
    org_id: str | None,
    company_name: str | None,
    titles: list[str] | None = None,
    excluded_seniority: list[str] | None = None,
    regions: list[str] | None = None,
    company_hq_regions: list[str] | None = None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_org_id = _as_str(org_id)
    normalized_company_name = _as_str(company_name)
    action = "build_salesnav_url"

    if not normalized_org_id or not normalized_company_name:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload: dict[str, Any] = {
        "orgId": normalized_org_id,
        "companyName": normalized_company_name,
    }
    if titles is not None:
        payload["titles"] = titles
    if excluded_seniority is not None:
        payload["excludedSeniority"] = excluded_seniority
    if regions is not None:
        payload["regions"] = regions
    if company_hq_regions is not None:
        payload["companyHQRegions"] = company_hq_regions

    url = f"{normalized_base_url.rstrip('/')}/run/tools/claude/salesnav-url/build"
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_SALESNAV_URL_TIMEOUT_SECONDS) as client:
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

    success = bool(body.get("success")) if isinstance(body, dict) else False
    salesnav_url = _as_str(body.get("url")) if isinstance(body, dict) else None
    mapped = {
        "salesnav_url": salesnav_url,
        "source_provider": "revenueinfra",
    }

    if not success or not salesnav_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": mapped,
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
        "mapped": mapped,
    }
