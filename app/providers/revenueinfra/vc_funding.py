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

_CHECK_VC_FUNDING_TIMEOUT_SECONDS = 30.0


def _normalize_vc_item(value: Any) -> dict[str, str | None] | None:
    if not isinstance(value, dict):
        return None
    vc_name = _as_str(value.get("vc_name"))
    if not vc_name:
        return None
    return {
        "vc_name": vc_name,
        "vc_domain": _as_str(value.get("vc_domain")),
    }


def _normalize_vcs(value: Any) -> list[dict[str, str | None]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str | None]] = []
    for item in value:
        parsed = _normalize_vc_item(item)
        if parsed is None:
            continue
        normalized.append(parsed)
    return normalized


async def check_vc_funding(*, base_url: str, domain: str) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)
    action = "check_vc_funding"

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
        "/run/companies/db/has-raised-vc-status/check"
    )
    payload: dict[str, Any] = {"domain": normalized_domain}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_CHECK_VC_FUNDING_TIMEOUT_SECONDS) as client:
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

    has_raised_vc = bool(body.get("has_raised_vc")) if isinstance(body, dict) else False
    vc_names_raw = body.get("vc_names") if isinstance(body, dict) else None
    vc_names: list[str] = []
    if isinstance(vc_names_raw, list):
        for item in vc_names_raw:
            vc_name = _as_str(item)
            if vc_name:
                vc_names.append(vc_name)
    vcs = _normalize_vcs(body.get("vcs") if isinstance(body, dict) else None)
    vc_count = len(vc_names)
    if len(vcs) > vc_count:
        vc_count = len(vcs)

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
            "has_raised_vc": has_raised_vc,
            "vc_count": vc_count,
            "vc_names": vc_names,
            "vcs": vcs,
            "founded_date": _as_str(body.get("founded_date")) if isinstance(body, dict) else None,
        },
    }
