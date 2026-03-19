from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.blitzapi_company_search import BlitzAPICompanySearchOutput
from app.contracts.company_enrich import BlitzAPICompanyEnrichOutput
from app.providers import blitzapi
from app.services._input_extraction import extract_company_linkedin_url, extract_company_name, extract_domain


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_str_list(value: Any) -> list[str] | None:
    if isinstance(value, str):
        item = _as_non_empty_str(value)
        return [item] if item else None
    if not isinstance(value, list):
        return None
    cleaned: list[str] = []
    for item in value:
        parsed = _as_non_empty_str(item)
        if parsed:
            cleaned.append(parsed)
    return cleaned or None


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _cumulative_context(input_data: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(input_data.get("cumulative_context"))


def _step_config(input_data: dict[str, Any]) -> dict[str, Any]:
    context_step = _as_dict(_cumulative_context(input_data).get("step_config"))
    direct_step = _as_dict(input_data.get("step_config"))
    return {**context_step, **direct_step}


def _extract_from_input_context_step(input_data: dict[str, Any], key: str) -> Any:
    if key in input_data and input_data.get(key) is not None:
        return input_data.get(key)
    context = _cumulative_context(input_data)
    if key in context and context.get(key) is not None:
        return context.get(key)
    return _step_config(input_data).get(key)


def _normalize_include_exclude(value: Any) -> dict[str, list[str]] | None:
    value_dict = _as_dict(value)
    if value_dict:
        include = _as_str_list(value_dict.get("include")) or []
        exclude = _as_str_list(value_dict.get("exclude")) or []
        if include or exclude:
            return {"include": include, "exclude": exclude}
    parsed = _as_str_list(value)
    if parsed:
        return {"include": parsed, "exclude": []}
    return None


def _build_company_filters(input_data: dict[str, Any]) -> dict[str, Any]:
    prebuilt = _extract_from_input_context_step(input_data, "company")
    if isinstance(prebuilt, dict) and prebuilt:
        return prebuilt
    prebuilt_alias = _extract_from_input_context_step(input_data, "company_filters")
    if isinstance(prebuilt_alias, dict) and prebuilt_alias:
        return prebuilt_alias

    company: dict[str, Any] = {}

    keywords = _normalize_include_exclude(_extract_from_input_context_step(input_data, "keywords"))
    if not keywords:
        include = _as_str_list(_extract_from_input_context_step(input_data, "keywords_include")) or []
        exclude = _as_str_list(_extract_from_input_context_step(input_data, "keywords_exclude")) or []
        if include or exclude:
            keywords = {"include": include, "exclude": exclude}
    if keywords:
        company["keywords"] = keywords

    industry = _normalize_include_exclude(_extract_from_input_context_step(input_data, "industry"))
    if not industry:
        include = _as_str_list(_extract_from_input_context_step(input_data, "industry_include")) or []
        exclude = _as_str_list(_extract_from_input_context_step(input_data, "industry_exclude")) or []
        if include or exclude:
            industry = {"include": include, "exclude": exclude}
    if industry:
        company["industry"] = industry

    hq_source = _as_dict(_extract_from_input_context_step(input_data, "hq"))
    hq: dict[str, Any] = {}
    continent = _as_str_list(hq_source.get("continent")) or _as_str_list(_extract_from_input_context_step(input_data, "hq_continent")) or _as_str_list(
        _extract_from_input_context_step(input_data, "continent")
    )
    if continent:
        hq["continent"] = continent
    country_code = _as_str_list(hq_source.get("country_code")) or _as_str_list(
        _extract_from_input_context_step(input_data, "hq_country_code")
    ) or _as_str_list(_extract_from_input_context_step(input_data, "country_code"))
    if country_code:
        hq["country_code"] = country_code
    sales_region = _as_str_list(hq_source.get("sales_region")) or _as_str_list(
        _extract_from_input_context_step(input_data, "hq_sales_region")
    ) or _as_str_list(_extract_from_input_context_step(input_data, "sales_region"))
    if sales_region:
        hq["sales_region"] = sales_region

    city = _normalize_include_exclude(hq_source.get("city")) or _normalize_include_exclude(
        _extract_from_input_context_step(input_data, "hq_city")
    )
    if city:
        hq["city"] = city
    if hq:
        company["hq"] = hq

    employee_range = _as_str_list(_extract_from_input_context_step(input_data, "employee_range"))
    if employee_range:
        company["employee_range"] = employee_range

    founded_year_min = _as_int(_extract_from_input_context_step(input_data, "founded_year_min"))
    founded_year_max = _as_int(_extract_from_input_context_step(input_data, "founded_year_max"))
    if founded_year_min is not None or founded_year_max is not None:
        company["founded_year"] = {
            "min": founded_year_min if founded_year_min is not None else 0,
            "max": founded_year_max if founded_year_max is not None else 0,
        }

    company_type = _normalize_include_exclude(_extract_from_input_context_step(input_data, "company_type"))
    if not company_type:
        type_include = _as_str_list(_extract_from_input_context_step(input_data, "type_include")) or []
        type_exclude = _as_str_list(_extract_from_input_context_step(input_data, "type_exclude")) or []
        if type_include or type_exclude:
            company_type = {"include": type_include, "exclude": type_exclude}
    if company_type:
        company["type"] = company_type

    min_followers = _as_int(_extract_from_input_context_step(input_data, "min_linkedin_followers"))
    if min_followers is not None:
        company["min_linkedin_followers"] = min_followers

    # Shared fallback extraction keeps company filter derivation consistent
    # with other service functions when direct filters are absent.
    derived_domain = extract_domain(input_data)
    if derived_domain and "website" not in company:
        company["website"] = {"include": [derived_domain], "exclude": []}

    derived_company_name = extract_company_name(input_data)
    if derived_company_name and "name" not in company:
        company["name"] = {"include": [derived_company_name], "exclude": []}

    return company


async def execute_company_search_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.search.blitzapi"
    attempts: list[dict[str, Any]] = []

    company_filters = _build_company_filters(input_data)
    if not company_filters:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_filters"],
            "provider_attempts": attempts,
        }

    max_results = _as_int(_extract_from_input_context_step(input_data, "max_results")) or 10
    max_results = max(min(max_results, 50), 1)
    cursor = _as_non_empty_str(_extract_from_input_context_step(input_data, "cursor"))

    settings = get_settings()
    provider_result = await blitzapi.search_companies(
        api_key=settings.blitzapi_api_key,
        company_filters=company_filters,
        max_results=max_results,
        cursor=cursor,
    )
    attempt = provider_result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})

    mapped = provider_result.get("mapped") if isinstance(provider_result.get("mapped"), dict) else {}
    results = mapped.get("results") if isinstance(mapped.get("results"), list) else []
    pagination = mapped.get("pagination") if isinstance(mapped.get("pagination"), dict) else {}

    try:
        output = BlitzAPICompanySearchOutput.model_validate(
            {
                "results": results,
                "results_count": len(results),
                "total_results": pagination.get("totalItems"),
                "cursor": pagination.get("cursor"),
                "source_provider": "blitzapi",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_enrich_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.enrich.blitzapi"
    attempts: list[dict[str, Any]] = []

    company_linkedin_url = extract_company_linkedin_url(input_data)
    company_domain = extract_domain(input_data)

    if not company_linkedin_url and not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_linkedin_url|company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    if not company_linkedin_url and company_domain:
        bridge_result = await blitzapi.resolve_linkedin_from_domain(
            api_key=settings.blitzapi_api_key,
            domain=company_domain,
        )
        attempts.append(bridge_result["attempt"])
        bridge_mapped = _as_dict(bridge_result.get("mapped"))
        company_linkedin_url = _as_non_empty_str(bridge_mapped.get("company_linkedin_url"))

    provider_result = await blitzapi.enrich_company_profile(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=company_linkedin_url,
    )
    attempts.append(provider_result["attempt"])

    mapped = provider_result.get("mapped")
    if not isinstance(mapped, dict):
        attempt_status = provider_result["attempt"].get("status", "failed")
        status = "found" if attempt_status == "found" else "not_found" if attempt_status == "not_found" else "failed"
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    try:
        output = BlitzAPICompanyEnrichOutput.model_validate(mapped).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {"code": "output_validation_failed", "message": str(exc)},
        }

    status = provider_result["attempt"].get("status", "failed")
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
