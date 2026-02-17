from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.search import CompanySearchOutput, PersonSearchOutput
from app.providers import blitzapi, companyenrich, prospeo


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


async def _search_companies_prospeo(
    *,
    query: str | None,
    page: int,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await prospeo.search_companies(
        api_key=settings.prospeo_api_key,
        query=query,
        page=page,
        provider_filters=provider_filters,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


async def _search_companies_blitzapi(
    *,
    query: str | None,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    blitz_input = (provider_filters or {}).get("blitzapi") or {}
    linkedin_url = blitz_input.get("company_linkedin_url")
    domain = blitz_input.get("company_domain") or _domain_from_value(query)
    if not linkedin_url and domain:
        bridge = await blitzapi.domain_to_linkedin(
            api_key=settings.blitzapi_api_key,
            domain=domain,
        )
        attempts.append(bridge["attempt"])
        linkedin_url = (bridge.get("mapped") or {}).get("company_linkedin_url")
    result = await blitzapi.company_search(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=linkedin_url,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


async def _search_companies_companyenrich(
    *,
    query: str | None,
    page: int,
    page_size: int,
    attempts: list[dict[str, Any]],
    provider_filters: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await companyenrich.search_companies(
        api_key=settings.companyenrich_api_key,
        query=query,
        page=page,
        page_size=page_size,
        provider_filters=provider_filters,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


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
    output = CompanySearchOutput.model_validate(
        {
            "results": deduped,
            "result_count": len(deduped),
            "provider_order_used": _company_search_provider_order(),
            "pagination": pagination_by_provider,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "company.search",
        "status": "found" if deduped else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }



def _person_search_provider_order() -> list[str]:
    settings = get_settings()
    parsed = [item.strip() for item in settings.person_search_order.split(",") if item.strip()]
    allowed = {"prospeo", "blitzapi", "companyenrich"}
    filtered = [item for item in parsed if item in allowed]
    return filtered or ["prospeo", "blitzapi", "companyenrich"]


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
    result = await prospeo.search_people(
        api_key=settings.prospeo_api_key,
        query=query,
        page=page,
        company_domain=company_domain,
        company_name=company_name,
        provider_filters=provider_filters,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


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
    blitz_input = (provider_filters or {}).get("blitzapi") or {}
    linkedin_url = blitz_input.get("company_linkedin_url") or company_linkedin_url
    domain = blitz_input.get("company_domain") or company_domain
    if not linkedin_url and domain:
        bridge = await blitzapi.domain_to_linkedin(api_key=settings.blitzapi_api_key, domain=domain)
        attempts.append(bridge["attempt"])
        linkedin_url = (bridge.get("mapped") or {}).get("company_linkedin_url")
    result = await blitzapi.person_search(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=linkedin_url,
        query=query,
        limit=limit,
        blitz_input=blitz_input,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


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
    result = await companyenrich.search_people(
        api_key=settings.companyenrich_api_key,
        query=query,
        page=page,
        page_size=page_size,
        company_domain=company_domain,
        company_name=company_name,
        provider_filters=provider_filters,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


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
    output = PersonSearchOutput.model_validate(
        {
            "results": deduped,
            "result_count": len(deduped),
            "provider_order_used": _person_search_provider_order(),
            "pagination": pagination_by_provider,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "person.search",
        "status": "found" if deduped else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }
