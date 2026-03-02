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

_INFER_LINKEDIN_URL_TIMEOUT_SECONDS = 30.0


async def infer_linkedin_url(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_company_name = _as_str(company_name)
    normalized_domain = _as_str(domain)
    action = "infer_linkedin_url"

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

    url = f"{normalized_base_url.rstrip('/')}/run/companies/gemini/linkedin-url/get"
    payload: dict[str, Any] = {
        "company_name": normalized_company_name,
        "domain": normalized_domain,
    }
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_INFER_LINKEDIN_URL_TIMEOUT_SECONDS) as client:
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
    linkedin_url = _as_str(body.get("linkedin_url")) if isinstance(body, dict) else None
    if not success or not linkedin_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": {
                "company_linkedin_url": None,
                "source_provider": "revenueinfra",
            },
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
            "company_linkedin_url": linkedin_url,
            "source_provider": "revenueinfra",
        },
    }
