from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from app.config import get_settings


def _now_ms() -> int:
    return int(time.time() * 1000)


def _domain_from_value(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    if cleaned.startswith("http://"):
        cleaned = cleaned[len("http://") :]
    if cleaned.startswith("https://"):
        cleaned = cleaned[len("https://") :]
    cleaned = cleaned.split("/")[0]
    if cleaned.startswith("www."):
        cleaned = cleaned[len("www.") :]
    return cleaned or None


def _company_search_provider_order() -> list[str]:
    settings = get_settings()
    parsed = [item.strip() for item in settings.company_search_order.split(",") if item.strip()]
    allowed = {"prospeo", "blitzapi", "companyenrich"}
    filtered = [item for item in parsed if item in allowed]
    return filtered or ["prospeo", "blitzapi", "companyenrich"]


def _canonical_company_result(
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


async def _search_companies_prospeo(
    *,
    query: str | None,
    page: int,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.prospeo_api_key:
        attempts.append(
            {"provider": "prospeo", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

    prospeo_filters = (provider_filters or {}).get("prospeo")
    if not prospeo_filters:
        if not query:
            attempts.append(
                {"provider": "prospeo", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
            )
            return [], None
        prospeo_filters = {"company": {"names": {"include": [query]}}}

    payload = {"page": page, "filters": prospeo_filters}
    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/search-company",
            headers={"X-KEY": settings.prospeo_api_key, "Content-Type": "application/json"},
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400 or body.get("error") is True:
        code = body.get("error_code")
        attempts.append(
            {
                "provider": "prospeo",
                "action": "company_search",
                "status": "not_found" if code == "NO_RESULTS" else "failed",
                "http_status": res.status_code,
                "provider_status": code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    results = body.get("results") or []
    mapped: list[dict[str, Any]] = []
    for item in results:
        company = item.get("company") or {}
        location = company.get("location") or {}
        mapped.append(
            _canonical_company_result(
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

    attempts.append(
        {
            "provider": "prospeo",
            "action": "company_search",
            "status": "found" if mapped else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mapped, body.get("pagination")


async def _search_companies_blitzapi(
    *,
    query: str | None,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.blitzapi_api_key:
        attempts.append(
            {"provider": "blitzapi", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

    blitz_input = (provider_filters or {}).get("blitzapi") or {}
    linkedin_url = blitz_input.get("company_linkedin_url")
    domain = blitz_input.get("company_domain") or _domain_from_value(query)
    start_ms = _now_ms()

    async with httpx.AsyncClient(timeout=30.0) as client:
        if not linkedin_url and domain:
            bridge = await client.post(
                "https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin",
                headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
                json={"domain": domain},
            )
            try:
                bridge_body = bridge.json()
            except Exception:  # noqa: BLE001
                bridge_body = {"raw": bridge.text}

            if bridge.status_code < 400 and bridge_body.get("found"):
                linkedin_url = bridge_body.get("company_linkedin_url")
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "found",
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )
            else:
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "not_found" if bridge.status_code in {404, 422} else "failed",
                        "http_status": bridge.status_code,
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )

        if not linkedin_url:
            attempts.append(
                {"provider": "blitzapi", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
            )
            return [], None

        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/company",
            headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
            json={"company_linkedin_url": linkedin_url},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "company_search",
                "status": "not_found" if res.status_code == 404 else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    company = body.get("company") or {}
    if not body.get("found") or not company:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "company_search",
                "status": "not_found",
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    hq = company.get("hq") or {}
    mapped = [
        _canonical_company_result(
            provider="blitzapi",
            name=company.get("name"),
            domain=company.get("domain"),
            website=company.get("website"),
            linkedin_url=company.get("linkedin_url"),
            industry=company.get("industry"),
            employee_range=company.get("size"),
            founded_year=company.get("founded_year"),
            hq_country_code=hq.get("country_code"),
            source_company_id=str(company.get("linkedin_id")) if company.get("linkedin_id") is not None else None,
            raw=company,
        )
    ]
    attempts.append(
        {
            "provider": "blitzapi",
            "action": "company_search",
            "status": "found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mapped, {"page": 1, "totalPages": 1, "totalItems": 1}


async def _search_companies_companyenrich(
    *,
    query: str | None,
    page: int,
    page_size: int,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.companyenrich_api_key:
        attempts.append(
            {"provider": "companyenrich", "action": "company_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

    override = (provider_filters or {}).get("companyenrich") or {}
    payload: dict[str, Any] = {"page": page, "pageSize": page_size}
    if query:
        payload["query"] = query
    payload.update(override)
    if not payload.get("query") and not payload.get("semanticQuery"):
        attempts.append(
            {"provider": "companyenrich", "action": "company_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return [], None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.companyenrich.com/companies/search",
            headers={
                "Authorization": f"Bearer {settings.companyenrich_api_key}",
                "accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "companyenrich",
                "action": "company_search",
                "status": "not_found" if res.status_code in {404, 422} else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    items = body.get("items") or []
    mapped: list[dict[str, Any]] = []
    for company in items:
        socials = company.get("socials") or {}
        location = company.get("location") or {}
        country = (location.get("country") or {}).get("code")
        mapped.append(
            _canonical_company_result(
                provider="companyenrich",
                name=company.get("name"),
                domain=company.get("domain"),
                website=company.get("website"),
                linkedin_url=socials.get("linkedin_url"),
                industry=company.get("industry"),
                employee_range=company.get("employees"),
                founded_year=company.get("founded_year"),
                hq_country_code=country,
                source_company_id=company.get("id"),
                raw=company,
            )
        )

    attempts.append(
        {
            "provider": "companyenrich",
            "action": "company_search",
            "status": "found" if mapped else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    pagination = {"page": body.get("page"), "totalPages": body.get("totalPages"), "totalItems": body.get("totalItems")}
    return mapped, pagination


def _dedupe_companies(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            item.get("company_domain")
            or item.get("company_linkedin_url")
            or item.get("source_company_id")
            or item.get("company_name")
            or str(uuid.uuid4())
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


async def execute_company_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    query = input_data.get("query")
    page = int(input_data.get("page") or 1)
    page_size = min(max(int(input_data.get("page_size") or 25), 1), 100)
    limit = max(int(input_data.get("limit") or 100), 1)
    provider_filters = input_data.get("provider_filters")
    if provider_filters is not None and not isinstance(provider_filters, dict):
        provider_filters = None

    if not isinstance(query, str) and not provider_filters:
        return {
            "run_id": run_id,
            "operation_id": "company.search",
            "status": "failed",
            "missing_inputs": ["query|provider_filters"],
            "provider_attempts": attempts,
        }

    combined: list[dict[str, Any]] = []
    pagination_by_provider: dict[str, Any] = {}

    for provider in _company_search_provider_order():
        if provider == "prospeo":
            results, pagination = await _search_companies_prospeo(
                query=query if isinstance(query, str) else None,
                page=page,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        elif provider == "blitzapi":
            results, pagination = await _search_companies_blitzapi(
                query=query if isinstance(query, str) else None,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        elif provider == "companyenrich":
            results, pagination = await _search_companies_companyenrich(
                query=query if isinstance(query, str) else None,
                page=page,
                page_size=page_size,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        else:
            continue

        if pagination is not None:
            pagination_by_provider[provider] = pagination
        combined.extend(results)
        if len(combined) >= limit:
            break

    deduped = _dedupe_companies(combined)[:limit]
    return {
        "run_id": run_id,
        "operation_id": "company.search",
        "status": "found" if deduped else "not_found",
        "output": {
            "results": deduped,
            "result_count": len(deduped),
            "provider_order_used": _company_search_provider_order(),
            "pagination": pagination_by_provider,
        },
        "provider_attempts": attempts,
    }



def _person_search_provider_order() -> list[str]:
    settings = get_settings()
    parsed = [item.strip() for item in settings.person_search_order.split(",") if item.strip()]
    allowed = {"prospeo", "blitzapi", "companyenrich"}
    filtered = [item for item in parsed if item in allowed]
    return filtered or ["prospeo", "blitzapi", "companyenrich"]


def _canonical_person_result(
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


async def _search_people_prospeo(
    *,
    query: str | None,
    page: int,
    company_domain: str | None,
    company_name: str | None,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.prospeo_api_key:
        attempts.append(
            {"provider": "prospeo", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

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
        attempts.append(
            {"provider": "prospeo", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return [], None

    payload = {"page": page, "filters": filters}
    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/search-person",
            headers={"X-KEY": settings.prospeo_api_key, "Content-Type": "application/json"},
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400 or body.get("error") is True:
        code = body.get("error_code")
        attempts.append(
            {
                "provider": "prospeo",
                "action": "person_search",
                "status": "not_found" if code == "NO_RESULTS" else "failed",
                "http_status": res.status_code,
                "provider_status": code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    mapped: list[dict[str, Any]] = []
    for item in body.get("results") or []:
        person = item.get("person") or {}
        company = item.get("company") or {}
        mapped.append(
            _canonical_person_result(
                provider="prospeo",
                full_name=person.get("full_name") or person.get("name"),
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                linkedin_url=person.get("linkedin_url"),
                headline=person.get("headline"),
                current_title=person.get("job_title") or person.get("title"),
                company_name=company.get("name"),
                company_domain=company.get("domain"),
                location_name=person.get("location"),
                country_code=person.get("country_code"),
                source_person_id=person.get("person_id"),
                raw={"person": person, "company": company},
            )
        )

    attempts.append(
        {
            "provider": "prospeo",
            "action": "person_search",
            "status": "found" if mapped else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mapped, body.get("pagination")


async def _search_people_blitzapi(
    *,
    query: str | None,
    company_domain: str | None,
    company_linkedin_url: str | None,
    limit: int,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.blitzapi_api_key:
        attempts.append(
            {"provider": "blitzapi", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

    blitz_input = (provider_filters or {}).get("blitzapi") or {}
    linkedin_url = blitz_input.get("company_linkedin_url") or company_linkedin_url
    domain = blitz_input.get("company_domain") or company_domain
    start_ms = _now_ms()

    async with httpx.AsyncClient(timeout=30.0) as client:
        if not linkedin_url and domain:
            bridge = await client.post(
                "https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin",
                headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
                json={"domain": domain},
            )
            try:
                bridge_body = bridge.json()
            except Exception:  # noqa: BLE001
                bridge_body = {"raw": bridge.text}

            if bridge.status_code < 400 and bridge_body.get("found"):
                linkedin_url = bridge_body.get("company_linkedin_url")
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "found",
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )
            else:
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "not_found" if bridge.status_code in {404, 422} else "failed",
                        "http_status": bridge.status_code,
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )

        if not linkedin_url:
            attempts.append(
                {"provider": "blitzapi", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
            )
            return [], None

        if query:
            cascade = blitz_input.get("cascade") or [
                {
                    "include_title": [query],
                    "exclude_title": ["intern", "assistant", "junior"],
                    "location": ["WORLD"],
                    "include_headline_search": True,
                }
            ]
            res = await client.post(
                "https://api.blitz-api.ai/v2/search/waterfall-icp-keyword",
                headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
                json={"company_linkedin_url": linkedin_url, "cascade": cascade, "max_results": min(limit, 100)},
            )
            try:
                body = res.json()
            except Exception:  # noqa: BLE001
                body = {"raw": res.text}

            if res.status_code >= 400:
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "person_search",
                        "status": "failed",
                        "http_status": res.status_code,
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": body,
                    }
                )
                return [], None

            mapped: list[dict[str, Any]] = []
            for row in body.get("results") or []:
                person = row.get("person") or {}
                location = person.get("location") or {}
                current = (person.get("experiences") or [{}])[0] or {}
                mapped.append(
                    _canonical_person_result(
                        provider="blitzapi",
                        full_name=person.get("full_name"),
                        first_name=person.get("first_name"),
                        last_name=person.get("last_name"),
                        linkedin_url=person.get("linkedin_url"),
                        headline=person.get("headline"),
                        current_title=current.get("job_title"),
                        company_name=None,
                        company_domain=None,
                        location_name=location.get("city"),
                        country_code=location.get("country_code"),
                        source_person_id=None,
                        raw=row,
                    )
                )

            attempts.append(
                {
                    "provider": "blitzapi",
                    "action": "person_search",
                    "status": "found" if mapped else "not_found",
                    "duration_ms": _now_ms() - start_ms,
                    "raw_response": body,
                }
            )
            return mapped, {"page": 1, "totalPages": 1, "totalItems": len(mapped)}

        res = await client.post(
            "https://api.blitz-api.ai/v2/search/employee-finder",
            headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
            json={"company_linkedin_url": linkedin_url, "max_results": min(limit, 100), **{k: v for k, v in blitz_input.items() if k != "company_linkedin_url" and k != "company_domain"}},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "person_search",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    mapped = []
    for person in body.get("results") or []:
        location = person.get("location") or {}
        current = (person.get("experiences") or [{}])[0] or {}
        mapped.append(
            _canonical_person_result(
                provider="blitzapi",
                full_name=person.get("full_name"),
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                linkedin_url=person.get("linkedin_url"),
                headline=person.get("headline"),
                current_title=current.get("job_title"),
                company_name=None,
                company_domain=None,
                location_name=location.get("city"),
                country_code=location.get("country_code"),
                source_person_id=None,
                raw=person,
            )
        )

    attempts.append(
        {
            "provider": "blitzapi",
            "action": "person_search",
            "status": "found" if mapped else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mapped, {"page": body.get("page"), "totalPages": body.get("total_pages"), "totalItems": body.get("results_length")}


async def _search_people_companyenrich(
    *,
    query: str | None,
    page: int,
    page_size: int,
    company_domain: str | None,
    company_name: str | None,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    if not settings.companyenrich_api_key:
        attempts.append(
            {"provider": "companyenrich", "action": "person_search", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return [], None

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
        attempts.append(
            {"provider": "companyenrich", "action": "person_search", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return [], None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.companyenrich.com/people/search",
            headers={
                "Authorization": f"Bearer {settings.companyenrich_api_key}",
                "accept": "application/json",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "companyenrich",
                "action": "person_search",
                "status": "not_found" if res.status_code in {404, 422} else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return [], None

    mapped = []
    for person in body.get("items") or []:
        socials = person.get("socials") or {}
        location = person.get("location") or {}
        country = location.get("country") or {}
        experiences = person.get("experiences") or []
        current_company = None
        for exp in experiences:
            if exp.get("isCurrent") and exp.get("type") == "company":
                current_company = exp.get("company") or {}
                break
        mapped.append(
            _canonical_person_result(
                provider="companyenrich",
                full_name=person.get("name"),
                first_name=person.get("first_name"),
                last_name=person.get("last_name"),
                linkedin_url=socials.get("linkedin_url"),
                headline=person.get("position"),
                current_title=person.get("position"),
                company_name=(current_company or {}).get("name"),
                company_domain=(current_company or {}).get("domain"),
                location_name=location.get("address"),
                country_code=country.get("code"),
                source_person_id=str(person.get("id")) if person.get("id") is not None else None,
                raw=person,
            )
        )

    attempts.append(
        {
            "provider": "companyenrich",
            "action": "person_search",
            "status": "found" if mapped else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mapped, {"page": body.get("page"), "totalPages": body.get("totalPages"), "totalItems": body.get("totalItems")}


def _dedupe_people(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in items:
        key = (
            item.get("linkedin_url")
            or item.get("source_person_id")
            or f"{item.get('full_name')}::{item.get('current_company_domain')}"
            or str(uuid.uuid4())
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


async def execute_person_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    query = input_data.get("query")
    page = int(input_data.get("page") or 1)
    page_size = min(max(int(input_data.get("page_size") or 25), 1), 100)
    limit = max(int(input_data.get("limit") or 100), 1)
    company_domain = _domain_from_value(input_data.get("company_domain") or input_data.get("company_website"))
    company_name = input_data.get("company_name")
    company_linkedin_url = input_data.get("company_linkedin_url")
    provider_filters = input_data.get("provider_filters")
    if provider_filters is not None and not isinstance(provider_filters, dict):
        provider_filters = None

    if not isinstance(query, str) and not company_domain and not company_name and not company_linkedin_url and not provider_filters:
        return {
            "run_id": run_id,
            "operation_id": "person.search",
            "status": "failed",
            "missing_inputs": ["query|company_domain|company_name|company_linkedin_url|provider_filters"],
            "provider_attempts": attempts,
        }

    combined: list[dict[str, Any]] = []
    pagination_by_provider: dict[str, Any] = {}

    for provider in _person_search_provider_order():
        if provider == "prospeo":
            results, pagination = await _search_people_prospeo(
                query=query if isinstance(query, str) else None,
                page=page,
                company_domain=company_domain,
                company_name=company_name if isinstance(company_name, str) else None,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        elif provider == "blitzapi":
            results, pagination = await _search_people_blitzapi(
                query=query if isinstance(query, str) else None,
                company_domain=company_domain,
                company_linkedin_url=company_linkedin_url if isinstance(company_linkedin_url, str) else None,
                limit=limit,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        elif provider == "companyenrich":
            results, pagination = await _search_people_companyenrich(
                query=query if isinstance(query, str) else None,
                page=page,
                page_size=page_size,
                company_domain=company_domain,
                company_name=company_name if isinstance(company_name, str) else None,
                attempts=attempts,
                provider_filters=provider_filters,
            )
        else:
            continue

        if pagination is not None:
            pagination_by_provider[provider] = pagination
        combined.extend(results)
        if len(combined) >= limit:
            break

    deduped = _dedupe_people(combined)[:limit]
    return {
        "run_id": run_id,
        "operation_id": "person.search",
        "status": "found" if deduped else "not_found",
        "output": {
            "results": deduped,
            "result_count": len(deduped),
            "provider_order_used": _person_search_provider_order(),
            "pagination": pagination_by_provider,
        },
        "provider_attempts": attempts,
    }
