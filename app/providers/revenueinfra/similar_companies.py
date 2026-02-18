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

_SIMILAR_COMPANIES_TIMEOUT_SECONDS = 30.0


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _normalize_similar_company_item(
    value: Any,
) -> dict[str, str | float | None] | None:
    if not isinstance(value, dict):
        return None
    return {
        "company_name": _as_str(value.get("company_name")),
        "company_domain": _as_str(value.get("company_domain")),
        "company_linkedin_url": _as_str(value.get("company_linkedin_url")),
        "similarity_score": _as_float(value.get("similarity_score")),
    }


def _normalize_similar_companies(
    value: Any,
) -> list[dict[str, str | float | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | float | None]] = []
    for item in value:
        parsed = _normalize_similar_company_item(item)
        if parsed is None:
            continue
        normalized.append(parsed)
    return normalized


async def find_similar_companies(
    *,
    base_url: str,
    domain: str,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)
    action = "find_similar_companies"

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

    url = (
        f"{normalized_base_url.rstrip('/')}"
        "/run/companies/db/similar-companies/list"
    )
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(
            timeout=_SIMILAR_COMPANIES_TIMEOUT_SECONDS
        ) as client:
            response = await client.post(url, json={"domain": normalized_domain})
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

    similar_companies = _normalize_similar_companies(
        body.get("similar_companies") if isinstance(body, dict) else None
    )
    similar_count = (
        body.get("similar_count")
        if isinstance(body, dict) and isinstance(body.get("similar_count"), int)
        else len(similar_companies)
    )

    if not similar_companies:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": {"similar_companies": [], "similar_count": 0},
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
            "similar_companies": similar_companies,
            "similar_count": similar_count,
        },
    }
