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

_LOOKUP_CHAMPIONS_TIMEOUT_SECONDS = 30.0


def _normalize_champion_item(
    value: Any,
    *,
    include_testimonial: bool,
) -> dict[str, str | None] | None:
    if not isinstance(value, dict):
        return None

    champion: dict[str, str | None] = {
        "full_name": _as_str(value.get("full_name")),
        "job_title": _as_str(value.get("job_title")),
        "company_name": _as_str(value.get("company_name")),
        "company_domain": _as_str(value.get("company_domain")),
        "company_linkedin_url": _as_str(value.get("company_linkedin_url")),
        "case_study_url": _as_str(value.get("case_study_url")),
    }
    if include_testimonial:
        champion["testimonial"] = _as_str(value.get("testimonial"))
    return champion


def _normalize_champions(
    value: Any,
    *,
    include_testimonial: bool,
) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in value:
        parsed = _normalize_champion_item(item, include_testimonial=include_testimonial)
        if parsed is None:
            continue
        normalized.append(parsed)
    return normalized


async def _lookup(
    *,
    base_url: str,
    domain: str,
    endpoint: str,
    action: str,
    include_testimonial: bool,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)

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

    url = f"{normalized_base_url.rstrip('/')}{endpoint}"
    payload: dict[str, Any] = {"domain": normalized_domain}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_LOOKUP_CHAMPIONS_TIMEOUT_SECONDS) as client:
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

    champions = _normalize_champions(
        body.get("champions") if isinstance(body, dict) else None,
        include_testimonial=include_testimonial,
    )
    champion_count = len(champions)
    if not champions:
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
                "champions": [],
                "champion_count": 0,
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
            "champions": champions,
            "champion_count": champion_count,
        },
    }


async def lookup_champions(*, base_url: str, domain: str) -> ProviderAdapterResult:
    return await _lookup(
        base_url=base_url,
        domain=domain,
        endpoint="/run/companies/db/case-study-champions/lookup",
        action="lookup_champions",
        include_testimonial=False,
    )


async def lookup_champion_testimonials(
    *,
    base_url: str,
    domain: str,
) -> ProviderAdapterResult:
    return await _lookup(
        base_url=base_url,
        domain=domain,
        endpoint="/run/companies/db/case-study-champions-detailed/lookup",
        action="lookup_champion_testimonials",
        include_testimonial=True,
    )
