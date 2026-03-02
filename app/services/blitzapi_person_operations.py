from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.blitzapi_person import EmployeeFinderOutput, FindWorkEmailOutput, WaterfallIcpSearchOutput
from app.providers import blitzapi

_DEFAULT_WATERFALL_CASCADE: list[dict[str, Any]] = [
    {
        "include_title": ["VP", "Director", "Head of"],
        "exclude_title": ["intern", "assistant", "junior"],
        "location": ["WORLD"],
        "include_headline_search": False,
    },
    {
        "include_title": ["CEO", "founder", "cofounder", "CTO", "COO", "CRO"],
        "exclude_title": [],
        "location": ["WORLD"],
        "include_headline_search": False,
    },
]


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _cumulative_context(input_data: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(input_data.get("cumulative_context"))


def _step_config(input_data: dict[str, Any]) -> dict[str, Any]:
    return _as_dict(input_data.get("step_config"))


def _extract_by_aliases(input_data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        direct_value = _as_non_empty_str(input_data.get(alias))
        if direct_value:
            return direct_value
    context = _cumulative_context(input_data)
    for alias in aliases:
        context_value = _as_non_empty_str(context.get(alias))
        if context_value:
            return context_value
    return None


def _extract_from_input_context_step(input_data: dict[str, Any], key: str) -> Any:
    if key in input_data and input_data.get(key) is not None:
        return input_data.get(key)
    context = _cumulative_context(input_data)
    if key in context and context.get(key) is not None:
        return context.get(key)
    return _step_config(input_data).get(key)


async def execute_person_search_waterfall_icp_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.search.waterfall_icp_blitzapi"
    attempts: list[dict[str, Any]] = []

    company_linkedin_url = _extract_by_aliases(input_data, ("company_linkedin_url", "linkedin_url"))
    if not company_linkedin_url:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_linkedin_url"],
            "provider_attempts": attempts,
        }

    cascade_value = _extract_from_input_context_step(input_data, "cascade")
    cascade = cascade_value if isinstance(cascade_value, list) else _DEFAULT_WATERFALL_CASCADE
    max_results = _as_int(_extract_from_input_context_step(input_data, "max_results"), default=10, minimum=1)

    settings = get_settings()
    provider_result = await blitzapi.search_icp_waterfall(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=company_linkedin_url,
        cascade=cascade,
        max_results=max_results,
    )
    attempt = provider_result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = provider_result.get("mapped") or {}
    results = mapped.get("results") if isinstance(mapped, dict) and isinstance(mapped.get("results"), list) else []

    try:
        output = WaterfallIcpSearchOutput.model_validate(
            {
                "results": results,
                "results_count": len(results),
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


async def execute_person_search_employee_finder_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.search.employee_finder_blitzapi"
    attempts: list[dict[str, Any]] = []

    company_linkedin_url = _extract_by_aliases(input_data, ("company_linkedin_url", "linkedin_url"))
    if not company_linkedin_url:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_linkedin_url"],
            "provider_attempts": attempts,
        }

    job_level = _extract_from_input_context_step(input_data, "job_level")
    job_function = _extract_from_input_context_step(input_data, "job_function")
    country_code = _extract_from_input_context_step(input_data, "country_code")
    max_results = _as_int(_extract_from_input_context_step(input_data, "max_results"), default=10, minimum=1)
    page = _as_int(_extract_from_input_context_step(input_data, "page"), default=1, minimum=1)

    settings = get_settings()
    provider_result = await blitzapi.search_employees(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=company_linkedin_url,
        job_level=job_level,
        job_function=job_function,
        country_code=country_code,
        max_results=max_results,
        page=page,
    )
    attempt = provider_result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = provider_result.get("mapped") or {}
    results = mapped.get("results") if isinstance(mapped, dict) and isinstance(mapped.get("results"), list) else []
    pagination = mapped.get("pagination") if isinstance(mapped, dict) and isinstance(mapped.get("pagination"), dict) else None

    try:
        output = EmployeeFinderOutput.model_validate(
            {
                "results": results,
                "results_count": len(results),
                "pagination": pagination,
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


async def execute_person_contact_resolve_email_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.contact.resolve_email_blitzapi"
    attempts: list[dict[str, Any]] = []

    person_linkedin_url = _extract_by_aliases(input_data, ("person_linkedin_url", "linkedin_url"))
    if not person_linkedin_url:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["person_linkedin_url"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    provider_result = await blitzapi.find_work_email(
        api_key=settings.blitzapi_api_key,
        person_linkedin_url=person_linkedin_url,
    )
    attempt = provider_result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = provider_result.get("mapped")

    work_email = mapped.get("work_email") if isinstance(mapped, dict) else None
    all_emails = mapped.get("all_emails") if isinstance(mapped, dict) else None
    try:
        output = FindWorkEmailOutput.model_validate(
            {
                "work_email": work_email,
                "all_emails": all_emails,
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
