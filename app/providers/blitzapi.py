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


def canonical_company_result(
    *,
    company: dict[str, Any],
) -> dict[str, Any]:
    hq = _as_dict(company.get("hq"))
    return {
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_website": company.get("website"),
        "company_linkedin_url": company.get("linkedin_url"),
        "industry_primary": company.get("industry"),
        "employee_range": company.get("size"),
        "founded_year": company.get("founded_year"),
        "hq_country_code": hq.get("country_code"),
        "source_company_id": str(company.get("linkedin_id")) if company.get("linkedin_id") is not None else None,
        "source_provider": "blitzapi",
        "raw": company,
    }


def canonical_person_result(
    *,
    person: dict[str, Any],
    raw: dict[str, Any],
) -> dict[str, Any]:
    location = _as_dict(person.get("location"))
    experiences = _as_list(person.get("experiences"))
    current = next((exp for exp in experiences if isinstance(exp, dict) and exp.get("job_is_current")), None)
    if not isinstance(current, dict):
        current = experiences[0] if experiences and isinstance(experiences[0], dict) else {}
    location_name = _as_str(location.get("city")) or _as_str(location.get("country_code"))
    return {
        "full_name": person.get("full_name"),
        "first_name": person.get("first_name"),
        "last_name": person.get("last_name"),
        "linkedin_url": person.get("linkedin_url"),
        "headline": person.get("headline"),
        "current_title": current.get("job_title") or current.get("position"),
        "current_company_name": None,
        "current_company_domain": None,
        "location_name": location_name,
        "country_code": location.get("country_code"),
        "source_person_id": str(person.get("id")) if person.get("id") is not None else None,
        "source_provider": "blitzapi",
        "raw": raw,
    }


async def domain_to_linkedin(
    *,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "blitzapi", "action": "domain_to_linkedin", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": {"company_linkedin_url": None},
        }
    if not domain:
        return {
            "attempt": {"provider": "blitzapi", "action": "domain_to_linkedin", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": {"company_linkedin_url": None},
        }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"domain": domain},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code < 400 and body.get("found"):
        return {
            "attempt": {"provider": "blitzapi", "action": "domain_to_linkedin", "status": "found", "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"company_linkedin_url": body.get("company_linkedin_url")},
        }
    return {
        "attempt": {
            "provider": "blitzapi",
            "action": "domain_to_linkedin",
            "status": "not_found" if res.status_code in {404} else "failed",
            "http_status": res.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"company_linkedin_url": None},
    }


async def company_search(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "blitzapi", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": {"results": [], "pagination": None},
        }
    if not company_linkedin_url:
        return {
            "attempt": {"provider": "blitzapi", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": {"results": [], "pagination": None},
        }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/company",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"company_linkedin_url": company_linkedin_url},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "blitzapi", "action": "company_search", "status": "not_found" if res.status_code == 404 else "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"results": [], "pagination": None},
        }
    company = _as_dict(body.get("company"))
    if not body.get("found") or not company:
        return {
            "attempt": {"provider": "blitzapi", "action": "company_search", "status": "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"results": [], "pagination": None},
        }
    return {
        "attempt": {"provider": "blitzapi", "action": "company_search", "status": "found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": [canonical_company_result(company=company)], "pagination": {"page": 1, "totalPages": 1, "totalItems": 1}},
    }


async def person_search(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
    query: str | None,
    limit: int,
    blitz_input: dict[str, Any] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "blitzapi", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": {"results": [], "pagination": None},
        }
    if not company_linkedin_url:
        return {
            "attempt": {"provider": "blitzapi", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": {"results": [], "pagination": None},
        }
    blitz_input = blitz_input or {}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        if query:
            cascade = blitz_input.get("cascade") or [
                {"include_title": [query], "exclude_title": ["intern", "assistant", "junior"], "location": ["WORLD"], "include_headline_search": True}
            ]
            res = await client.post(
                "https://api.blitz-api.ai/v2/search/waterfall-icp-keyword",
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
                json={"company_linkedin_url": company_linkedin_url, "cascade": cascade, "max_results": min(limit, 100)},
            )
            body = parse_json_or_raw(res.text, res.json)
            if res.status_code >= 400:
                return {
                    "attempt": {"provider": "blitzapi", "action": "person_search", "status": "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
                    "mapped": {"results": [], "pagination": None},
                }
            mapped = [canonical_person_result(person=_as_dict(_as_dict(row).get("person")), raw=_as_dict(row)) for row in _as_list(body.get("results"))]
            return {
                "attempt": {"provider": "blitzapi", "action": "person_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
                "mapped": {"results": mapped, "pagination": {"page": 1, "totalPages": 1, "totalItems": len(mapped)}},
            }

        pass_through = {k: v for k, v in blitz_input.items() if k not in {"company_linkedin_url", "company_domain"}}
        res = await client.post(
            "https://api.blitz-api.ai/v2/search/employee-finder",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"company_linkedin_url": company_linkedin_url, "max_results": min(limit, 100), **pass_through},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "blitzapi", "action": "person_search", "status": "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": {"results": [], "pagination": None},
        }
    mapped = [canonical_person_result(person=_as_dict(person), raw=_as_dict(person)) for person in _as_list(body.get("results"))]
    return {
        "attempt": {"provider": "blitzapi", "action": "person_search", "status": "found" if mapped else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"results": mapped, "pagination": {"page": body.get("page"), "totalPages": body.get("total_pages"), "totalItems": body.get("results_length")}},
    }


async def phone_enrich(
    *,
    api_key: str | None,
    person_linkedin_url: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "blitzapi", "action": "resolve_mobile_phone", "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": None,
        }
    if not person_linkedin_url:
        return {
            "attempt": {"provider": "blitzapi", "action": "resolve_mobile_phone", "status": "skipped", "skip_reason": "missing_required_inputs"},
            "mapped": None,
        }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/phone",
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json={"person_linkedin_url": person_linkedin_url},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "blitzapi", "action": "resolve_mobile_phone", "status": "failed", "http_status": res.status_code, "duration_ms": now_ms() - start_ms, "raw_response": body},
            "mapped": None,
        }
    phone = _as_str(body.get("phone"))
    found = bool(body.get("found") and phone)
    return {
        "attempt": {"provider": "blitzapi", "action": "resolve_mobile_phone", "status": "found" if found else "not_found", "duration_ms": now_ms() - start_ms, "raw_response": body},
        "mapped": {"mobile_phone": phone if body.get("found") else None},
    }


async def enrich_company(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
) -> ProviderAdapterResult:
    result = await company_search(api_key=api_key, company_linkedin_url=company_linkedin_url)
    attempt = dict(result["attempt"])
    attempt["action"] = "company_enrich"
    mapped = None
    rows = (result["mapped"] or {}).get("results") if isinstance(result["mapped"], dict) else None
    if rows:
        mapped = (rows[0] or {}).get("raw")
    return {"attempt": attempt, "mapped": mapped}
