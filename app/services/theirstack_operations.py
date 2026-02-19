from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.theirstack import (
    TheirStackCompanySearchOutput,
    TheirStackHiringSignalsOutput,
    TheirStackJobSearchExtendedOutput,
    TheirStackTechStackOutput,
)
from app.providers import theirstack


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any, *, default: int, minimum: int = 1, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if parsed < minimum:
        return minimum
    if parsed > maximum:
        return maximum
    return parsed


def _has_filter_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    if isinstance(value, dict):
        return len(value) > 0
    return True


def _cumulative_context(input_data: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(input_data.get("cumulative_context"))


def _extract_step_config(input_data: dict[str, Any]) -> dict[str, Any]:
    direct = _as_dict(input_data.get("step_config"))
    if direct:
        return direct
    context = _cumulative_context(input_data)
    return _as_dict(context.get("step_config"))


def _first_context_value(input_data: dict[str, Any], key: str) -> Any:
    context = _cumulative_context(input_data)
    profile = _as_dict(context.get("company_profile"))
    output = _as_dict(context.get("output"))
    return (
        input_data.get(key)
        or context.get(key)
        or profile.get(key)
        or output.get(key)
    )


async def execute_company_search_by_tech_stack(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.search.by_tech_stack"
    attempts: list[dict[str, Any]] = []
    step_config = _extract_step_config(input_data)

    limit = _as_int(step_config.get("limit"), default=25, minimum=1, maximum=200)
    filters = {
        "technology_slug_or": step_config.get("technology_slug_or"),
        "industry_or": step_config.get("industry_or"),
        "min_employee_count": step_config.get("min_employee_count"),
        "max_employee_count": step_config.get("max_employee_count"),
        "company_country_code_or": step_config.get("company_country_code_or"),
        "job_title_or": step_config.get("job_title_or"),
    }
    cleaned_filters = {key: value for key, value in filters.items() if _has_filter_value(value)}

    if not cleaned_filters:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": [
                "technology_slug_or|industry_or|min_employee_count|max_employee_count|company_country_code_or|job_title_or"
            ],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await theirstack.search_companies(
        api_key=settings.theirstack_api_key,
        filters=cleaned_filters,
        limit=limit,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    mapped = _as_dict(provider_result.get("mapped"))
    results = mapped.get("results") if isinstance(mapped.get("results"), list) else []

    try:
        output = TheirStackCompanySearchOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "source_provider": "theirstack",
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

    provider_status = attempt.get("status", "failed")
    if provider_status == "failed":
        status = "failed"
    elif provider_status == "skipped":
        status = "failed"
    else:
        status = "found" if output["result_count"] else "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_search_by_job_postings(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.search.by_job_postings"
    attempts: list[dict[str, Any]] = []
    step_config = _extract_step_config(input_data)

    limit = _as_int(step_config.get("limit"), default=25, minimum=1, maximum=200)
    filters = {
        "job_title_or": step_config.get("job_title_or"),
        "job_country_code_or": step_config.get("job_country_code_or"),
        "posted_at_max_age_days": step_config.get("posted_at_max_age_days"),
        "job_technology_slug_or": step_config.get("job_technology_slug_or"),
        "job_seniority_or": step_config.get("job_seniority_or"),
        "company_domain_or": step_config.get("company_domain_or"),
        "company_domain_not": step_config.get("company_domain_not"),
        "company_name_or": step_config.get("company_name_or"),
        "company_name_not": step_config.get("company_name_not"),
        "company_linkedin_url_or": step_config.get("company_linkedin_url_or"),
        "posted_at_gte": step_config.get("posted_at_gte"),
        "posted_at_lte": step_config.get("posted_at_lte"),
        "remote": step_config.get("remote"),
        "min_salary_usd": step_config.get("min_salary_usd"),
        "max_salary_usd": step_config.get("max_salary_usd"),
        "employment_statuses_or": step_config.get("employment_statuses_or"),
        "company_type": step_config.get("company_type"),
        "min_employee_count": step_config.get("min_employee_count"),
        "max_employee_count": step_config.get("max_employee_count"),
        "min_revenue_usd": step_config.get("min_revenue_usd"),
        "max_revenue_usd": step_config.get("max_revenue_usd"),
    }
    cleaned_filters = {key: value for key, value in filters.items() if _has_filter_value(value)}

    if not cleaned_filters:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": [
                "job_title_or|job_country_code_or|posted_at_max_age_days|posted_at_gte|posted_at_lte|job_technology_slug_or|job_seniority_or|company_domain_or|company_name_or|company_linkedin_url_or|remote|min_salary_usd|max_salary_usd|employment_statuses_or|company_type|min_employee_count|max_employee_count|min_revenue_usd|max_revenue_usd"
            ],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await theirstack.search_jobs(
        api_key=settings.theirstack_api_key,
        filters=cleaned_filters,
        limit=limit,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    mapped = _as_dict(provider_result.get("mapped"))
    results = mapped.get("results") if isinstance(mapped.get("results"), list) else []

    try:
        output = TheirStackJobSearchExtendedOutput.model_validate(
            {
                "results": results,
                "result_count": len(results),
                "total_results": mapped.get("total_results"),
                "total_companies": mapped.get("total_companies"),
                "source_provider": "theirstack",
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

    provider_status = attempt.get("status", "failed")
    if provider_status == "failed":
        status = "failed"
    elif provider_status == "skipped":
        status = "failed"
    else:
        status = "found" if output["result_count"] else "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_enrich_tech_stack(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.enrich.tech_stack"
    attempts: list[dict[str, Any]] = []

    company_domain = _as_non_empty_str(_first_context_value(input_data, "company_domain"))
    company_name = _as_non_empty_str(_first_context_value(input_data, "company_name"))
    company_linkedin_url = _as_non_empty_str(_first_context_value(input_data, "company_linkedin_url"))

    if not (company_domain or company_name or company_linkedin_url):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain|company_name|company_linkedin_url"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await theirstack.get_technographics(
        api_key=settings.theirstack_api_key,
        company_domain=company_domain,
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    mapped = _as_dict(provider_result.get("mapped"))
    technologies = mapped.get("technologies") if isinstance(mapped.get("technologies"), list) else []

    try:
        output = TheirStackTechStackOutput.model_validate(
            {
                "technologies": technologies,
                "technology_count": len(technologies),
                "source_provider": "theirstack",
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

    provider_status = attempt.get("status", "failed")
    if provider_status == "failed":
        status = "failed"
    elif provider_status == "skipped":
        status = "failed"
    else:
        status = "found" if output["technology_count"] else "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_enrich_hiring_signals(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.enrich.hiring_signals"
    attempts: list[dict[str, Any]] = []

    company_domain = _as_non_empty_str(_first_context_value(input_data, "company_domain"))
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await theirstack.enrich_hiring_signals(
        api_key=settings.theirstack_api_key,
        company_domain=company_domain,
    )
    attempt = _as_dict(provider_result.get("attempt"))
    attempts.append(attempt)

    mapped = provider_result.get("mapped")
    if not isinstance(mapped, dict):
        mapped = {}

    try:
        output = TheirStackHiringSignalsOutput.model_validate(
            {
                **mapped,
                "source_provider": "theirstack",
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

    provider_status = attempt.get("status", "failed")
    if provider_status == "failed":
        status = "failed"
    elif provider_status == "skipped":
        status = "failed"
    elif output.get("domain") or output.get("company_name"):
        status = "found"
    else:
        status = "not_found"

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
