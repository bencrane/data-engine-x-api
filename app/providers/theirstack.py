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


def _map_job_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "job_id": _as_int(raw.get("id")),
        "job_title": _as_str(raw.get("job_title")),
        "company_name": _as_str(raw.get("company")),
        "company_domain": _as_str(raw.get("company_domain")),
        "url": _as_str(raw.get("url")),
        "date_posted": _as_str(raw.get("date_posted")),
        "location": _as_str(raw.get("location")),
        "seniority": _as_str(raw.get("seniority")),
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

    payload = {**_as_dict(filters), "limit": max(limit, 1)}
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
    return {
        "attempt": {
            "provider": "theirstack",
            "action": "search_jobs",
            "status": "found" if result_count else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {"results": mapped_results, "result_count": result_count},
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
