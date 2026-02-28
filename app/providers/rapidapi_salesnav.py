from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_PROVIDER = "rapidapi_salesnav"
_ENDPOINT = "https://realtime-linkedin-sales-navigator-data.p.rapidapi.com/premium_search_person_via_url"
_HOST = "realtime-linkedin-sales-navigator-data.p.rapidapi.com"
_TIMEOUT_SECONDS = 30.0


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any, *, default: int, minimum: int = 1) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return parsed if parsed >= minimum else minimum


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _map_person(raw: dict[str, Any]) -> dict[str, Any]:
    current = _as_dict(raw.get("currentPosition"))
    company_urn = _as_dict(current.get("companyUrnResolutionResult"))
    started_on = _as_dict(current.get("startedOn"))
    tenure_position = _as_dict(current.get("tenureAtPosition"))
    tenure_company = _as_dict(current.get("tenureAtCompany"))

    return {
        "full_name": raw.get("fullName"),
        "first_name": raw.get("firstName"),
        "last_name": raw.get("lastName"),
        "linkedin_url": raw.get("navigationUrl"),
        "profile_urn": raw.get("profileUrn"),
        "geo_region": raw.get("geoRegion"),
        "summary": raw.get("summary"),
        "current_title": current.get("title"),
        "current_company_name": current.get("companyName"),
        "current_company_id": current.get("companyId"),
        "current_company_industry": company_urn.get("industry"),
        "current_company_location": company_urn.get("location"),
        "position_start_month": started_on.get("month"),
        "position_start_year": started_on.get("year"),
        "tenure_at_position_years": tenure_position.get("numYears"),
        "tenure_at_position_months": tenure_position.get("numMonths"),
        "tenure_at_company_years": tenure_company.get("numYears"),
        "tenure_at_company_months": tenure_company.get("numMonths"),
        "open_link": raw.get("openLink"),
    }


async def scrape_sales_nav_url(
    *,
    api_key: str | None,
    sales_nav_url: str,
    page: int = 1,
    account_number: int = 1,
) -> ProviderAdapterResult:
    normalized_api_key = _as_non_empty_str(api_key)
    if not normalized_api_key:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "scrape_sales_nav_url",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_url = _as_non_empty_str(sales_nav_url)
    if not normalized_url:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "scrape_sales_nav_url",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    normalized_page = _as_int(page, default=1, minimum=1)
    normalized_account_number = _as_int(account_number, default=1, minimum=1)
    headers = {
        "x-rapidapi-host": _HOST,
        "x-rapidapi-key": normalized_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "page": normalized_page,
        "url": normalized_url,
        "account_number": normalized_account_number,
    }
    start_ms = now_ms()

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            response = await client.post(_ENDPOINT, headers=headers, json=payload)
            body = parse_json_or_raw(response.text, response.json)
    except httpx.TimeoutException:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "scrape_sales_nav_url",
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
                "action": "scrape_sales_nav_url",
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
                "action": "scrape_sales_nav_url",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    parsed_body = _as_dict(body)
    response_obj = _as_dict(parsed_body.get("response"))
    data = [item for item in _as_list(response_obj.get("data")) if isinstance(item, dict)]
    pagination = _as_dict(response_obj.get("pagination"))
    success_flag = parsed_body.get("success")

    if success_flag is False or not data:
        return {
            "attempt": {
                "provider": _PROVIDER,
                "action": "scrape_sales_nav_url",
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": duration_ms,
                "raw_response": parsed_body,
            },
            "mapped": {
                "results": [],
                "result_count": 0,
                "total_available": pagination.get("total"),
                "page": normalized_page,
                "source_url": normalized_url,
            },
        }

    return {
        "attempt": {
            "provider": _PROVIDER,
            "action": "scrape_sales_nav_url",
            "status": "found",
            "http_status": response.status_code,
            "duration_ms": duration_ms,
            "raw_response": parsed_body,
        },
        "mapped": {
            "results": [_map_person(person) for person in data],
            "result_count": len(data),
            "total_available": pagination.get("total"),
            "page": normalized_page,
            "source_url": normalized_url,
        },
    }
