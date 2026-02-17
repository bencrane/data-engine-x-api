from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


async def resolve_email(
    *,
    api_key: str | None,
    first_name: str | None,
    last_name: str | None,
    full_name: str | None,
    domain: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    has_name = bool(
        (first_name and first_name.strip())
        or (last_name and last_name.strip())
        or (full_name and full_name.strip())
    )
    has_company = bool((domain and domain.strip()) or (company_name and company_name.strip()))
    if not has_name or not has_company:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload: dict[str, Any] = {}
    if full_name:
        payload["full_name"] = full_name
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if domain:
        payload["domain"] = domain
    elif company_name:
        payload["company_name"] = company_name

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/email-finder",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    email = _as_str(body.get("email"))
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "resolve_email",
            "status": "found" if email else "not_found",
            "duration_ms": now_ms() - start_ms,
            "provider_status": body.get("status"),
            "raw_response": body,
        },
        "mapped": {"email": email},
    }


async def resolve_mobile_phone(
    *,
    api_key: str | None,
    profile_url: str | None,
    work_email: str | None,
    personal_email: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    payload: dict[str, Any] = {}
    if profile_url:
        payload["profile_url"] = profile_url
    if work_email:
        payload["work_email"] = work_email
    if personal_email:
        payload["personal_email"] = personal_email
    if not payload:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/mobile-finder",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mobile = _as_str(body.get("mobile_number"))
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "resolve_mobile_phone",
            "status": "found" if mobile else "not_found",
            "provider_status": body.get("message"),
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"mobile_phone": mobile},
    }


async def enrich_company(
    *,
    api_key: str | None,
    payload: dict[str, Any],
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "company_enrich",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    clean_payload = {k: v for k, v in payload.items() if v}
    if not clean_payload:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "company_enrich",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/companies/company-search",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=clean_payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "company_enrich",
                "status": "not_found" if res.status_code == 404 else "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    found = bool(_as_str(body.get("companyName")) or body.get("companyId"))
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "provider_status": body.get("message"),
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": body if found else None,
    }
