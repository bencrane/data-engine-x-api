from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://api.theirstack.com"


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
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    for item in value:
        parsed = _as_str(item)
        if parsed:
            cleaned.append(parsed)
    return cleaned or None


def _map_company_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "company_name": _as_str(raw.get("name")),
        "domain": _as_str(raw.get("domain")),
        "linkedin_url": _as_str(raw.get("linkedin_url")),
        "industry": _as_str(raw.get("industry")),
        "employee_count": _as_int(raw.get("employee_count")),
        "country_code": _as_str(raw.get("country_code")),
        "num_jobs": _as_int(raw.get("num_jobs")),
        "num_jobs_last_30_days": _as_int(raw.get("num_jobs_last_30_days")),
        "technology_slugs": _as_str_list(raw.get("technology_slugs")),
        "annual_revenue_usd": _as_float(raw.get("annual_revenue_usd")),
        "total_funding_usd": _as_int(raw.get("total_funding_usd")),
        "funding_stage": _as_str(raw.get("funding_stage")),
    }


def _map_location_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = _as_str(raw.get("name"))
    display_name = _as_str(raw.get("display_name"))
    if not name and not display_name:
        return None

    return {
        "name": name,
        "state": _as_str(raw.get("state")),
        "state_code": _as_str(raw.get("state_code")),
        "country_code": _as_str(raw.get("country_code")),
        "country_name": _as_str(raw.get("country_name")),
        "display_name": display_name,
        "latitude": _as_float(raw.get("latitude")),
        "longitude": _as_float(raw.get("longitude")),
        "type": _as_str(raw.get("type")),
    }


def _map_job_item(raw: dict[str, Any]) -> dict[str, Any]:
    theirstack_job_id = _as_int(raw.get("id"))
    hiring_team_raw = _as_list(raw.get("hiring_team"))
    hiring_team: list[dict[str, Any]] = []
    for item in hiring_team_raw:
        mapped_item = _map_hiring_team_item(_as_dict(item))
        if mapped_item:
            hiring_team.append(mapped_item)
    locations_raw = _as_list(raw.get("locations"))
    locations: list[dict[str, Any]] = []
    for item in locations_raw:
        mapped_item = _map_location_item(_as_dict(item))
        if mapped_item:
            locations.append(mapped_item)

    return {
        "job_id": theirstack_job_id,
        "theirstack_job_id": theirstack_job_id,
        "job_title": _as_str(raw.get("job_title")),
        "normalized_title": _as_str(raw.get("normalized_title")),
        "company_name": _as_str(raw.get("company")),
        "company_domain": _as_str(raw.get("company_domain")),
        "url": _as_str(raw.get("url")),
        "final_url": _as_str(raw.get("final_url")),
        "source_url": _as_str(raw.get("source_url")),
        "date_posted": _as_str(raw.get("date_posted")),
        "discovered_at": _as_str(raw.get("discovered_at")),
        "reposted": raw.get("reposted") if isinstance(raw.get("reposted"), bool) else None,
        "date_reposted": _as_str(raw.get("date_reposted")),
        "location": _as_str(raw.get("location")),
        "short_location": _as_str(raw.get("short_location")),
        "long_location": _as_str(raw.get("long_location")),
        "state_code": _as_str(raw.get("state_code")),
        "postal_code": _as_str(raw.get("postal_code")),
        "latitude": _as_float(raw.get("latitude")),
        "longitude": _as_float(raw.get("longitude")),
        "cities": _as_str_list(raw.get("cities")),
        "locations": locations or None,
        "country": _as_str(raw.get("country")),
        "country_code": _as_str(raw.get("country_code")),
        "countries": _as_str_list(raw.get("countries")),
        "country_codes": _as_str_list(raw.get("country_codes")),
        "remote": raw.get("remote") if isinstance(raw.get("remote"), bool) else None,
        "hybrid": raw.get("hybrid") if isinstance(raw.get("hybrid"), bool) else None,
        "seniority": _as_str(raw.get("seniority")),
        "employment_statuses": _as_str_list(raw.get("employment_statuses")),
        "easy_apply": raw.get("easy_apply") if isinstance(raw.get("easy_apply"), bool) else None,
        "salary_string": _as_str(raw.get("salary_string")),
        "min_annual_salary_usd": _as_float(raw.get("min_annual_salary_usd")),
        "max_annual_salary_usd": _as_float(raw.get("max_annual_salary_usd")),
        "avg_annual_salary_usd": _as_float(raw.get("avg_annual_salary_usd")),
        "salary_currency": _as_str(raw.get("salary_currency")),
        "description": _as_str(raw.get("description")),
        "technology_slugs": _as_str_list(raw.get("technology_slugs")),
        "hiring_team": hiring_team or None,
        "company_object": _map_company_object(_as_dict(raw.get("company_object"))),
        "manager_roles": _as_str_list(raw.get("manager_roles")),
    }


def _map_hiring_team_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    full_name = _as_str(raw.get("full_name"))
    linkedin_url = _as_str(raw.get("linkedin_url"))
    if not full_name and not linkedin_url:
        return None

    return {
        "full_name": full_name,
        "first_name": _as_str(raw.get("first_name")),
        "linkedin_url": linkedin_url,
        "role": _as_str(raw.get("role")),
        "image_url": _as_str(raw.get("image_url")),
    }


def _map_company_object(raw: dict[str, Any]) -> dict[str, Any] | None:
    name = _as_str(raw.get("name"))
    domain = _as_str(raw.get("domain"))
    if not name and not domain:
        return None

    return {
        "theirstack_company_id": _as_str(raw.get("id")),
        "name": name,
        "domain": domain,
        "industry": _as_str(raw.get("industry")),
        "country": _as_str(raw.get("country")),
        "employee_count": _as_int(raw.get("employee_count")),
        "employee_count_range": _as_str(raw.get("employee_count_range")),
        "logo": _as_str(raw.get("logo")),
        "linkedin_url": _as_str(raw.get("linkedin_url")),
        "num_jobs": _as_int(raw.get("num_jobs")),
        "num_jobs_last_30_days": _as_int(raw.get("num_jobs_last_30_days")),
        "founded_year": _as_int(raw.get("founded_year")),
        "annual_revenue_usd": _as_float(raw.get("annual_revenue_usd")),
        "total_funding_usd": _as_int(raw.get("total_funding_usd")),
        "last_funding_round_date": _as_str(raw.get("last_funding_round_date")),
        "funding_stage": _as_str(raw.get("funding_stage")),
        "city": _as_str(raw.get("city")),
        "long_description": _as_str(raw.get("long_description")),
        "publicly_traded_symbol": _as_str(raw.get("publicly_traded_symbol")),
        "publicly_traded_exchange": _as_str(raw.get("publicly_traded_exchange")),
        "technology_slugs": _as_str_list(raw.get("technology_slugs")),
        "technology_names": _as_str_list(raw.get("technology_names")),
    }


def _map_tech_item(raw: dict[str, Any]) -> dict[str, Any] | None:
    technology = _as_dict(raw.get("technology"))
    name = _as_str(technology.get("name"))
    if not name:
        return None

    return {
        "name": name,
        "slug": _as_str(technology.get("slug")),
        "category": _as_str(technology.get("category")),
        "confidence": _as_str(raw.get("confidence")),
        "jobs": _as_int(raw.get("jobs")),
        "jobs_last_30_days": _as_int(raw.get("jobs_last_30_days")),
        "first_date_found": _as_str(raw.get("first_date_found")),
        "last_date_found": _as_str(raw.get("last_date_found")),
        "rank_within_category": _as_int(raw.get("rank_within_category")),
    }


async def search_companies(
    *,
    api_key: str | None,
    filters: dict[str, Any],
    limit: int,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_companies",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    payload = {**_as_dict(filters), "limit": max(limit, 1)}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_BASE_URL}/v1/companies/search",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_companies",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    response_body = _as_dict(body)
    mapped_results = [_map_company_item(_as_dict(item)) for item in _as_list(response_body.get("data"))]
    result_count = len(mapped_results)
    return {
        "attempt": {
            "provider": "theirstack",
            "action": "search_companies",
            "status": "found" if result_count else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"results": mapped_results, "result_count": result_count},
    }


async def search_jobs(
    *,
    api_key: str | None,
    filters: dict[str, Any],
    limit: int,
    offset: int = 0,
    page: int | None = None,
    cursor: str | None = None,
    include_total_results: bool = False,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_jobs",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    payload: dict[str, Any] = {**_as_dict(filters), "limit": max(limit, 1)}
    if offset != 0:
        payload["offset"] = offset
    if page is not None:
        payload["page"] = page
    if cursor is not None:
        payload["cursor"] = cursor
    if include_total_results:
        payload["include_total_results"] = True
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_BASE_URL}/v1/jobs/search",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "search_jobs",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    response_body = _as_dict(body)
    mapped_results = [_map_job_item(_as_dict(item)) for item in _as_list(response_body.get("data"))]
    result_count = len(mapped_results)
    metadata = _as_dict(response_body.get("metadata"))
    return {
        "attempt": {
            "provider": "theirstack",
            "action": "search_jobs",
            "status": "found" if result_count else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": mapped_results,
            "result_count": result_count,
            "total_results": _as_int(metadata.get("total_results")),
            "total_companies": _as_int(metadata.get("total_companies")),
        },
    }


async def get_technographics(
    *,
    api_key: str | None,
    company_domain: str | None,
    company_name: str | None,
    company_linkedin_url: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "technographics",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"technologies": [], "technology_count": 0},
        }

    payload: dict[str, Any] = {}
    if _as_str(company_domain):
        payload["company_domain"] = _as_str(company_domain)
    if _as_str(company_name):
        payload["company_name"] = _as_str(company_name)
    if _as_str(company_linkedin_url):
        payload["company_linkedin_url"] = _as_str(company_linkedin_url)

    if not payload:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "technographics",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"technologies": [], "technology_count": 0},
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{_BASE_URL}/v1/companies/technographics",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "technographics",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"technologies": [], "technology_count": 0},
        }

    response_body = _as_dict(body)
    mapped_technologies: list[dict[str, Any]] = []
    for item in _as_list(response_body.get("data")):
        mapped_item = _map_tech_item(_as_dict(item))
        if mapped_item:
            mapped_technologies.append(mapped_item)

    technology_count = len(mapped_technologies)
    return {
        "attempt": {
            "provider": "theirstack",
            "action": "technographics",
            "status": "found" if technology_count else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"technologies": mapped_technologies, "technology_count": technology_count},
    }


async def enrich_hiring_signals(
    *,
    api_key: str | None,
    company_domain: str | None,
) -> ProviderAdapterResult:
    normalized_domain = _as_str(company_domain)
    if not normalized_domain:
        return {
            "attempt": {
                "provider": "theirstack",
                "action": "enrich_hiring_signals",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    result = await search_companies(
        api_key=api_key,
        filters={"company_domain_or": [normalized_domain]},
        limit=1,
    )

    mapped = _as_dict(result.get("mapped"))
    results = _as_list(mapped.get("results"))
    first_company = _as_dict(results[0]) if results else {}

    recent_job_titles: list[str] = []
    raw_response = _as_dict(_as_dict(result.get("attempt")).get("raw_response"))
    raw_data = _as_list(raw_response.get("data"))
    first_raw_company = _as_dict(raw_data[0]) if raw_data else {}
    for job in _as_list(first_raw_company.get("jobs_found")):
        title = _as_str(_as_dict(job).get("job_title"))
        if title:
            recent_job_titles.append(title)

    return {
        "attempt": {
            **_as_dict(result.get("attempt")),
            "action": "enrich_hiring_signals",
        },
        "mapped": {
            "company_name": first_company.get("company_name"),
            "domain": first_company.get("domain"),
            "num_jobs": first_company.get("num_jobs"),
            "num_jobs_last_30_days": first_company.get("num_jobs_last_30_days"),
            "technology_slugs": first_company.get("technology_slugs"),
            "recent_job_titles": recent_job_titles or None,
        }
        if first_company
        else None,
    }
