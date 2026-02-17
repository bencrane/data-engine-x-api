from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _extract_location_name(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if not isinstance(value, dict):
        return None
    for key in ("name", "full", "address", "formatted"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    parts: list[str] = []
    for key in ("city", "state", "state_code", "country", "country_name", "country_code"):
        candidate = value.get(key)
        if isinstance(candidate, str):
            cleaned = candidate.strip()
            if cleaned:
                parts.append(cleaned)
    if not parts:
        country_obj = value.get("country")
        if isinstance(country_obj, dict):
            country_name = country_obj.get("name")
            country_code = country_obj.get("code")
            for candidate in (country_name, country_code):
                if isinstance(candidate, str) and candidate.strip():
                    parts.append(candidate.strip())
    return ", ".join(parts) if parts else None


def _extract_country_code(person: dict[str, Any]) -> str | None:
    country_code = person.get("country_code")
    if isinstance(country_code, str) and country_code.strip():
        return country_code.strip()
    location = person.get("location")
    if isinstance(location, dict):
        direct = location.get("country_code")
        if isinstance(direct, str) and direct.strip():
            return direct.strip()
        country_obj = location.get("country")
        if isinstance(country_obj, dict):
            nested = country_obj.get("code")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
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
        code = body.get("error_code")
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
    for item in body.get("results") or []:
        company = item.get("company") or {}
        location = company.get("location") or {}
        mapped.append(
            canonical_company_result(
                provider="prospeo",
                name=company.get("name"),
                domain=company.get("domain"),
                website=company.get("website"),
                linkedin_url=company.get("linkedin_url"),
                industry=company.get("industry"),
                employee_range=company.get("employee_range"),
                founded_year=company.get("founded"),
                hq_country_code=location.get("country_code"),
                source_company_id=company.get("company_id"),
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
        code = body.get("error_code")
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
    for item in body.get("results") or []:
        person = item.get("person") or {}
        company = item.get("company") or {}
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
    if res.status_code >= 400:
        code = body.get("error_code")
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
    company = body.get("company")
    found = bool(company and isinstance(company, dict))
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
