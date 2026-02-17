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


def _extract_location_name(value: Any) -> str | None:
    candidate = _as_str(value)
    if candidate:
        return candidate
    location = _as_dict(value)
    if not location:
        return None
    for key in ("name", "full", "address", "formatted"):
        candidate = _as_str(location.get(key))
        if candidate:
            return candidate
    parts: list[str] = []
    for key in ("city", "state", "state_code", "country", "country_name", "country_code"):
        candidate = _as_str(location.get(key))
        if candidate:
            parts.append(candidate)
    if not parts:
        country_obj = _as_dict(location.get("country"))
        if isinstance(country_obj, dict):
            for candidate in (_as_str(country_obj.get("name")), _as_str(country_obj.get("code"))):
                if candidate:
                    parts.append(candidate)
    return ", ".join(parts) if parts else None


def _extract_country_code(person: dict[str, Any]) -> str | None:
    country_code = _as_str(person.get("country_code"))
    if country_code:
        return country_code
    location = _as_dict(person.get("location"))
    if location:
        direct = _as_str(location.get("country_code"))
        if direct:
            return direct
        nested = _as_str(_as_dict(location.get("country")).get("code"))
        if nested:
            return nested
    return None


def canonical_company_result(
    *,
    provider: str,
    name: str | None,
    domain: str | None,
    website: str | None,
    linkedin_url: str | None,
    industry: str | None,
    employee_range: str | None,
    founded_year: int | None,
    hq_country_code: str | None,
    source_company_id: str | None,
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "company_name": name,
        "company_domain": domain,
        "company_website": website,
        "company_linkedin_url": linkedin_url,
        "industry_primary": industry,
        "employee_range": employee_range,
        "founded_year": founded_year,
        "hq_country_code": hq_country_code,
        "source_company_id": source_company_id,
        "source_provider": provider,
        "raw": raw,
    }


def canonical_person_result(
    *,
    provider: str,
    full_name: str | None,
    first_name: str | None,
    last_name: str | None,
    linkedin_url: str | None,
    headline: str | None,
    current_title: str | None,
    company_name: str | None,
    company_domain: str | None,
    location_name: str | None,
    country_code: str | None,
    source_person_id: str | None,
    raw: dict[str, Any],
) -> dict[str, Any]:
    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "linkedin_url": linkedin_url,
        "headline": headline,
        "current_title": current_title,
        "current_company_name": company_name,
        "current_company_domain": company_domain,
        "location_name": location_name,
        "country_code": country_code,
        "source_person_id": source_person_id,
        "source_provider": provider,
        "raw": raw,
    }


async def search_companies(
    *,
    api_key: str | None,
    query: str | None,
    page: int,
    provider_filters: dict[str, Any] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "prospeo", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": {"results": [], "pagination": None},
        }
    prospeo_filters = (provider_filters or {}).get("prospeo")
    if not prospeo_filters:
        if not query:
            return {
                "attempt": {"provider": "prospeo", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"},
                "mapped": {"results": [], "pagination": None},
            }
        prospeo_filters = {"company": {"names": {"include": [query]}}}

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/search-company",
            headers={"X-KEY": api_key, "Content-Type": "application/json"},
            json={"page": page, "filters": prospeo_filters},
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400 or body.get("error") is True:
        code = _as_str(body.get("error_code"))
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "company_search",
                "status": "not_found" if code == "NO_RESULTS" else "failed",
                "http_status": res.status_code,
                "provider_status": code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "pagination": None},
        }

    mapped: list[dict[str, Any]] = []
    for item in _as_list(body.get("results")):
        item_dict = _as_dict(item)
        company = _as_dict(item_dict.get("company"))
        location = _as_dict(company.get("location"))
        mapped.append(
            canonical_company_result(
                provider="prospeo",
                name=company.get("name"),
                domain=company.get("domain"),
                website=company.get("website"),
                linkedin_url=company.get("linkedin_url"),
                industry=company.get("industry"),
                employee_range=company.get("employee_range"),
                founded_year=_as_int(company.get("founded")),
                hq_country_code=location.get("country_code"),
                source_company_id=str(company.get("company_id")) if company.get("company_id") is not None else None,
                raw=company,
            )
        )

    return {
        "attempt": {"provider": "prospeo", "action": "company_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": mapped, "pagination": body.get("pagination")},
    }


async def search_people(
    *,
    api_key: str | None,
    query: str | None,
    page: int,
    company_domain: str | None,
    company_name: str | None,
    provider_filters: dict[str, Any] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "prospeo", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": {"results": [], "pagination": None},
        }
    filters = (provider_filters or {}).get("prospeo")
    if not filters:
        filters = {}
        if query:
            filters["person_job_title"] = {"include": [query]}
        if company_domain:
            filters.setdefault("company", {}).setdefault("websites", {})["include"] = [company_domain]
        elif company_name:
            filters.setdefault("company", {}).setdefault("names", {})["include"] = [company_name]
    if not filters:
        return {
            "attempt": {"provider": "prospeo", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": {"results": [], "pagination": None},
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/search-person",
            headers={"X-KEY": api_key, "Content-Type": "application/json"},
            json={"page": page, "filters": filters},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400 or body.get("error") is True:
        code = _as_str(body.get("error_code"))
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "person_search",
                "status": "not_found" if code == "NO_RESULTS" else "failed",
                "http_status": res.status_code,
                "provider_status": code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "pagination": None},
        }

    mapped: list[dict[str, Any]] = []
    for item in _as_list(body.get("results")):
        item_dict = _as_dict(item)
        person = _as_dict(item_dict.get("person"))
        company = _as_dict(item_dict.get("company"))
        mapped.append(
            canonical_person_result(
                provider="prospeo",
                full_name=person.get("full_name") or person.get("name"),
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                linkedin_url=person.get("linkedin_url"),
                headline=person.get("headline"),
                current_title=person.get("current_job_title") or person.get("job_title") or person.get("title"),
                company_name=company.get("name"),
                company_domain=company.get("domain"),
                location_name=_extract_location_name(person.get("location")),
                country_code=_extract_country_code(person),
                source_person_id=str(person.get("person_id")) if person.get("person_id") is not None else None,
                raw={"person": person, "company": company},
            )
        )
    return {
        "attempt": {"provider": "prospeo", "action": "person_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": mapped, "pagination": body.get("pagination")},
    }


async def enrich_company(
    *,
    api_key: str | None,
    data: dict[str, Any],
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "prospeo", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": None,
        }
    payload_data = {k: v for k, v in data.items() if v}
    if not payload_data:
        return {
            "attempt": {"provider": "prospeo", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": None,
        }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/enrich-company",
            headers={"X-KEY": api_key, "Content-Type": "application/json"},
            json={"data": payload_data},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400 or body.get("error") is True:
        code = _as_str(body.get("error_code"))
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "company_enrich",
                "status": "not_found" if code == "NO_MATCH" else "failed",
                "http_status": res.status_code,
                "provider_status": code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    company = _as_dict(body.get("company"))
    found = bool(company)
    return {
        "attempt": {
            "provider": "prospeo",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "provider_status": "free_enrichment" if body.get("free_enrichment") else "ok",
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": company if found else None,
    }
