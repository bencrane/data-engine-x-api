from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

import httpx

from app.config import get_settings

PENDING_ICYPEAS_STATUSES = {"NONE", "SCHEDULED", "IN_PROGRESS"}
INCONCLUSIVE_MILLIONVERIFIER_RESULTS = {"unknown", "catch_all"}
INCONCLUSIVE_REOON_STATUSES = {"unknown", "catch_all"}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _deep_find_first_str(data: Any, keys: set[str]) -> str | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys and isinstance(value, str) and value.strip():
                return value.strip()
            nested = _deep_find_first_str(value, keys)
            if nested:
                return nested
    elif isinstance(data, list):
        for item in data:
            nested = _deep_find_first_str(item, keys)
            if nested:
                return nested
    return None


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
    if not settings.icypeas_api_key:
        attempts.append(
            {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None
    if not (first_name or last_name):
        attempts.append(
            {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_name_input",
            }
        )
        return None

    start_ms = _now_ms()
    headers = {
        "Authorization": settings.icypeas_api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        submit_res = await client.post(
            "https://app.icypeas.com/api/email-search",
            headers=headers,
            json={
                "firstname": first_name or "",
                "lastname": last_name or "",
                "domainOrCompany": domain_or_company,
            },
        )
        submit_body: dict[str, Any] = {}
        try:
            submit_body = submit_res.json()
        except Exception:  # noqa: BLE001
            submit_body = {"raw": submit_res.text}

        if submit_res.status_code >= 400:
            attempts.append(
                {
                    "provider": "icypeas",
                    "action": "resolve_email",
                    "status": "failed",
                    "http_status": submit_res.status_code,
                    "duration_ms": _now_ms() - start_ms,
                    "raw_response": submit_body,
                }
            )
            return None

        search_id = submit_body.get("item", {}).get("_id")
        if not search_id:
            attempts.append(
                {
                    "provider": "icypeas",
                    "action": "resolve_email",
                    "status": "failed",
                    "duration_ms": _now_ms() - start_ms,
                    "raw_response": submit_body,
                    "error": "missing_search_id",
                }
            )
            return None

        deadline = _now_ms() + settings.icypeas_max_wait_ms
        last_body: dict[str, Any] = {}
        final_status: str | None = None

        while _now_ms() < deadline:
            read_res = await client.post(
                "https://app.icypeas.com/api/bulk-single-searchs/read",
                headers=headers,
                json={"id": search_id},
            )
            try:
                last_body = read_res.json()
            except Exception:  # noqa: BLE001
                last_body = {"raw": read_res.text}

            if read_res.status_code >= 400:
                attempts.append(
                    {
                        "provider": "icypeas",
                        "action": "resolve_email",
                        "status": "failed",
                        "http_status": read_res.status_code,
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": last_body,
                    }
                )
                return None

            item = (last_body.get("items") or [{}])[0]
            final_status = str(item.get("status") or "")
            if final_status not in PENDING_ICYPEAS_STATUSES:
                emails = item.get("results", {}).get("emails") or []
                resolved_email = None
                if emails and isinstance(emails, list):
                    first_email = emails[0] or {}
                    resolved_email = first_email.get("email")

                attempts.append(
                    {
                        "provider": "icypeas",
                        "action": "resolve_email",
                        "status": "found" if resolved_email else "not_found",
                        "duration_ms": _now_ms() - start_ms,
                        "provider_status": final_status,
                        "search_id": search_id,
                        "raw_response": last_body,
                    }
                )
                return resolved_email

            await asyncio.sleep(settings.icypeas_poll_interval_ms / 1000)

        attempts.append(
            {
                "provider": "icypeas",
                "action": "resolve_email",
                "status": "failed",
                "duration_ms": _now_ms() - start_ms,
                "search_id": search_id,
                "provider_status": final_status,
                "error": "poll_timeout",
                "raw_response": last_body,
            }
        )
        return None


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
    if not settings.leadmagic_api_key:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None

    has_name = bool((first_name and first_name.strip()) or (last_name and last_name.strip()) or (full_name and full_name.strip()))
    has_company = bool((domain and domain.strip()) or (company_name and company_name.strip()))
    if not has_name or not has_company:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            }
        )
        return None

    payload: dict[str, Any] = {}
    if full_name:
        payload["full_name"] = full_name
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if domain:
        payload["domain"] = domain
    elif company_name:
        payload["company_name"] = company_name

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/email-finder",
            headers={
                "X-API-Key": settings.leadmagic_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    email = body.get("email")
    attempts.append(
        {
            "provider": "leadmagic",
            "action": "resolve_email",
            "status": "found" if email else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "provider_status": body.get("status"),
            "raw_response": body,
        }
    )
    return email


async def _parallel_findability_email(
    *,
    full_name: str,
    company: str,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    if not settings.parallel_api_key:
        attempts.append(
            {
                "provider": "parallel",
                "action": "findability_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None

    start_ms = _now_ms()
    task_input = {"full_name": full_name, "company": company}
    payload = {
        "input": json.dumps(task_input),
        "processor": settings.parallel_processor,
        "task_spec": {
            "input_schema": {
                "type": "json",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "full_name": {"type": "string", "description": "Full name of the person"},
                        "company": {"type": "string", "description": "Company where the person works"},
                    },
                },
            },
            "output_schema": {
                "type": "json",
                "json_schema": {
                    "type": "object",
                    "properties": {
                        "email": {"type": "string", "description": "Work email address"},
                        "linkedin_url": {"type": "string", "description": "LinkedIn profile URL"},
                    },
                },
            },
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.parallel.ai/v1/tasks/runs",
            headers={
                "x-api-key": settings.parallel_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "parallel",
                "action": "findability_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    email = _deep_find_first_str(
        body,
        {"email"},
    )
    attempts.append(
        {
            "provider": "parallel",
            "action": "findability_email",
            "status": "found" if email else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return email


async def _millionverifier_verify(
    *,
    email: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.millionverifier_api_key:
        attempts.append(
            {
                "provider": "millionverifier",
                "action": "verify_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            "https://api.millionverifier.com/api/v3",
            params={
                "api": settings.millionverifier_api_key,
                "email": email,
                "timeout": settings.millionverifier_timeout_seconds,
            },
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "millionverifier",
                "action": "verify_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    result = str(body.get("result") or "").lower()
    inconclusive = result in INCONCLUSIVE_MILLIONVERIFIER_RESULTS or not result
    attempts.append(
        {
            "provider": "millionverifier",
            "action": "verify_email",
            "status": "verified",
            "provider_status": result,
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return {
        "provider": "millionverifier",
        "status": result,
        "inconclusive": inconclusive,
        "raw_response": body,
    }


async def _reoon_verify(
    *,
    email: str,
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.reoon_api_key:
        attempts.append(
            {
                "provider": "reoon",
                "action": "verify_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=90.0) as client:
        res = await client.get(
            "https://emailverifier.reoon.com/api/v1/verify",
            params={
                "email": email,
                "key": settings.reoon_api_key,
                "mode": settings.reoon_mode,
            },
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "reoon",
                "action": "verify_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    status = str(body.get("status") or "").lower()
    inconclusive = status in INCONCLUSIVE_REOON_STATUSES or not status
    attempts.append(
        {
            "provider": "reoon",
            "action": "verify_email",
            "status": "verified",
            "provider_status": status,
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return {
        "provider": "reoon",
        "status": status,
        "inconclusive": inconclusive,
        "raw_response": body,
    }


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
    if not settings.leadmagic_api_key:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None

    payload: dict[str, Any] = {}
    if profile_url:
        payload["profile_url"] = profile_url
    if work_email:
        payload["work_email"] = work_email
    if personal_email:
        payload["personal_email"] = personal_email
    if not payload:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            }
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/people/mobile-finder",
            headers={
                "X-API-Key": settings.leadmagic_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "resolve_mobile_phone",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    mobile = body.get("mobile_number")
    attempts.append(
        {
            "provider": "leadmagic",
            "action": "resolve_mobile_phone",
            "status": "found" if mobile else "not_found",
            "provider_status": body.get("message"),
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return mobile


async def _blitzapi_phone_enrich(
    *,
    person_linkedin_url: str | None,
    attempts: list[dict[str, Any]],
) -> str | None:
    settings = get_settings()
    if not settings.blitzapi_api_key:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None
    if not person_linkedin_url:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "resolve_mobile_phone",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            }
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/phone",
            headers={
                "x-api-key": settings.blitzapi_api_key,
                "Content-Type": "application/json",
            },
            json={"person_linkedin_url": person_linkedin_url},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "resolve_mobile_phone",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    phone = body.get("phone")
    attempts.append(
        {
            "provider": "blitzapi",
            "action": "resolve_mobile_phone",
            "status": "found" if body.get("found") and phone else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return phone if body.get("found") else None


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

    return {
        "run_id": run_id,
        "operation_id": "person.contact.resolve_email",
        "status": "found" if resolved_email else "not_found",
        "output": {
            "email": resolved_email,
            "source_provider": source,
            "verification": verification,
        },
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

    return {
        "run_id": run_id,
        "operation_id": "person.contact.verify_email",
        "status": "verified" if verification else "failed",
        "output": {
            "email": email,
            "verification": verification,
        },
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

    return {
        "run_id": run_id,
        "operation_id": "person.contact.resolve_mobile_phone",
        "status": "found" if mobile_phone else "not_found",
        "output": {
            "mobile_phone": mobile_phone,
            "source_provider": source,
        },
        "provider_attempts": attempts,
    }

