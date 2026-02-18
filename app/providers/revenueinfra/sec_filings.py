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

_FETCH_TIMEOUT_SECONDS = 60.0
_ANALYZE_TIMEOUT_SECONDS = 300.0

_ANALYZE_10K_URL = "https://bencrane--hq-master-data-ingest-analyze-sec-10k.modal.run"
_ANALYZE_10Q_URL = "https://bencrane--hq-master-data-ingest-analyze-sec-10q.modal.run"
_ANALYZE_8K_EXECUTIVE_URL = (
    "https://bencrane--hq-master-data-ingest-analyze-sec-8k-executive.modal.run"
)


def _filing_info(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {
        "filing_date": _as_str(value.get("filing_date")),
        "report_date": _as_str(value.get("report_date")),
        "accession_number": _as_str(value.get("accession_number")),
        "document_url": _as_str(value.get("document_url")),
        "items": value.get("items") if isinstance(value.get("items"), list) else None,
    }


def _filing_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    mapped: list[dict[str, Any]] = []
    for raw_item in value:
        parsed = _filing_info(raw_item)
        if parsed is None:
            continue
        mapped.append(parsed)
    return mapped


def _analysis_result(
    *,
    action: str,
    body: dict[str, Any],
    response: httpx.Response,
    duration_ms: int,
    document_url: str,
    domain: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
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
            "filing_type": _as_str(body.get("filing_type")),
            "document_url": document_url,
            "domain": domain,
            "company_name": company_name,
            "analysis": _as_str(body.get("analysis")),
        },
    }


async def fetch_sec_filings(*, base_url: str, domain: str) -> ProviderAdapterResult:
    normalized_base_url = _as_str(base_url) or _configured_base_url()
    normalized_domain = _as_str(domain)

    if not normalized_domain:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "fetch_sec_filings",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    url = f"{normalized_base_url.rstrip('/')}/run/companies/sec/filings/fetch"
    payload = {"domain": normalized_domain}
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "fetch_sec_filings",
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
                "action": "fetch_sec_filings",
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
                "action": "fetch_sec_filings",
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
                "action": "fetch_sec_filings",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    filings = body.get("filings") if isinstance(body, dict) else None
    filings_dict = filings if isinstance(filings, dict) else {}
    latest_10k = _filing_info(filings_dict.get("latest_10k"))
    latest_10q = _filing_info(filings_dict.get("latest_10q"))
    recent_8k_executive_changes = _filing_list(filings_dict.get("recent_8k_executive_changes"))
    recent_8k_earnings = _filing_list(filings_dict.get("recent_8k_earnings"))
    recent_8k_material_contracts = _filing_list(
        filings_dict.get("recent_8k_material_contracts")
    )

    has_any = bool(
        latest_10k
        or latest_10q
        or recent_8k_executive_changes
        or recent_8k_earnings
        or recent_8k_material_contracts
    )
    attempt_status = "found" if has_any else "not_found"

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": "fetch_sec_filings",
            "status": attempt_status,
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": body,
        },
        "mapped": {
            "cik": _as_str(body.get("cik")),
            "ticker": _as_str(body.get("ticker")),
            "company_name": _as_str(body.get("company_name")),
            "latest_10k": latest_10k,
            "latest_10q": latest_10q,
            "recent_8k_executive_changes": recent_8k_executive_changes,
            "recent_8k_earnings": recent_8k_earnings,
            "recent_8k_material_contracts": recent_8k_material_contracts,
        },
    }


async def analyze_10k(
    *,
    document_url: str,
    domain: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    normalized_document_url = _as_str(document_url)
    normalized_domain = _as_str(domain)
    normalized_company_name = _as_str(company_name)
    if not normalized_document_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_10k",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload = {
        "document_url": normalized_document_url,
        "domain": normalized_domain,
        "company_name": normalized_company_name,
    }
    start_ms = now_ms()
    try:
        async with httpx.AsyncClient(timeout=_ANALYZE_TIMEOUT_SECONDS) as client:
            response = await client.post(_ANALYZE_10K_URL, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_10k",
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
                "action": "analyze_10k",
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
                "action": "analyze_10k",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    return _analysis_result(
        action="analyze_10k",
        body=body,
        response=response,
        duration_ms=duration_ms,
        document_url=normalized_document_url,
        domain=normalized_domain,
        company_name=normalized_company_name,
    )


async def analyze_10q(
    *,
    document_url: str,
    domain: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    normalized_document_url = _as_str(document_url)
    normalized_domain = _as_str(domain)
    normalized_company_name = _as_str(company_name)
    if not normalized_document_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_10q",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload = {
        "document_url": normalized_document_url,
        "domain": normalized_domain,
        "company_name": normalized_company_name,
    }
    start_ms = now_ms()
    try:
        async with httpx.AsyncClient(timeout=_ANALYZE_TIMEOUT_SECONDS) as client:
            response = await client.post(_ANALYZE_10Q_URL, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_10q",
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
                "action": "analyze_10q",
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
                "action": "analyze_10q",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    return _analysis_result(
        action="analyze_10q",
        body=body,
        response=response,
        duration_ms=duration_ms,
        document_url=normalized_document_url,
        domain=normalized_domain,
        company_name=normalized_company_name,
    )


async def analyze_8k_executive(
    *,
    document_url: str,
    domain: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
    normalized_document_url = _as_str(document_url)
    normalized_domain = _as_str(domain)
    normalized_company_name = _as_str(company_name)
    if not normalized_document_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_8k_executive",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload = {
        "document_url": normalized_document_url,
        "domain": normalized_domain,
        "company_name": normalized_company_name,
    }
    start_ms = now_ms()
    try:
        async with httpx.AsyncClient(timeout=_ANALYZE_TIMEOUT_SECONDS) as client:
            response = await client.post(_ANALYZE_8K_EXECUTIVE_URL, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "analyze_8k_executive",
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
                "action": "analyze_8k_executive",
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
                "action": "analyze_8k_executive",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    return _analysis_result(
        action="analyze_8k_executive",
        body=body,
        response=response,
        duration_ms=duration_ms,
        document_url=normalized_document_url,
        domain=normalized_domain,
        company_name=normalized_company_name,
    )
