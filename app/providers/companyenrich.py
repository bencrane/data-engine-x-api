from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def canonical_company_result(company: dict[str, Any]) -> dict[str, Any]:
    socials = _as_dict(company.get("socials"))
    location = _as_dict(company.get("location"))
    country = _as_str(_as_dict(location.get("country")).get("code"))
    return {
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_website": company.get("website"),
        "company_linkedin_url": socials.get("linkedin_url"),
        "industry_primary": company.get("industry"),
        "employee_range": company.get("employees"),
        "founded_year": _as_int(company.get("founded_year")),
        "hq_country_code": country,
        "source_company_id": str(company.get("id")) if company.get("id") is not None else None,
        "source_provider": "companyenrich",
        "raw": company,
    }


def canonical_person_result(person: dict[str, Any]) -> dict[str, Any]:
    socials = _as_dict(person.get("socials"))
    location = _as_dict(person.get("location"))
    country = _as_dict(location.get("country"))
    experiences = _as_list(person.get("experiences"))
    current_company = None
    current_experience = None
    for exp in experiences:
        if not isinstance(exp, dict) or not exp.get("isCurrent"):
            continue
        current_experience = exp
        if exp.get("type") == "company":
            current_company = exp.get("company") or {}
        break
    current_position = person.get("position")
    if (not isinstance(current_position, str) or not current_position.strip()) and isinstance(current_experience, dict):
        current_position = current_experience.get("position")
    return {
        "full_name": person.get("name"),
        "first_name": person.get("first_name"),
        "last_name": person.get("last_name"),
        "linkedin_url": socials.get("linkedin_url"),
        "headline": person.get("position"),
        "current_title": current_position,
        "current_company_name": (current_company or {}).get("name"),
        "current_company_domain": (current_company or {}).get("domain"),
        "location_name": _as_str(location.get("address")),
        "country_code": country.get("code"),
        "source_person_id": str(person.get("id")) if person.get("id") is not None else None,
        "source_provider": "companyenrich",
        "raw": person,
    }


async def search_companies(
    *,
    api_key: str | None,
    query: str | None,
    page: int,
    page_size: int,
    provider_filters: dict[str, Any] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {"attempt": {"provider": "companyenrich", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": {"results": [], "pagination": None}}
    override = (provider_filters or {}).get("companyenrich") or {}
    payload: dict[str, Any] = {"page": page, "pageSize": page_size}
    if query:
        payload["query"] = query
    payload.update(override)
    if not payload.get("query") and not payload.get("semanticQuery"):
        return {"attempt": {"provider": "companyenrich", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": {"results": [], "pagination": None}}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.companyenrich.com/companies/search",
            headers={"Authorization": f"Bearer {api_key}", "accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "companyenrich", "action": "company_search", "status": "not_found" if res.status_code in {404, 422} else "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"results": [], "pagination": None},
        }
    mapped = [canonical_company_result(_as_dict(company)) for company in _as_list(body.get("items"))]
    pagination = {"page": body.get("page"), "totalPages": body.get("totalPages"), "totalItems": body.get("totalItems")}
    return {
        "attempt": {"provider": "companyenrich", "action": "company_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": mapped, "pagination": pagination},
    }


async def search_people(
    *,
    api_key: str | None,
    query: str | None,
    page: int,
    page_size: int,
    company_domain: str | None,
    company_name: str | None,
    provider_filters: dict[str, Any] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {"attempt": {"provider": "companyenrich", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": {"results": [], "pagination": None}}
    override = (provider_filters or {}).get("companyenrich") or {}
    payload: dict[str, Any] = {"page": page, "pageSize": page_size}
    if query:
        payload["positionQuery"] = query
    if company_domain:
        payload["domains"] = [company_domain]
    elif company_name:
        payload["companyFilter"] = {"query": company_name}
    payload.update(override)
    if not payload.get("positionQuery") and not payload.get("domains") and not payload.get("companyFilter"):
        return {"attempt": {"provider": "companyenrich", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": {"results": [], "pagination": None}}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.companyenrich.com/people/search",
            headers={"Authorization": f"Bearer {api_key}", "accept": "application/json", "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "companyenrich", "action": "person_search", "status": "not_found" if res.status_code in {404, 422} else "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"results": [], "pagination": None},
        }
    mapped = [canonical_person_result(_as_dict(person)) for person in _as_list(body.get("items"))]
    pagination = {"page": body.get("page"), "totalPages": body.get("totalPages"), "totalItems": body.get("totalItems")}
    return {
        "attempt": {"provider": "companyenrich", "action": "person_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": mapped, "pagination": pagination},
    }


async def enrich_company(
    *,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {"attempt": {"provider": "companyenrich", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": None}
    if not domain:
        return {"attempt": {"provider": "companyenrich", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": None}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            "https://api.companyenrich.com/companies/enrich",
            params={"domain": domain},
            headers={"Authorization": f"Bearer {api_key}", "accept": "application/json"},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "companyenrich", "action": "company_enrich", "status": "not_found" if res.status_code == 404 else "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": None,
        }
    found = bool(body.get("id") or body.get("domain") or body.get("name"))
    return {
        "attempt": {"provider": "companyenrich", "action": "company_enrich", "status": "found" if found else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": body if found else None,
    }
