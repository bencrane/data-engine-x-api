from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.search import CompanySearchOutput, EcommerceSearchOutput, FMCSACarrierSearchOutput, PersonSearchOutput
from app.providers import blitzapi, companyenrich, fmcsa, leadmagic, prospeo, storeleads_search


def _domain_from_value(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
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


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(
    value: Any,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None and parsed < minimum:
        parsed = minimum
    if maximum is not None and parsed > maximum:
        parsed = maximum
    return parsed


def _as_non_empty_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    for item in value:
        parsed = _as_non_empty_str(item)
        if parsed:
            cleaned.append(parsed)
    return cleaned or None


def _as_non_empty_str_or_list(value: Any) -> str | list[str] | None:
    parsed_str = _as_non_empty_str(value)
    if parsed_str:
        return parsed_str
    return _as_non_empty_str_list(value)


def _as_int_or_none(value: Any) -> int | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_list_of_dicts(value: Any) -> list[dict[str, Any]] | None:
    if not isinstance(value, list):
        return None
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            cleaned.append(item)
    return cleaned or None


def _person_provider_filters(input_data: dict[str, Any]) -> dict[str, Any] | None:
    raw = input_data.get("provider_filters")
    if not isinstance(raw, dict):
        return None
    sanitized = {
        key: value
        for key, value in raw.items()
        if key in {"prospeo", "blitzapi", "companyenrich", "leadmagic"} and isinstance(value, dict)
    }
    return sanitized or None


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


def _first_present(input_data: dict[str, Any], step_config: dict[str, Any], key: str) -> Any:
    direct = input_data.get(key)
    if direct is not None:
        return direct
    return step_config.get(key)


def _extract_ecommerce_filters(input_data: dict[str, Any], step_config: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": _as_non_empty_str(_first_present(input_data, step_config, "platform")),
        "country_code": _as_non_empty_str(_first_present(input_data, step_config, "country_code")),
        "app_installed": _as_non_empty_str(_first_present(input_data, step_config, "app_installed")),
        "category": _as_non_empty_str(_first_present(input_data, step_config, "category")),
        "domain_state": _as_non_empty_str(_first_present(input_data, step_config, "domain_state")) or "Active",
        "rank_min": _as_int_or_none(_first_present(input_data, step_config, "rank_min")),
        "rank_max": _as_int_or_none(_first_present(input_data, step_config, "rank_max")),
        "monthly_app_spend_min": _as_int_or_none(_first_present(input_data, step_config, "monthly_app_spend_min")),
        "monthly_app_spend_max": _as_int_or_none(_first_present(input_data, step_config, "monthly_app_spend_max")),
        "page": _as_int_or_none(_first_present(input_data, step_config, "page")) or 0,
        "page_size": min(max(_as_int_or_none(_first_present(input_data, step_config, "page_size")) or 50, 1), 50),
    }


async def execute_company_search_ecommerce(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    step_config = _as_dict(input_data.get("step_config"))
    filters = _extract_ecommerce_filters(input_data, step_config)

    if not (filters.get("platform") or filters.get("category") or filters.get("app_installed")):
        return {
            "run_id": run_id,
            "operation_id": "company.search.ecommerce",
            "status": "failed",
            "missing_inputs": ["platform|category|app_installed"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await storeleads_search.search_ecommerce(
        api_key=settings.storeleads_api_key,
        filters=filters,
    )
    attempts.append(provider_result["attempt"])
    mapped = provider_result.get("mapped") or {"results": [], "result_count": 0}
    mapped_results = mapped.get("results") or []
    canonical_results = [
        {
            "merchant_name": result.get("merchant_name"),
            "domain": result.get("domain"),
            "ecommerce_platform": result.get("platform"),
            "ecommerce_plan": result.get("plan"),
            "estimated_monthly_sales_cents": result.get("estimated_monthly_sales_cents"),
            "global_rank": result.get("rank"),
            "country_code": result.get("country_code"),
            "description": result.get("description"),
            "source_provider": "storeleads",
        }
        for result in mapped_results
        if isinstance(result, dict)
    ]

    try:
        output = EcommerceSearchOutput.model_validate(
            {
                "results": canonical_results,
                "result_count": len(canonical_results),
                "page": filters["page"],
                "source_provider": "storeleads",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.search.ecommerce",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    status_from_attempt = provider_result["attempt"].get("status")
    final_status = "not_found" if not canonical_results else "found"
    if status_from_attempt == "failed":
        final_status = "failed"
    return {
        "run_id": run_id,
        "operation_id": "company.search.ecommerce",
        "status": final_status,
        "output": output,
        "provider_attempts": attempts,
    }


def _first_non_empty_string(values: list[Any]) -> str | None:
    for value in values:
        parsed = _as_non_empty_str(value)
        if parsed:
            return parsed
    return None


def _extract_carrier_name(input_data: dict[str, Any]) -> str | None:
    direct = _first_non_empty_string([input_data.get("carrier_name"), input_data.get("company_name")])
    if direct:
        return direct

    company_profile = _as_dict(input_data.get("company_profile"))
    from_profile = _first_non_empty_string(
        [
            company_profile.get("carrier_name"),
            company_profile.get("company_name"),
            company_profile.get("legal_name"),
        ]
    )
    if from_profile:
        return from_profile

    output = _as_dict(input_data.get("output"))
    return _first_non_empty_string(
        [
            output.get("carrier_name"),
            output.get("company_name"),
            output.get("legal_name"),
        ]
    )


async def execute_company_search_fmcsa(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    step_config = _as_dict(input_data.get("step_config"))
    carrier_name = _extract_carrier_name(input_data)
    max_results = _as_int(step_config.get("max_results"), default=50, minimum=1, maximum=50)

    if not carrier_name:
        return {
            "run_id": run_id,
            "operation_id": "company.search.fmcsa",
            "status": "failed",
            "missing_inputs": ["carrier_name|company_name"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    adapter_result = await fmcsa.search_carriers(
        api_key=settings.fmcsa_api_key,
        name=carrier_name,
        max_results=max_results,
    )
    attempts.append(adapter_result["attempt"])
    mapped = adapter_result.get("mapped") or {"results": [], "result_count": 0}

    try:
        output = FMCSACarrierSearchOutput.model_validate(
            {
                **mapped,
                "source_provider": "fmcsa",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.search.fmcsa",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    return {
        "run_id": run_id,
        "operation_id": "company.search.fmcsa",
        "status": adapter_result["attempt"].get("status", "failed"),
        "output": output,
        "provider_attempts": attempts,
    }



def _person_search_provider_order() -> list[str]:
    settings = get_settings()
    parsed = [item.strip() for item in settings.person_search_order.split(",") if item.strip()]
    allowed = {"prospeo", "blitzapi", "companyenrich", "leadmagic"}
    filtered = [item for item in parsed if item in allowed]
    if "leadmagic" not in filtered:
        filtered.append("leadmagic")
    return filtered or ["prospeo", "blitzapi", "companyenrich", "leadmagic"]


def _as_list_from_str_or_list(value: str | list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    return value or None


def _country_codes_from_location(location: str | list[str] | None) -> list[str] | None:
    values = _as_list_from_str_or_list(location)
    if not values:
        return None
    country_codes: list[str] = []
    for value in values:
        token = value.strip().upper()
        if len(token) == 2 and token.isalpha():
            country_codes.append(token)
    return country_codes or None


def _title_to_blitz_job_levels(job_title: str | None) -> list[str] | None:
    if not job_title:
        return None
    normalized = job_title.lower()
    if any(token in normalized for token in ("chief ", " cxo", " ceo", " cfo", " coo", " cmo", " cto", " cio", "founder", "owner", "president")):
        return ["C-Team"]
    if "vp" in normalized or "vice president" in normalized:
        return ["VP"]
    if "director" in normalized or normalized.startswith("head ") or " head of " in normalized:
        return ["Director"]
    if "manager" in normalized:
        return ["Manager"]
    return None


def _merge_dict(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def _build_prospeo_filters(
    *,
    query: str | None,
    job_title: str | None,
    company_domain: str | None,
    company_name: str | None,
    location: str | list[str] | None,
    provider_filters: dict[str, Any] | None,
) -> dict[str, Any] | None:
    existing = ((provider_filters or {}).get("prospeo") or {}) if isinstance((provider_filters or {}).get("prospeo"), dict) else {}
    computed: dict[str, Any] = {}
    title_query = job_title or query
    if title_query:
        computed["person_job_title"] = {"include": [title_query]}
    location_values = _as_list_from_str_or_list(location)
    if location_values:
        computed["person_location_search"] = {"include": location_values}
    if company_domain:
        computed.setdefault("company", {}).setdefault("websites", {})["include"] = [company_domain]
    elif company_name:
        computed.setdefault("company", {}).setdefault("names", {})["include"] = [company_name]
    if not existing and not computed:
        return None
    return _merge_dict(existing, computed)


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
    company_linkedin_url: str | None,
    job_level: str | list[str] | None,
    job_function: str | list[str] | None,
    country_code: str | list[str] | None,
    max_results: int,
    page: int,
    attempts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await blitzapi.search_employees(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=company_linkedin_url,
        job_level=job_level,
        job_function=job_function,
        country_code=country_code,
        max_results=max_results,
        page=page,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


async def _search_people_blitzapi_waterfall(
    *,
    company_linkedin_url: str | None,
    cascade: list[dict[str, Any]] | None,
    max_results: int,
    attempts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await blitzapi.search_icp_waterfall(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=company_linkedin_url,
        cascade=cascade,
        max_results=max_results,
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


async def _search_people_leadmagic_employees(
    *,
    company_domain: str | None,
    company_name: str | None,
    max_results: int,
    attempts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await leadmagic.search_employees(
        api_key=settings.leadmagic_api_key,
        company_domain=company_domain,
        company_name=company_name,
        limit=max_results,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("results") or [], mapped.get("pagination")


async def _search_people_leadmagic_role(
    *,
    company_domain: str | None,
    company_name: str | None,
    job_title: str | None,
    attempts: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    settings = get_settings()
    result = await leadmagic.search_by_role(
        api_key=settings.leadmagic_api_key,
        company_domain=company_domain,
        company_name=company_name,
        job_title=job_title,
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
    query = _as_non_empty_str(input_data.get("query"))
    page = _as_int(input_data.get("page"), default=1, minimum=1)
    limit = _as_int(input_data.get("limit"), default=100, minimum=1)
    max_results = _as_int(input_data.get("max_results"), default=limit, minimum=1)
    limit = max_results
    company_domain = _domain_from_value(input_data.get("company_domain") or input_data.get("company_website"))
    company_name = _as_non_empty_str(input_data.get("company_name"))
    company_linkedin_url = _as_non_empty_str(input_data.get("company_linkedin_url"))
    job_title = _as_non_empty_str(input_data.get("job_title"))
    job_level = _as_non_empty_str_or_list(input_data.get("job_level"))
    job_function = _as_non_empty_str_or_list(input_data.get("job_function"))
    location = _as_non_empty_str_or_list(input_data.get("location"))
    cascade = _as_list_of_dicts(input_data.get("cascade"))
    provider_filters = _person_provider_filters(input_data)
    prospeo_filters = _build_prospeo_filters(
        query=query,
        job_title=job_title,
        company_domain=company_domain,
        company_name=company_name,
        location=location,
        provider_filters=provider_filters,
    )

    effective_provider_filters = dict(provider_filters or {})
    if prospeo_filters:
        effective_provider_filters["prospeo"] = prospeo_filters

    if (
        not query
        and not company_domain
        and not company_name
        and not company_linkedin_url
        and not job_title
        and not job_level
        and not job_function
        and not location
        and not cascade
        and not provider_filters
    ):
        return {
            "run_id": run_id,
            "operation_id": "person.search",
            "status": "failed",
            "missing_inputs": [
                "query|company_domain|company_name|company_linkedin_url|job_title|job_level|job_function|location|cascade|provider_filters"
            ],
            "provider_attempts": attempts,
        }

    combined: list[dict[str, Any]] = []
    pagination_by_provider: dict[str, Any] = {}
    provider_order = _person_search_provider_order()
    ordered_general = [provider for provider in provider_order if provider in {"prospeo", "blitzapi", "companyenrich", "leadmagic"}]

    if cascade:
        execution_plan: list[str] = ["blitzapi_waterfall"]
    elif job_title:
        execution_plan = ["leadmagic_role"] + [provider for provider in ordered_general if provider in {"prospeo", "companyenrich"}]
        if "blitzapi" in ordered_general:
            execution_plan.append("blitzapi")
    else:
        execution_plan = []
        if "prospeo" in ordered_general:
            execution_plan.append("prospeo")
        if "blitzapi" in ordered_general:
            execution_plan.append("blitzapi")
        if "companyenrich" in ordered_general:
            execution_plan.append("companyenrich")
        if "leadmagic" in ordered_general:
            execution_plan.append("leadmagic_employee")

    provider_order_used: list[str] = []

    for provider in execution_plan:
        try:
            if provider == "prospeo":
                provider_order_used.append("prospeo")
                results, pagination = await _search_people_prospeo(
                    query=job_title or query,
                    page=page,
                    company_domain=company_domain,
                    company_name=company_name,
                    attempts=attempts,
                    provider_filters=effective_provider_filters,
                )
            elif provider == "blitzapi":
                provider_order_used.append("blitzapi")
                derived_job_level = _title_to_blitz_job_levels(job_title) if job_title else None
                results, pagination = await _search_people_blitzapi(
                    company_linkedin_url=company_linkedin_url,
                    job_level=job_level or derived_job_level,
                    job_function=job_function,
                    country_code=_country_codes_from_location(location),
                    max_results=limit,
                    page=page,
                    attempts=attempts,
                )
            elif provider == "blitzapi_waterfall":
                provider_order_used.append("blitzapi")
                results, pagination = await _search_people_blitzapi_waterfall(
                    company_linkedin_url=company_linkedin_url,
                    cascade=cascade,
                    max_results=limit,
                    attempts=attempts,
                )
            elif provider == "companyenrich":
                provider_order_used.append("companyenrich")
                results, pagination = await _search_people_companyenrich(
                    query=job_title or query,
                    page=page,
                    page_size=min(max(limit, 1), 100),
                    company_domain=company_domain,
                    company_name=company_name,
                    attempts=attempts,
                    provider_filters=effective_provider_filters,
                )
            elif provider == "leadmagic_employee":
                provider_order_used.append("leadmagic")
                results, pagination = await _search_people_leadmagic_employees(
                    company_domain=company_domain,
                    company_name=company_name,
                    max_results=limit,
                    attempts=attempts,
                )
            elif provider == "leadmagic_role":
                provider_order_used.append("leadmagic")
                results, pagination = await _search_people_leadmagic_role(
                    company_domain=company_domain,
                    company_name=company_name,
                    job_title=job_title,
                    attempts=attempts,
                )
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            attempts.append(
                {
                    "provider": provider,
                    "action": "person_search",
                    "status": "failed",
                    "provider_status": f"unhandled_exception:{exc.__class__.__name__}",
                    "raw_response": {"error": str(exc)},
                }
            )
            continue

        if pagination is not None:
            pagination_by_provider[provider] = pagination
        combined.extend(results)
        if results:
            break

    deduped = _dedupe_people(combined)[:limit]
    try:
        output = PersonSearchOutput.model_validate(
            {
                "results": deduped,
                "result_count": len(deduped),
                "provider_order_used": provider_order_used,
                "pagination": pagination_by_provider,
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "person.search",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "person.search",
        "status": "found" if deduped else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }
