from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.resolve import (
    ResolveDomainOutput,
    ResolveLinkedInOutput,
    ResolveLocationOutput,
    ResolvePersonLinkedInOutput,
)
from app.providers import blitzapi
from app.providers import revenueinfra


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _cumulative_context(input_data: dict[str, Any]) -> dict[str, Any]:
    context = input_data.get("cumulative_context")
    if isinstance(context, dict):
        return context
    return {}


def _extract_by_aliases(input_data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = _as_non_empty_str(input_data.get(alias))
        if value:
            return value
    context = _cumulative_context(input_data)
    for alias in aliases:
        value = _as_non_empty_str(context.get(alias))
        if value:
            return value
    return None


def _extract_email(input_data: dict[str, Any]) -> str | None:
    return _extract_by_aliases(input_data, ("work_email", "email"))


def _extract_domain(input_data: dict[str, Any]) -> str | None:
    return _extract_by_aliases(input_data, ("domain", "company_domain", "canonical_domain"))


def _extract_company_linkedin_url(input_data: dict[str, Any]) -> str | None:
    return _extract_by_aliases(input_data, ("company_linkedin_url", "linkedin_url"))


def _extract_company_name(input_data: dict[str, Any]) -> str | None:
    return _extract_by_aliases(input_data, ("company_name",))


def _missing_input_result(
    *,
    run_id: str,
    operation_id: str,
    missing_input: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "failed",
        "missing_inputs": [missing_input],
        "provider_attempts": attempts,
    }


async def execute_company_resolve_domain_from_email(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.domain_from_email"
    attempts: list[dict[str, Any]] = []

    work_email = _extract_email(input_data)
    if not work_email:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="work_email",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_domain_from_email(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        work_email=work_email,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveDomainOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_resolve_domain_from_linkedin(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.domain_from_linkedin"
    attempts: list[dict[str, Any]] = []

    company_linkedin_url = _extract_company_linkedin_url(input_data)
    if not company_linkedin_url:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="company_linkedin_url",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_domain_from_linkedin(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        company_linkedin_url=company_linkedin_url,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveDomainOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_resolve_domain_from_name(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.domain_from_name"
    attempts: list[dict[str, Any]] = []

    company_name = _extract_company_name(input_data)
    if not company_name:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="company_name",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_domain_from_company_name(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        company_name=company_name,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveDomainOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_resolve_linkedin_from_domain(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.linkedin_from_domain"
    attempts: list[dict[str, Any]] = []

    domain = _extract_domain(input_data)
    if not domain:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="domain",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_linkedin_from_domain(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        domain=domain,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveLinkedInOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_resolve_linkedin_from_domain_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.linkedin_from_domain_blitzapi"
    attempts: list[dict[str, Any]] = []

    domain = _extract_domain(input_data)
    if not domain:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="domain",
            attempts=attempts,
        )

    settings = get_settings()
    result = await blitzapi.resolve_linkedin_from_domain(
        api_key=settings.blitzapi_api_key,
        domain=domain,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveLinkedInOutput.model_validate({**mapped, "source_provider": "blitzapi"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_person_resolve_linkedin_from_email(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.resolve.linkedin_from_email"
    attempts: list[dict[str, Any]] = []

    work_email = _extract_email(input_data)
    if not work_email:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="work_email",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_person_linkedin_from_email(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        work_email=work_email,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolvePersonLinkedInOutput.model_validate(
        {**mapped, "source_provider": "revenueinfra"}
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_resolve_location_from_domain(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.location_from_domain"
    attempts: list[dict[str, Any]] = []

    domain = _extract_domain(input_data)
    if not domain:
        return _missing_input_result(
            run_id=run_id,
            operation_id=operation_id,
            missing_input="domain",
            attempts=attempts,
        )

    settings = get_settings()
    result = await revenueinfra.resolve_company_location_from_domain(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        domain=domain,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")
    status = attempt.get("status", "failed") if isinstance(attempt, dict) else "failed"

    if not isinstance(mapped, dict):
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": status,
            "provider_attempts": attempts,
        }

    output = ResolveLocationOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": status,
        "output": output,
        "provider_attempts": attempts,
    }
