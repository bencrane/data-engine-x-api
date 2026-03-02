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

_ICP_JOB_TITLES_GEMINI_TIMEOUT_SECONDS = 60.0


async def research_icp_job_titles_gemini(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
    company_description: str | None = None,
) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_company_name = _as_str(company_name)
    normalized_domain = _as_str(domain)
    normalized_company_description = _as_str(company_description)
    action = "research_icp_job_titles_gemini"

    if not normalized_company_name and not normalized_domain:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/run/companies/gemini/icp-job-titles/research"
    payload: dict[str, Any] = {
        "company_name": normalized_company_name,
        "domain": normalized_domain,
        "company_description": normalized_company_description,
    }
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_ICP_JOB_TITLES_GEMINI_TIMEOUT_SECONDS) as client:
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
    mapped = {
        "inferred_product": body.get("inferred_product") if isinstance(body, dict) else None,
        "buyer_persona": body.get("buyer_persona") if isinstance(body, dict) else None,
        "titles": body.get("titles") if isinstance(body, dict) else None,
        "champion_titles": body.get("champion_titles") if isinstance(body, dict) else None,
        "evaluator_titles": body.get("evaluator_titles") if isinstance(body, dict) else None,
        "decision_maker_titles": body.get("decision_maker_titles") if isinstance(body, dict) else None,
        "source_provider": "revenueinfra",
    }

    if not success:
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
