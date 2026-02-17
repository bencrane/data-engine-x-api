from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_ads import GoogleAdsOutput, LinkedInAdsOutput, MetaAdsOutput
from app.providers import adyntel


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _normalize_domain(value: Any) -> str | None:
    if not isinstance(value, str):
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


def _validate_adyntel_settings(attempts: list[dict[str, Any]], action: str) -> tuple[str | None, str | None]:
    settings = get_settings()
    validation = adyntel.validate_credentials(
        api_key=settings.adyntel_api_key,
        email=settings.adyntel_account_email,
        action=action,
    )
    if validation is not None:
        attempts.append(validation["attempt"])
        return None, None
    return settings.adyntel_api_key, settings.adyntel_account_email


def _normalize_optional_text_fields(
    input_data: dict[str, Any],
    keys: set[str],
) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for key in keys:
        value = _as_non_empty_str(input_data.get(key))
        if value:
            normalized[key] = value
    return normalized


async def execute_company_ads_search_linkedin(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    api_key, email = _validate_adyntel_settings(attempts, "search_linkedin_ads")
    if not api_key or not email:
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.linkedin",
            "status": "failed",
            "provider_attempts": attempts,
        }

    company_domain = _normalize_domain(input_data.get("company_domain"))
    linkedin_page_id = _as_non_empty_str(input_data.get("linkedin_page_id"))
    if not company_domain and not linkedin_page_id:
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.linkedin",
            "status": "failed",
            "missing_inputs": ["company_domain|linkedin_page_id"],
            "provider_attempts": attempts,
        }

    payload: dict[str, Any] = {}
    if company_domain:
        payload["company_domain"] = company_domain
    if linkedin_page_id:
        payload["linkedin_page_id"] = linkedin_page_id
    optional = _normalize_optional_text_fields(input_data, {"continuation_token"})
    if "continuation_token" in optional:
        payload["continuation_token"] = optional["continuation_token"]

    settings = get_settings()
    result = await adyntel.search_linkedin_ads(
        api_key=api_key,
        email=email,
        timeout_seconds=settings.adyntel_timeout_seconds,
        payload=payload,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    ads = mapped.get("ads") or []
    try:
        output = LinkedInAdsOutput.model_validate(mapped).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.linkedin",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.linkedin",
        "status": "found" if ads else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_ads_search_meta(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    api_key, email = _validate_adyntel_settings(attempts, "search_meta_ads")
    if not api_key or not email:
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.meta",
            "status": "failed",
            "provider_attempts": attempts,
        }

    company_domain = _normalize_domain(input_data.get("company_domain"))
    facebook_url = _as_non_empty_str(input_data.get("facebook_url"))
    keyword = _as_non_empty_str(input_data.get("keyword"))
    optional = _normalize_optional_text_fields(
        input_data,
        {"country_code", "continuation_token", "media_type", "active_status"},
    )

    payload: dict[str, Any] = {}
    endpoint = "facebook"
    if keyword:
        endpoint = "facebook_ad_search"
        payload["keyword"] = keyword
        if "country_code" in optional:
            payload["country_code"] = optional["country_code"]
    else:
        if company_domain:
            payload["company_domain"] = company_domain
        if facebook_url:
            payload["facebook_url"] = facebook_url
        for key in {"continuation_token", "media_type", "country_code", "active_status"}:
            if key in optional:
                payload[key] = optional[key]

        if "company_domain" not in payload and "facebook_url" not in payload:
            return {
                "run_id": run_id,
                "operation_id": "company.ads.search.meta",
                "status": "failed",
                "missing_inputs": ["company_domain|facebook_url|keyword"],
                "provider_attempts": attempts,
            }

    settings = get_settings()
    result = await adyntel.search_meta_ads(
        api_key=api_key,
        email=email,
        timeout_seconds=settings.adyntel_timeout_seconds,
        endpoint=endpoint,
        payload=payload,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    results = mapped.get("results") or []
    try:
        output = MetaAdsOutput.model_validate(mapped).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.meta",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.meta",
        "status": "found" if results else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_ads_search_google(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    api_key, email = _validate_adyntel_settings(attempts, "search_google_ads")
    if not api_key or not email:
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.google",
            "status": "failed",
            "provider_attempts": attempts,
        }

    company_domain = _normalize_domain(input_data.get("company_domain"))
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.google",
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    payload: dict[str, Any] = {"company_domain": company_domain}
    optional = _normalize_optional_text_fields(input_data, {"media_type", "continuation_token"})
    if "media_type" in optional:
        payload["media_type"] = optional["media_type"]
    if "continuation_token" in optional:
        payload["continuation_token"] = optional["continuation_token"]

    settings = get_settings()
    result = await adyntel.search_google_ads(
        api_key=api_key,
        email=email,
        timeout_seconds=settings.adyntel_timeout_seconds,
        payload=payload,
    )
    attempts.append(result["attempt"])
    mapped = result.get("mapped") or {}
    ads = mapped.get("ads") or []
    try:
        output = GoogleAdsOutput.model_validate(mapped).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.ads.search.google",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.google",
        "status": "found" if ads else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }

