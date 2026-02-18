from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_person_result(
    *,
    raw: dict[str, Any],
    fallback_company_name: str | None,
    fallback_company_domain: str | None,
) -> dict[str, Any]:
    return {
        "full_name": _as_str(raw.get("full_name")),
        "first_name": _as_str(raw.get("first_name")),
        "last_name": _as_str(raw.get("last_name")),
        "linkedin_url": _as_str(raw.get("profile_url")),
        "headline": _as_str(raw.get("job_title")),
        "current_title": _as_str(raw.get("job_title")),
        "current_company_name": _as_str(raw.get("company_name")) or fallback_company_name,
        "current_company_domain": _as_str(raw.get("company_website")) or fallback_company_domain,
        "location_name": _as_str(raw.get("location")),
        "country_code": None,
        "source_person_id": None,
        "source_provider": "leadmagic",
        "raw": raw,
    }


async def search_employees(
    *,
    api_key: str | None,
    company_domain: str | None,
    company_name: str | None,
    limit: int,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "employee_finder",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "pagination": None},
        }
    if not _as_str(company_domain) and not _as_str(company_name):
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "employee_finder",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "pagination": None},
        }

    payload: dict[str, Any] = {"limit": max(limit, 1)}
    if _as_str(company_domain):
        payload["company_domain"] = _as_str(company_domain)
    if _as_str(company_name):
        payload["company_name"] = _as_str(company_name)

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/employee-finder",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "employee_finder",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "pagination": None},
        }

    mapped = [
        _canonical_person_result(
            raw=_as_dict(employee),
            fallback_company_name=_as_str(company_name),
            fallback_company_domain=_as_str(company_domain),
        )
        for employee in _as_list(body.get("employees"))
    ]
    pagination = {
        "page": 1,
        "totalPages": 1,
        "totalItems": body.get("total_count", len(mapped)),
    }
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "employee_finder",
            "status": "found" if mapped else "not_found",
            "provider_status": body.get("message"),
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"results": mapped, "pagination": pagination},
    }


async def search_by_role(
    *,
    api_key: str | None,
    company_domain: str | None,
    company_name: str | None,
    job_title: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "role_finder",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "pagination": None},
        }
    if not _as_str(job_title) or (not _as_str(company_domain) and not _as_str(company_name)):
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "role_finder",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "pagination": None},
        }

    payload: dict[str, Any] = {"job_title": _as_str(job_title)}
    if _as_str(company_domain):
        payload["company_domain"] = _as_str(company_domain)
    if _as_str(company_name):
        payload["company_name"] = _as_str(company_name)

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/role-finder",
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "role_finder",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "pagination": None},
        }

    profile_url = _as_str(body.get("profile_url"))
    if not profile_url:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "role_finder",
                "status": "not_found",
                "provider_status": body.get("message"),
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "pagination": {"page": 1, "totalPages": 1, "totalItems": 0}},
        }

    mapped_person = _canonical_person_result(
        raw=body,
        fallback_company_name=_as_str(company_name),
        fallback_company_domain=_as_str(company_domain),
    )
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "role_finder",
            "status": "found",
            "provider_status": body.get("message"),
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"results": [mapped_person], "pagination": {"page": 1, "totalPages": 1, "totalItems": 1}},
    }


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
