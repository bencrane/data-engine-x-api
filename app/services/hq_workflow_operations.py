from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.hq_workflow import (
    DiscoverCustomersGeminiOutput,
    EvaluateIcpFitOutput,
    GeminiIcpJobTitlesOutput,
    IcpCriterionOutput,
    InferLinkedInUrlOutput,
    SalesNavUrlOutput,
)
from app.providers import revenueinfra


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    return None


def _coerce_list_of_strings(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    parsed = [_as_str(item) for item in value]
    cleaned = [item for item in parsed if item]
    return cleaned or None


def _coerce_titles(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    titles: list[str] = []
    for item in value:
        if isinstance(item, dict):
            title = _as_str(item.get("title"))
            if title:
                titles.append(title)
            continue
        title = _as_str(item)
        if title:
            titles.append(title)
    return titles or None


def _coerce_customer_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        if isinstance(item, dict):
            name = _as_str(item.get("name"))
            if name:
                names.append(name)
            continue
        name = _as_str(item)
        if name:
            names.append(name)
    return names or None


def _ctx(input_data: dict[str, Any]) -> dict[str, Any]:
    context = input_data.get("cumulative_context")
    if isinstance(context, dict):
        return context
    return {}


def _extract_str(input_data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = _as_str(input_data.get(alias))
        if value:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_str(context.get(alias))
        if value:
            return value
    return None


def _extract_list(input_data: dict[str, Any], aliases: tuple[str, ...]) -> list[Any] | None:
    for alias in aliases:
        value = _as_list(input_data.get(alias))
        if value is not None:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_list(context.get(alias))
        if value is not None:
            return value
    return None


def _missing_inputs_result(
    *,
    run_id: str,
    operation_id: str,
    missing_inputs: list[str],
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "failed",
        "missing_inputs": missing_inputs,
        "provider_attempts": attempts,
    }


def _validate_output(
    *,
    model: Any,
    payload: dict[str, Any],
    run_id: str,
    operation_id: str,
    attempts: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        return model.model_validate(payload).model_dump(), None
    except Exception as exc:  # noqa: BLE001
        return None, {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }


async def execute_company_research_infer_linkedin_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.research.infer_linkedin_url"
    attempts: list[dict[str, Any]] = []

    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    domain = _extract_str(input_data, ("domain", "company_domain", "canonical_domain"))
    if not company_name:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=["company_name"],
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.infer_linkedin_url(
        base_url=settings.revenueinfra_api_url,
        company_name=company_name,
        domain=domain,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=InferLinkedInUrlOutput,
        payload={
            "company_linkedin_url": mapped.get("company_linkedin_url"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_icp_job_titles_gemini(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.research.icp_job_titles_gemini"
    attempts: list[dict[str, Any]] = []

    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    domain = _extract_str(input_data, ("domain", "company_domain", "canonical_domain"))
    company_description = _extract_str(input_data, ("company_description", "description_raw", "description"))
    if not company_name and not domain:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=["company_name|domain"],
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.research_icp_job_titles_gemini(
        base_url=settings.revenueinfra_api_url,
        company_name=company_name,
        domain=domain,
        company_description=company_description,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=GeminiIcpJobTitlesOutput,
        payload={
            "inferred_product": mapped.get("inferred_product"),
            "buyer_persona": mapped.get("buyer_persona"),
            "titles": mapped.get("titles"),
            "champion_titles": mapped.get("champion_titles"),
            "evaluator_titles": mapped.get("evaluator_titles"),
            "decision_maker_titles": mapped.get("decision_maker_titles"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_discover_customers_gemini(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.research.discover_customers_gemini"
    attempts: list[dict[str, Any]] = []

    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    domain = _extract_str(input_data, ("domain", "company_domain", "canonical_domain"))
    if not company_name and not domain:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=["company_name|domain"],
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.discover_customers_gemini(
        base_url=settings.revenueinfra_api_url,
        company_name=company_name,
        domain=domain,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=DiscoverCustomersGeminiOutput,
        payload={
            "customers": mapped.get("customers"),
            "customer_count": mapped.get("customer_count"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_derive_icp_criterion(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.derive.icp_criterion"
    attempts: list[dict[str, Any]] = []

    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    domain = _extract_str(input_data, ("domain", "company_domain", "canonical_domain"))
    if not company_name and not domain:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=["company_name|domain"],
            attempts=attempts,
        )

    customers = _coerce_customer_names(_extract_list(input_data, ("customers",)))
    icp_titles = _coerce_titles(_extract_list(input_data, ("champion_titles", "titles")))

    settings = get_settings()
    result = await revenueinfra.generate_icp_criterion(
        base_url=settings.revenueinfra_api_url,
        company_name=company_name,
        domain=domain,
        customers=customers,
        icp_titles=icp_titles,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=IcpCriterionOutput,
        payload={
            "icp_criterion": mapped.get("icp_criterion"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_derive_salesnav_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.derive.salesnav_url"
    attempts: list[dict[str, Any]] = []

    org_id = _extract_str(input_data, ("company_linkedin_id", "org_id", "orgId", "linkedin_id"))
    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    titles = _coerce_titles(_extract_list(input_data, ("champion_titles", "titles")))
    excluded_seniority = _coerce_list_of_strings(_extract_list(input_data, ("excluded_seniority", "excludedSeniority")))
    regions = _coerce_list_of_strings(_extract_list(input_data, ("regions",)))
    company_hq_regions = _coerce_list_of_strings(_extract_list(input_data, ("company_hq_regions", "companyHQRegions")))

    missing_inputs: list[str] = []
    if not org_id:
        missing_inputs.append("org_id")
    if not company_name:
        missing_inputs.append("company_name")
    if missing_inputs:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=missing_inputs,
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.build_salesnav_url(
        base_url=settings.revenueinfra_api_url,
        org_id=org_id,
        company_name=company_name,
        titles=titles,
        excluded_seniority=excluded_seniority,
        regions=regions,
        company_hq_regions=company_hq_regions,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=SalesNavUrlOutput,
        payload={
            "salesnav_url": mapped.get("salesnav_url"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_derive_evaluate_icp_fit(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.derive.evaluate_icp_fit"
    attempts: list[dict[str, Any]] = []

    criterion = _extract_str(input_data, ("criterion", "icp_criterion"))
    company_name = _extract_str(input_data, ("company_name", "canonical_name", "name"))
    domain = _extract_str(input_data, ("domain", "company_domain", "canonical_domain"))
    description = _extract_str(input_data, ("description", "description_raw"))
    if not criterion:
        return _missing_inputs_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_inputs=["criterion"],
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.evaluate_icp_fit(
        base_url=settings.revenueinfra_api_url,
        criterion=criterion,
        company_name=company_name,
        domain=domain,
        description=description,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result.get("mapped"), dict) else {}
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    output, error = _validate_output(
        model=EvaluateIcpFitOutput,
        payload={
            "icp_fit_verdict": mapped.get("icp_fit_verdict"),
            "icp_fit_reasoning": mapped.get("icp_fit_reasoning"),
            "source_provider": mapped.get("source_provider") or "revenueinfra",
        },
        run_id=run_id,
        operation_id=operation_id,
        attempts=attempts,
    )
    if error:
        return error
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
