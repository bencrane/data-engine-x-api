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

_LOOKUP_CUSTOMERS_TIMEOUT_SECONDS = 30.0


def _normalize_customer_item(value: Any) -> dict[str, str | None] | None:
    if not isinstance(value, dict):
        return None
    return {
        "customer_name": _as_str(value.get("customer_name")),
        "customer_domain": _as_str(value.get("customer_domain")),
        "customer_linkedin_url": _as_str(value.get("customer_linkedin_url")),
        "origin_company_name": _as_str(value.get("origin_company_name")),
        "origin_company_domain": _as_str(value.get("origin_company_domain")),
    }


def _normalize_customers(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in value:
        parsed = _normalize_customer_item(item)
        if parsed is None:
            continue
        if not parsed.get("customer_domain"):
            continue
        normalized.append(parsed)
    return normalized


async def lookup_customers(*, base_url: str, domain: str) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)
    action = "lookup_customers"

    if not normalized_domain:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/run/companies/db/company-customers/lookup"
    payload: dict[str, Any] = {"domain": normalized_domain}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_LOOKUP_CUSTOMERS_TIMEOUT_SECONDS) as client:
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
    if not success:
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

    customers = _normalize_customers(body.get("customers") if isinstance(body, dict) else None)
    customer_count = len(customers)
    if not customers:
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
                "customers": [],
                "customer_count": 0,
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
            "customers": customers,
            "customer_count": customer_count,
        },
    }
