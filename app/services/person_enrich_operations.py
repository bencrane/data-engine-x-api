from __future__ import annotations

import uuid
from typing import Any

import httpx

from app.config import get_settings
from app.contracts.person_enrich import PersonEnrichProfileOutput
from app.providers import ampleleads
from app.providers.common import now_ms, parse_json_or_raw


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off"}:
            return False
    return default


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def _domain_from_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if not normalized:
        return None
    if normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    if normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    normalized = normalized.split("/")[0]
    if normalized.startswith("www."):
        normalized = normalized[len("www.") :]
    return normalized or None


def _first_non_empty(items: list[Any]) -> str | None:
    for item in items:
        parsed = _as_non_empty_str(item)
        if parsed:
            return parsed
    return None


def _first_current_role(roles: list[Any]) -> dict[str, Any]:
    for role in roles:
        role_dict = _as_dict(role)
        if role_dict.get("current") is True:
            return role_dict
    return _as_dict(roles[0]) if roles else {}


def _normalize_skill_strings(value: Any) -> list[str] | None:
    normalized: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            cleaned = item.strip()
            if cleaned:
                normalized.append(cleaned)
            continue
        item_dict = _as_dict(item)
        skill_name = _first_non_empty(
            [
                item_dict.get("name"),
                item_dict.get("skill"),
                item_dict.get("title"),
            ]
        )
        if skill_name:
            normalized.append(skill_name)
    return normalized or None


def _has_prospeo_identifier(
    *,
    first_name: str | None,
    last_name: str | None,
    full_name: str | None,
    linkedin_url: str | None,
    email: str | None,
    person_id: str | None,
    company_name: str | None,
    company_domain: str | None,
    company_linkedin_url: str | None,
) -> bool:
    has_company = bool(company_name or company_domain or company_linkedin_url)
    has_first_last = bool(first_name and last_name and has_company)
    has_full_name = bool(full_name and has_company)
    return bool(has_first_last or has_full_name or linkedin_url or email or person_id)


async def _prospeo_enrich_person(
    *,
    linkedin_url: str | None,
    first_name: str | None,
    last_name: str | None,
    full_name: str | None,
    company_domain: str | None,
    company_name: str | None,
    company_linkedin_url: str | None,
    email: str | None,
    person_id: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.prospeo_api_key:
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    if not _has_prospeo_identifier(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        linkedin_url=linkedin_url,
        email=email,
        person_id=person_id,
        company_name=company_name,
        company_domain=company_domain,
        company_linkedin_url=company_linkedin_url,
    ):
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    payload_data = {
        "first_name": first_name,
        "last_name": last_name,
        "full_name": full_name,
        "linkedin_url": linkedin_url,
        "email": email,
        "person_id": person_id,
        "company_name": company_name,
        "company_website": company_domain,
        "company_linkedin_url": company_linkedin_url,
    }
    payload_data = {key: value for key, value in payload_data.items() if value}

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.prospeo.io/enrich-person",
            headers={
                "X-KEY": settings.prospeo_api_key,
                "Content-Type": "application/json",
            },
            json={"data": payload_data},
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400 or body.get("error") is True:
        error_code = _as_non_empty_str(body.get("error_code"))
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "person_enrich_profile",
                "status": "not_found" if error_code == "NO_MATCH" else "failed",
                "http_status": response.status_code,
                "provider_status": error_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    person = _as_dict(body.get("person"))
    company = _as_dict(body.get("company"))
    if not person:
        return {
            "attempt": {
                "provider": "prospeo",
                "action": "person_enrich_profile",
                "status": "not_found",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    job_history = _as_list(person.get("job_history"))
    current_role = _first_current_role(job_history)
    department = _first_non_empty(_as_list(current_role.get("departments")))

    mapped = {
        "full_name": _first_non_empty([person.get("full_name"), person.get("name")]),
        "first_name": _as_non_empty_str(person.get("first_name")),
        "last_name": _as_non_empty_str(person.get("last_name")),
        "linkedin_url": _first_non_empty([person.get("linkedin_url"), linkedin_url]),
        "headline": _as_non_empty_str(person.get("headline")),
        "current_title": _first_non_empty([person.get("current_job_title"), current_role.get("title")]),
        "seniority": _as_non_empty_str(current_role.get("seniority")),
        "department": department,
        "bio": _as_non_empty_str(person.get("bio")),
        "location": _first_non_empty(
            [
                _as_non_empty_str(_as_dict(person.get("location")).get("city")),
                _as_non_empty_str(_as_dict(person.get("location")).get("country")),
            ]
        ),
        "country": _as_non_empty_str(_as_dict(person.get("location")).get("country")),
        "current_company_name": _as_non_empty_str(company.get("name")),
        "current_company_domain": _as_non_empty_str(company.get("domain")),
        "current_company_linkedin_url": _as_non_empty_str(company.get("linkedin_url")),
        "work_history": job_history or None,
        "education": _as_list(person.get("education")) or None,
        "skills": _normalize_skill_strings(person.get("skills")),
        "email": _as_non_empty_str(_as_dict(person.get("email")).get("email")),
        "email_status": _as_non_empty_str(_as_dict(person.get("email")).get("status")),
        "mobile_phone": _as_non_empty_str(_as_dict(person.get("mobile")).get("mobile")),
        "mobile_status": _as_non_empty_str(_as_dict(person.get("mobile")).get("status")),
        "source_provider": "prospeo",
    }
    return {
        "attempt": {
            "provider": "prospeo",
            "action": "person_enrich_profile",
            "status": "found",
            "provider_status": "free_enrichment" if body.get("free_enrichment") else "ok",
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped,
    }


def _map_ampleleads_to_canonical(mapped: dict[str, Any]) -> dict[str, Any]:
    work_history = _as_list(mapped.get("work_history"))
    current_role = _first_current_role(work_history)
    contact_details = _as_dict(mapped.get("contact_details"))

    return {
        "full_name": _as_non_empty_str(mapped.get("full_name")),
        "first_name": _as_non_empty_str(mapped.get("first_name")),
        "last_name": _as_non_empty_str(mapped.get("last_name")),
        "linkedin_url": _as_non_empty_str(mapped.get("linkedin_url")),
        "headline": _as_non_empty_str(mapped.get("headline")),
        "current_title": _first_non_empty(
            [
                current_role.get("title"),
                current_role.get("position"),
                current_role.get("position_title"),
                current_role.get("role"),
            ]
        ),
        "location": _as_non_empty_str(mapped.get("location")),
        "work_history": work_history or None,
        "education": _as_list(mapped.get("education")) or None,
        "skills": _normalize_skill_strings(mapped.get("skills")),
        "recommendations": _as_list(mapped.get("recommendations")) or None,
        "people_also_viewed": _as_list(mapped.get("people_also_viewed")) or None,
        "email": _first_non_empty(
            [
                contact_details.get("email"),
                contact_details.get("work_email"),
                contact_details.get("email_address"),
            ]
        ),
        "mobile_phone": _first_non_empty(
            [
                contact_details.get("mobile"),
                contact_details.get("phone"),
                contact_details.get("phone_number"),
            ]
        ),
        "source_provider": "ampleleads",
    }


async def _leadmagic_profile_search(*, linkedin_url: str | None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.leadmagic_api_key:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    if not linkedin_url:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.leadmagic.io/v1/people/profile-search",
            headers={
                "X-API-Key": settings.leadmagic_api_key,
                "Content-Type": "application/json",
            },
            json={"profile_url": linkedin_url},
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "person_enrich_profile",
                "status": "not_found" if response.status_code == 404 else "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    message = _as_non_empty_str(body.get("message"))
    message_lower = message.lower() if message else ""
    if "not found" in message_lower:
        return {
            "attempt": {
                "provider": "leadmagic",
                "action": "person_enrich_profile",
                "status": "not_found",
                "provider_status": message,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mapped = {
        "full_name": _as_non_empty_str(body.get("full_name")),
        "first_name": _as_non_empty_str(body.get("first_name")),
        "last_name": _as_non_empty_str(body.get("last_name")),
        "linkedin_url": _first_non_empty([body.get("profile_url"), linkedin_url]),
        "current_title": _as_non_empty_str(body.get("professional_title")),
        "bio": _as_non_empty_str(body.get("bio")),
        "location": _as_non_empty_str(body.get("location")),
        "country": _as_non_empty_str(body.get("country")),
        "current_company_name": _as_non_empty_str(body.get("company_name")),
        "current_company_domain": _domain_from_value(body.get("company_website")),
        "work_history": _as_list(body.get("work_experience")) or None,
        "education": _as_list(body.get("education")) or None,
        "skills": _normalize_skill_strings(body.get("skills")),
        "certifications": _as_list(body.get("certifications")) or None,
        "honors": _as_list(body.get("honors")) or None,
        "total_tenure_years": _as_non_empty_str(body.get("total_tenure_years")),
        "follower_count": _as_int(body.get("follower_count")),
        "connections_count": _as_int(body.get("connections_count")),
        "source_provider": "leadmagic",
    }

    has_signal = bool(
        mapped.get("full_name")
        or mapped.get("current_title")
        or mapped.get("work_history")
        or mapped.get("education")
    )
    return {
        "attempt": {
            "provider": "leadmagic",
            "action": "person_enrich_profile",
            "status": "found" if has_signal else "not_found",
            "provider_status": message,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped if has_signal else None,
    }


async def execute_person_enrich_profile(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []

    linkedin_url = _as_non_empty_str(input_data.get("linkedin_url"))
    first_name = _as_non_empty_str(input_data.get("first_name"))
    last_name = _as_non_empty_str(input_data.get("last_name"))
    full_name = _as_non_empty_str(input_data.get("full_name"))
    company_domain = _domain_from_value(input_data.get("company_domain"))
    company_name = _as_non_empty_str(input_data.get("company_name"))
    company_linkedin_url = _as_non_empty_str(input_data.get("company_linkedin_url"))
    email = _as_non_empty_str(input_data.get("email"))
    person_id = _as_non_empty_str(input_data.get("person_id"))
    step_config = _as_dict(input_data.get("step_config"))
    include_work_history = _as_bool(
        input_data.get("include_work_history"),
        default=_as_bool(step_config.get("include_work_history"), default=False),
    )

    prospeo_result = await _prospeo_enrich_person(
        linkedin_url=linkedin_url,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        company_domain=company_domain,
        company_name=company_name,
        company_linkedin_url=company_linkedin_url,
        email=email,
        person_id=person_id,
    )
    attempts.append(prospeo_result["attempt"])
    if prospeo_result.get("mapped"):
        try:
            output = PersonEnrichProfileOutput.model_validate(prospeo_result["mapped"]).model_dump()
        except Exception as exc:  # noqa: BLE001
            return {
                "run_id": run_id,
                "operation_id": "person.enrich.profile",
                "status": "failed",
                "provider_attempts": attempts,
                "error": {"code": "output_validation_failed", "message": str(exc)},
            }
        return {
            "run_id": run_id,
            "operation_id": "person.enrich.profile",
            "status": "found",
            "output": output,
            "provider_attempts": attempts,
        }

    if include_work_history:
        ampleleads_result = await ampleleads.enrich_person(
            api_key=get_settings().ampleleads_api_key,
            linkedin_url=linkedin_url,
        )
        attempts.append(ampleleads_result["attempt"])
        if ampleleads_result.get("mapped"):
            canonical = _map_ampleleads_to_canonical(_as_dict(ampleleads_result["mapped"]))
            try:
                output = PersonEnrichProfileOutput.model_validate(canonical).model_dump()
            except Exception as exc:  # noqa: BLE001
                return {
                    "run_id": run_id,
                    "operation_id": "person.enrich.profile",
                    "status": "failed",
                    "provider_attempts": attempts,
                    "error": {"code": "output_validation_failed", "message": str(exc)},
                }
            return {
                "run_id": run_id,
                "operation_id": "person.enrich.profile",
                "status": "found",
                "output": output,
                "provider_attempts": attempts,
            }

    leadmagic_result = await _leadmagic_profile_search(linkedin_url=linkedin_url)
    attempts.append(leadmagic_result["attempt"])
    if leadmagic_result.get("mapped"):
        try:
            output = PersonEnrichProfileOutput.model_validate(leadmagic_result["mapped"]).model_dump()
        except Exception as exc:  # noqa: BLE001
            return {
                "run_id": run_id,
                "operation_id": "person.enrich.profile",
                "status": "failed",
                "provider_attempts": attempts,
                "error": {"code": "output_validation_failed", "message": str(exc)},
            }
        return {
            "run_id": run_id,
            "operation_id": "person.enrich.profile",
            "status": "found",
            "output": output,
            "provider_attempts": attempts,
        }

    return {
        "run_id": run_id,
        "operation_id": "person.enrich.profile",
        "status": "not_found",
        "provider_attempts": attempts,
    }
