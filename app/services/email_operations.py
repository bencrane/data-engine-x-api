from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.person_contact import ResolveEmailOutput, ResolveMobilePhoneOutput, VerifyEmailOutput
from app.providers import blitzapi, icypeas, leadmagic, millionverifier, parallel_ai, reoon

INCONCLUSIVE_MILLIONVERIFIER_RESULTS = {"unknown", "catch_all"}
INCONCLUSIVE_REOON_STATUSES = {"unknown", "catch_all"}


def _split_full_name(full_name: str | None) -> tuple[str | None, str | None]:
    if not full_name:
        return None, None
    parts = [part.strip() for part in full_name.split(" ") if part.strip()]
    if not parts:
        return None, None
    if len(parts) == 1:
        return parts[0], None
    return parts[0], " ".join(parts[1:])


async def _icypeas_email_search(
    *,
    first_name: str | None,
    last_name: str | None,
    domain_or_company: str,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    result = await icypeas.resolve_email(
        api_key=settings.icypeas_api_key,
        first_name=first_name,
        last_name=last_name,
        domain_or_company=domain_or_company,
        poll_interval_ms=settings.icypeas_poll_interval_ms,
        max_wait_ms=settings.icypeas_max_wait_ms,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("email")


async def _leadmagic_email_finder(
    *,
    first_name: str | None,
    last_name: str | None,
    full_name: str | None,
    domain: str | None,
    company_name: str | None,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    result = await leadmagic.resolve_email(
        api_key=settings.leadmagic_api_key,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        domain=domain,
        company_name=company_name,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("email")


async def _parallel_findability_email(
    *,
    full_name: str,
    company: str,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    result = await parallel_ai.findability_email(
        api_key=settings.parallel_api_key,
        full_name=full_name,
        company=company,
        processor=settings.parallel_processor,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("email")


async def _millionverifier_verify(
    *,
    email: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    result = await millionverifier.verify_email(
        api_key=settings.millionverifier_api_key,
        email=email,
        timeout_seconds=settings.millionverifier_timeout_seconds,
        inconclusive_statuses=INCONCLUSIVE_MILLIONVERIFIER_RESULTS,
    )
    attempts.append(result["attempt"])
    return result.get("mapped")


async def _reoon_verify(
    *,
    email: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    result = await reoon.verify_email(
        api_key=settings.reoon_api_key,
        email=email,
        mode=settings.reoon_mode,
        inconclusive_statuses=INCONCLUSIVE_REOON_STATUSES,
    )
    attempts.append(result["attempt"])
    return result.get("mapped")


def _mobile_provider_order() -> list[str]:
    settings = get_settings()
    parsed = [
        item.strip()
        for item in settings.person_resolve_mobile_order.split(",")
        if item.strip()
    ]
    allowed = {"leadmagic", "blitzapi"}
    filtered = [item for item in parsed if item in allowed]
    return filtered or ["leadmagic", "blitzapi"]


async def _leadmagic_mobile_finder(
    *,
    profile_url: str | None,
    work_email: str | None,
    personal_email: str | None,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    result = await leadmagic.resolve_mobile_phone(
        api_key=settings.leadmagic_api_key,
        profile_url=profile_url,
        work_email=work_email,
        personal_email=personal_email,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("mobile_phone")


async def _blitzapi_phone_enrich(
    *,
    person_linkedin_url: str | None,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    result = await blitzapi.phone_enrich(
        api_key=settings.blitzapi_api_key,
        person_linkedin_url=person_linkedin_url,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    return mapped.get("mobile_phone")


async def execute_person_contact_resolve_email(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    full_name = input_data.get("full_name")
    first_name = input_data.get("first_name")
    last_name = input_data.get("last_name")
    if not first_name and not last_name:
        split_first, split_last = _split_full_name(full_name)
        first_name = first_name or split_first
        last_name = last_name or split_last

    company_domain = input_data.get("company_domain")
    company_name = input_data.get("company_name")
    domain_or_company = company_domain or company_name

    if not domain_or_company:
        return {
            "run_id": run_id,
            "operation_id": "person.contact.resolve_email",
            "status": "failed",
            "missing_inputs": ["company_domain|company_name"],
            "provider_attempts": attempts,
        }
    if not (first_name or last_name or full_name):
        return {
            "run_id": run_id,
            "operation_id": "person.contact.resolve_email",
            "status": "failed",
            "missing_inputs": ["first_name|last_name|full_name"],
            "provider_attempts": attempts,
        }

    resolved_email = await _icypeas_email_search(
        first_name=first_name,
        last_name=last_name,
        domain_or_company=domain_or_company,
        attempts=attempts,
    )
    source = "icypeas" if resolved_email else None

    if not resolved_email:
        resolved_email = await _leadmagic_email_finder(
            first_name=first_name,
            last_name=last_name,
            full_name=full_name,
            domain=company_domain,
            company_name=company_name,
            attempts=attempts,
        )
        if resolved_email:
            source = "leadmagic"

    if not resolved_email:
        has_parallel_inputs = bool((full_name or (first_name and last_name)) and (company_name or company_domain))
        if not has_parallel_inputs:
            attempts.append(
                {
                    "provider": "parallel",
                    "action": "findability_email",
                    "status": "skipped",
                    "skip_reason": "missing_required_inputs",
                }
            )
        else:
            resolved_email = await _parallel_findability_email(
                full_name=full_name or f"{first_name or ''} {last_name or ''}".strip(),
                company=company_name or company_domain,
                attempts=attempts,
            )
            if resolved_email:
                source = "parallel"

    verification = None
    if resolved_email:
        verification = await _millionverifier_verify(email=resolved_email, attempts=attempts)
        if verification is None or verification.get("inconclusive", False):
            reoon_verification = await _reoon_verify(email=resolved_email, attempts=attempts)
            if reoon_verification is not None:
                verification = reoon_verification

    output = ResolveEmailOutput.model_validate(
        {
            "email": resolved_email,
            "source_provider": source,
            "verification": verification,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "person.contact.resolve_email",
        "status": "found" if resolved_email else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_person_contact_verify_email(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())
    email = input_data.get("email")
    if not email or not isinstance(email, str):
        return {
            "run_id": run_id,
            "operation_id": "person.contact.verify_email",
            "status": "failed",
            "missing_inputs": ["email"],
            "provider_attempts": attempts,
        }

    verification = await _millionverifier_verify(email=email, attempts=attempts)
    if verification is None or verification.get("inconclusive", False):
        reoon_verification = await _reoon_verify(email=email, attempts=attempts)
        if reoon_verification is not None:
            verification = reoon_verification

    output = VerifyEmailOutput.model_validate(
        {
            "email": email,
            "verification": verification,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "person.contact.verify_email",
        "status": "verified" if verification else "failed",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_person_contact_resolve_mobile_phone(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    profile_url = input_data.get("profile_url") or input_data.get("linkedin_url")
    work_email = input_data.get("work_email")
    personal_email = input_data.get("personal_email")
    if not (profile_url or work_email or personal_email):
        return {
            "run_id": run_id,
            "operation_id": "person.contact.resolve_mobile_phone",
            "status": "failed",
            "missing_inputs": ["profile_url|linkedin_url|work_email|personal_email"],
            "provider_attempts": attempts,
        }

    mobile_phone = None
    source = None
    for provider in _mobile_provider_order():
        if provider == "leadmagic":
            mobile_phone = await _leadmagic_mobile_finder(
                profile_url=profile_url,
                work_email=work_email,
                personal_email=personal_email,
                attempts=attempts,
            )
            if mobile_phone:
                source = "leadmagic"
                break
        elif provider == "blitzapi":
            mobile_phone = await _blitzapi_phone_enrich(
                person_linkedin_url=profile_url,
                attempts=attempts,
            )
            if mobile_phone:
                source = "blitzapi"
                break

    output = ResolveMobilePhoneOutput.model_validate(
        {
            "mobile_phone": mobile_phone,
            "source_provider": source,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "person.contact.resolve_mobile_phone",
        "status": "found" if mobile_phone else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }

