from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _map_ampleleads_person(data: dict[str, Any], linkedin_url: str) -> dict[str, Any]:
    first_name = _as_non_empty_str(data.get("first_name"))
    last_name = _as_non_empty_str(data.get("last_name"))
    full_name = " ".join(part for part in [first_name, last_name] if part) or None
    if not full_name:
        full_name = _as_non_empty_str(data.get("full_name"))

    return {
        "full_name": full_name,
        "first_name": first_name,
        "last_name": last_name,
        "linkedin_url": _as_non_empty_str(data.get("linkedin_url")) or linkedin_url,
        "headline": _as_non_empty_str(data.get("headline")),
        "location": _as_non_empty_str(data.get("location")),
        "contact_details": _as_dict(data.get("contact_details")) or None,
        "work_history": _as_list(data.get("experience")) or None,
        "skills": _as_list(data.get("skills")) or None,
        "education": _as_list(data.get("education")) or None,
        "recommendations": _as_list(data.get("recommendations")) or None,
        "people_also_viewed": _as_list(data.get("people_also_viewed")) or None,
        "raw": data,
    }


async def enrich_person(
    *,
    api_key: str | None,
    linkedin_url: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "ampleleads",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_linkedin_url = _as_non_empty_str(linkedin_url)
    if not normalized_linkedin_url:
        return {
            "attempt": {
                "provider": "ampleleads",
                "action": "person_enrich_profile",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            "https://api.ampleleads.io/v1/linkedin/person/enrich",
            params={"api_key": api_key},
            headers={"Content-Type": "application/json", "accept": "application/json"},
            json={"url": normalized_linkedin_url},
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "ampleleads",
                "action": "person_enrich_profile",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    success = body.get("success")
    data = _as_dict(body.get("data"))
    if success is False:
        return {
            "attempt": {
                "provider": "ampleleads",
                "action": "person_enrich_profile",
                "status": "failed",
                "provider_status": _as_non_empty_str(body.get("message")) or "success_false",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    if success is True and not data:
        return {
            "attempt": {
                "provider": "ampleleads",
                "action": "person_enrich_profile",
                "status": "not_found",
                "provider_status": _as_non_empty_str(body.get("message")) or "empty_data",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mapped = _map_ampleleads_person(data, normalized_linkedin_url)
    return {
        "attempt": {
            "provider": "ampleleads",
            "action": "person_enrich_profile",
            "status": "found",
            "provider_status": _as_non_empty_str(body.get("message")) or "ok",
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped,
    }
