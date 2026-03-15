from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.contracts.intent_search import EnumResolutionDetail
from app.providers import blitzapi, prospeo
from app.services.enum_registry.resolver import resolve_enum, ResolveResult

logger = logging.getLogger(__name__)

ENUM_FIELDS = {
    "seniority",
    "department",
    "industry",
    "employee_range",
    "company_type",
    "continent",
    "sales_region",
    "country_code",
}

PASS_THROUGH_FIELDS = {
    "query",
    "company_domain",
    "company_name",
    "company_linkedin_url",
    "job_title",
    "location",
}

_PROVIDER_ORDER: dict[str, list[str]] = {
    "people": ["prospeo", "blitzapi"],
    "companies": ["prospeo", "blitzapi"],
}


def _resolve_enum_criteria(
    provider_name: str,
    enum_criteria: dict[str, str | list[str]],
) -> tuple[dict[str, list[ResolveResult]], dict[str, EnumResolutionDetail], list[str]]:
    """Resolve enum fields for a provider, handling both str and list values.

    Returns (resolved_map, resolution_details, unresolved_fields).
    resolved_map: field -> list of ResolveResults with non-None values
    """
    resolved_map: dict[str, list[ResolveResult]] = {}
    resolution_details: dict[str, EnumResolutionDetail] = {}
    unresolved: list[str] = []

    for field, raw_value in enum_criteria.items():
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        field_results: list[ResolveResult] = []

        for val in values:
            result = resolve_enum(provider_name, field, val)
            if result.value is not None:
                field_results.append(result)

        if field_results:
            resolved_map[field] = field_results
            first = field_results[0]
            resolution_details[field] = EnumResolutionDetail(
                input_value=values[0] if len(values) == 1 else str(values),
                resolved_value=(
                    first.value
                    if len(field_results) == 1
                    else str([r.value for r in field_results])
                ),
                provider_field=first.provider_field,
                match_type=first.match_type,
                confidence=first.confidence,
            )
        else:
            unresolved.append(field)
            last_val = values[-1]
            no_match = resolve_enum(provider_name, field, last_val)
            resolution_details[field] = EnumResolutionDetail(
                input_value=last_val if len(values) == 1 else str(values),
                resolved_value=None,
                provider_field=no_match.provider_field,
                match_type=no_match.match_type,
                confidence=no_match.confidence,
            )

    return resolved_map, resolution_details, unresolved


def _resolved_values(
    resolved_map: dict[str, list[ResolveResult]],
    field: str,
) -> list[str] | None:
    """Get the list of resolved string values for a field, or None."""
    results = resolved_map.get(field)
    if not results:
        return None
    return [r.value for r in results if r.value]


def _resolved_single(
    resolved_map: dict[str, list[ResolveResult]],
    field: str,
) -> str | None:
    """Get a single resolved value for a field."""
    vals = _resolved_values(resolved_map, field)
    return vals[0] if vals else None


def _build_prospeo_person_filters(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
) -> dict[str, Any]:
    filters: dict[str, Any] = {}

    seniority = _resolved_values(resolved_map, "seniority")
    if seniority:
        filters["person_seniority"] = {"include": seniority}

    department = _resolved_values(resolved_map, "department")
    if department:
        filters["person_department"] = {"include": department}

    industry = _resolved_values(resolved_map, "industry")
    if industry:
        filters.setdefault("company", {})["industry"] = {"include": industry}

    employee_range = _resolved_values(resolved_map, "employee_range")
    if employee_range:
        filters.setdefault("company", {})["employee_range"] = {"include": employee_range}

    job_title = pass_through.get("job_title")
    if job_title:
        titles = job_title if isinstance(job_title, list) else [job_title]
        filters["person_job_title"] = {"include": titles}

    location = pass_through.get("location")
    if location:
        locs = location if isinstance(location, list) else [location]
        filters["person_location_search"] = {"include": locs}

    company_domain = pass_through.get("company_domain")
    company_name = pass_through.get("company_name")
    if company_domain:
        domain_val = company_domain if isinstance(company_domain, str) else company_domain[0]
        filters.setdefault("company", {}).setdefault("websites", {})["include"] = [domain_val]
    elif company_name:
        name_val = company_name if isinstance(company_name, str) else company_name[0]
        filters.setdefault("company", {}).setdefault("names", {})["include"] = [name_val]

    return filters


def _build_prospeo_company_filters(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
) -> dict[str, Any]:
    filters: dict[str, Any] = {}

    industry = _resolved_values(resolved_map, "industry")
    if industry:
        filters.setdefault("company", {})["industry"] = {"include": industry}

    employee_range = _resolved_values(resolved_map, "employee_range")
    if employee_range:
        filters.setdefault("company", {})["employee_range"] = {"include": employee_range}

    company_domain = pass_through.get("company_domain")
    company_name = pass_through.get("company_name")
    if company_domain:
        domain_val = company_domain if isinstance(company_domain, str) else company_domain[0]
        filters.setdefault("company", {}).setdefault("websites", {})["include"] = [domain_val]
    elif company_name:
        name_val = company_name if isinstance(company_name, str) else company_name[0]
        filters.setdefault("company", {}).setdefault("names", {})["include"] = [name_val]

    return filters


def _build_blitzapi_company_filters(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
) -> dict[str, Any]:
    company_filters: dict[str, Any] = {}

    industry = _resolved_values(resolved_map, "industry")
    if industry:
        company_filters["industry"] = {"include": industry}

    employee_range = _resolved_values(resolved_map, "employee_range")
    if employee_range:
        company_filters["employee_range"] = employee_range

    company_type = _resolved_values(resolved_map, "company_type")
    if company_type:
        company_filters["type"] = {"include": company_type}

    continent = _resolved_values(resolved_map, "continent")
    if continent:
        company_filters.setdefault("hq", {})["continent"] = continent

    country_code = _resolved_values(resolved_map, "country_code")
    if country_code:
        company_filters.setdefault("hq", {})["country_code"] = country_code

    sales_region = _resolved_values(resolved_map, "sales_region")
    if sales_region:
        company_filters.setdefault("hq", {})["sales_region"] = sales_region

    query = pass_through.get("query")
    company_name = pass_through.get("company_name")
    keyword = query or company_name
    if keyword:
        kw_val = keyword if isinstance(keyword, str) else keyword[0]
        company_filters["keywords"] = {"include": [kw_val]}

    company_domain = pass_through.get("company_domain")
    if company_domain:
        domain_val = company_domain if isinstance(company_domain, str) else company_domain[0]
        company_filters["website"] = {"include": [domain_val]}

    return company_filters


def _str_val(val: str | list[str] | None) -> str | None:
    if val is None:
        return None
    if isinstance(val, list):
        return val[0] if val else None
    return val


async def _try_prospeo_people(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
    page: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    settings = get_settings()
    filters = _build_prospeo_person_filters(resolved_map, pass_through)
    query = _str_val(pass_through.get("job_title")) or _str_val(pass_through.get("query"))
    result = await prospeo.search_people(
        api_key=settings.prospeo_api_key,
        query=query,
        page=page,
        company_domain=None,
        company_name=None,
        provider_filters={"prospeo": filters} if filters else None,
    )
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination"), result["attempt"]


async def _try_prospeo_companies(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
    page: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    settings = get_settings()
    filters = _build_prospeo_company_filters(resolved_map, pass_through)
    query = _str_val(pass_through.get("query")) or _str_val(pass_through.get("company_name"))
    result = await prospeo.search_companies(
        api_key=settings.prospeo_api_key,
        query=query,
        page=page,
        provider_filters={"prospeo": filters} if filters else None,
    )
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination"), result["attempt"]


async def _try_blitzapi_people(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
    limit: int,
    page: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    settings = get_settings()
    result = await blitzapi.search_employees(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=_str_val(pass_through.get("company_linkedin_url")),
        job_level=_resolved_values(resolved_map, "seniority"),
        job_function=_resolved_values(resolved_map, "department"),
        country_code=_resolved_values(resolved_map, "country_code"),
        max_results=limit,
        page=page,
    )
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination"), result["attempt"]


async def _try_blitzapi_companies(
    resolved_map: dict[str, list[ResolveResult]],
    pass_through: dict[str, str | list[str]],
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, dict[str, Any]]:
    settings = get_settings()
    company_filters = _build_blitzapi_company_filters(resolved_map, pass_through)
    result = await blitzapi.search_companies(
        api_key=settings.blitzapi_api_key,
        company_filters=company_filters if company_filters else None,
        max_results=limit,
    )
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination"), result["attempt"]


async def execute_intent_search(
    *,
    search_type: str,
    criteria: dict[str, str | list[str]],
    provider: str | None,
    limit: int,
    page: int,
) -> dict[str, Any]:
    # Separate criteria into enum and pass-through
    enum_criteria: dict[str, str | list[str]] = {}
    pass_through: dict[str, str | list[str]] = {}
    for key, value in criteria.items():
        if key in ENUM_FIELDS:
            enum_criteria[key] = value
        elif key in PASS_THROUGH_FIELDS:
            pass_through[key] = value

    # Determine provider order
    if provider:
        provider_order = [provider]
    else:
        provider_order = list(_PROVIDER_ORDER.get(search_type, ["prospeo", "blitzapi"]))

    all_attempts: list[dict[str, Any]] = []
    last_resolution_details: dict[str, EnumResolutionDetail] = {}
    last_unresolved: list[str] = []

    for prov in provider_order:
        # Resolve enums for this provider
        resolved_map, resolution_details, unresolved = _resolve_enum_criteria(
            prov, enum_criteria
        )
        last_resolution_details = resolution_details
        last_unresolved = unresolved

        # Check if there's anything usable
        has_enum_filters = bool(resolved_map)
        has_pass_through = bool(pass_through)
        if not has_enum_filters and not has_pass_through:
            continue

        try:
            if search_type == "people":
                if prov == "prospeo":
                    results, pagination, attempt = await _try_prospeo_people(
                        resolved_map, pass_through, page
                    )
                elif prov == "blitzapi":
                    results, pagination, attempt = await _try_blitzapi_people(
                        resolved_map, pass_through, limit, page
                    )
                else:
                    continue
            else:  # companies
                if prov == "prospeo":
                    results, pagination, attempt = await _try_prospeo_companies(
                        resolved_map, pass_through, page
                    )
                elif prov == "blitzapi":
                    results, pagination, attempt = await _try_blitzapi_companies(
                        resolved_map, pass_through, limit
                    )
                else:
                    continue

            all_attempts.append(attempt)

            if results:
                return {
                    "search_type": search_type,
                    "provider_used": prov,
                    "results": results,
                    "result_count": len(results),
                    "enum_resolution": {
                        k: v.model_dump() for k, v in resolution_details.items()
                    },
                    "unresolved_fields": unresolved,
                    "pagination": pagination,
                    "provider_attempts": all_attempts,
                }
        except Exception:
            logger.exception("Intent search provider %s failed", prov)
            all_attempts.append({
                "provider": prov,
                "action": "intent_search",
                "status": "failed",
            })

    # No provider returned results
    provider_used = provider_order[0] if provider_order else "none"
    return {
        "search_type": search_type,
        "provider_used": provider_used,
        "results": [],
        "result_count": 0,
        "enum_resolution": {
            k: v.model_dump() for k, v in last_resolution_details.items()
        },
        "unresolved_fields": last_unresolved,
        "pagination": None,
        "provider_attempts": all_attempts,
    }
