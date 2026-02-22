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

_RESOLVE_TIMEOUT_SECONDS = 15.0


async def _resolve_single_field(
    *,
    action: str,
    base_url: str,
    api_key: str | None,
    path: str,
    input_key: str,
    input_value: str | None,
    output_keys: tuple[str, ...],
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_api_key = _as_str(api_key)
    normalized_input_value = _as_str(input_value)

    if not normalized_api_key:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    if not normalized_input_value:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}{path}"
    payload: dict[str, Any] = {input_key: normalized_input_value}
    headers = {"x-api-key": normalized_api_key}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_RESOLVE_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
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

    if not isinstance(body, dict):
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

    resolved = bool(body.get("resolved"))
    mapped = {key: body.get(key) for key in output_keys}
    mapped["resolve_source"] = body.get("source")
    if resolved:
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


async def resolve_domain_from_email(
    *,
    base_url: str,
    api_key: str | None,
    work_email: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_domain_from_email",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-domain-from-email/single",
        input_key="work_email",
        input_value=work_email,
        output_keys=("domain",),
    )


async def resolve_domain_from_linkedin(
    *,
    base_url: str,
    api_key: str | None,
    company_linkedin_url: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_domain_from_linkedin",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-domain-from-linkedin/single",
        input_key="company_linkedin_url",
        input_value=company_linkedin_url,
        output_keys=("domain",),
    )


async def resolve_domain_from_company_name(
    *,
    base_url: str,
    api_key: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_domain_from_company_name",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-company-name/single",
        input_key="company_name",
        input_value=company_name,
        output_keys=("domain", "cleaned_company_name"),
    )


async def resolve_linkedin_from_domain(
    *,
    base_url: str,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_linkedin_from_domain",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-linkedin-from-domain/single",
        input_key="domain",
        input_value=domain,
        output_keys=("company_linkedin_url",),
    )


async def resolve_person_linkedin_from_email(
    *,
    base_url: str,
    api_key: str | None,
    work_email: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_person_linkedin_from_email",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-person-linkedin-from-email/single",
        input_key="work_email",
        input_value=work_email,
        output_keys=("person_linkedin_url",),
    )


async def resolve_company_location_from_domain(
    *,
    base_url: str,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    return await _resolve_single_field(
        action="resolve_company_location_from_domain",
        base_url=base_url,
        api_key=api_key,
        path="/api/workflows/resolve-company-location-from-domain/single",
        input_key="domain",
        input_value=domain,
        output_keys=("company_city", "company_state", "company_country"),
    )
