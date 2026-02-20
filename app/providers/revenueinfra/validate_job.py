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

_VALIDATE_JOB_TIMEOUT_SECONDS = 30.0


async def validate_job_active(
    *,
    base_url: str,
    api_key: str | None,
    company_domain: str,
    job_title: str,
    company_name: str | None = None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_company_domain = _as_str(company_domain)
    normalized_job_title = _as_str(job_title)
    normalized_company_name = _as_str(company_name)

    if not normalized_company_domain or not normalized_job_title:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "validate_job_active",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/api/ingest/brightdata/validate-job"
    payload: dict[str, Any] = {
        "company_domain": normalized_company_domain,
        "job_title": normalized_job_title,
        "company_name": normalized_company_name,
    }
    headers = {"x-api-key": _as_str(api_key) or ""}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_VALIDATE_JOB_TIMEOUT_SECONDS) as client:
            response = await client.post(url, headers=headers, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "validate_job_active",
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
                "action": "validate_job_active",
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
                "action": "validate_job_active",
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
                "action": "validate_job_active",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": "validate_job_active",
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "validation_result": body.get("validation_result"),
            "confidence": body.get("confidence"),
            "indeed_found": body.get("indeed", {}).get("found"),
            "indeed_match_count": body.get("indeed", {}).get("match_count"),
            "indeed_any_expired": body.get("indeed", {}).get("any_expired"),
            "indeed_matched_by": body.get("indeed", {}).get("matched_by"),
            "linkedin_found": body.get("linkedin", {}).get("found"),
            "linkedin_match_count": body.get("linkedin", {}).get("match_count"),
            "linkedin_matched_by": body.get("linkedin", {}).get("matched_by"),
        },
    }
