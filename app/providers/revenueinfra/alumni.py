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

_LOOKUP_ALUMNI_TIMEOUT_SECONDS = 30.0


def _normalize_alumni_item(value: Any) -> dict[str, str | None] | None:
    if not isinstance(value, dict):
        return None

    return {
        "full_name": _as_str(value.get("full_name")),
        "linkedin_url": _as_str(value.get("linkedin_url")),
        "current_company_name": _as_str(value.get("current_company_name")),
        "current_company_domain": _as_str(value.get("current_company_domain")),
        "current_company_linkedin_url": _as_str(value.get("current_company_linkedin_url")),
        "current_job_title": _as_str(value.get("current_job_title")),
        "past_company_name": _as_str(value.get("past_company_name")),
        "past_company_domain": _as_str(value.get("past_company_domain")),
        "past_job_title": _as_str(value.get("past_job_title")),
    }


def _normalize_alumni(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in value:
        parsed = _normalize_alumni_item(item)
        if parsed is None:
            continue
        normalized.append(parsed)
    return normalized


async def lookup_alumni(*, base_url: str, domain: str) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)

    if not normalized_domain:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "lookup_alumni",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/run/companies/db/alumni/lookup"
    payload: dict[str, Any] = {"past_company_domain": normalized_domain}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_LOOKUP_ALUMNI_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "lookup_alumni",
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
                "action": "lookup_alumni",
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
                "action": "lookup_alumni",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    success = bool(body.get("success")) if isinstance(body, dict) else False
    if not success:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "lookup_alumni",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    alumni = _normalize_alumni(body.get("alumni") if isinstance(body, dict) else None)
    alumni_count = len(alumni)
    if not alumni:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "lookup_alumni",
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": {
                "alumni": [],
                "alumni_count": 0,
            },
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": "lookup_alumni",
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "alumni": alumni,
            "alumni_count": alumni_count,
        },
    }
