from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_ads import GoogleAdsOutput, LinkedInAdsOutput, MetaAdsOutput
from app.providers import adyntel


def _normalize_domain(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
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
    linkedin_page_id = input_data.get("linkedin_page_id")
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
    if input_data.get("continuation_token"):
        payload["continuation_token"] = input_data["continuation_token"]

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
    output = LinkedInAdsOutput.model_validate(mapped).model_dump()
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
    facebook_url = input_data.get("facebook_url")
    keyword = input_data.get("keyword")

    payload: dict[str, Any] = {}
    endpoint = "facebook"
    if isinstance(keyword, str) and keyword.strip():
        endpoint = "facebook_ad_search"
        payload["keyword"] = keyword.strip()
        if input_data.get("country_code"):
            payload["country_code"] = input_data["country_code"]
    else:
        if company_domain:
            payload["company_domain"] = company_domain
        if isinstance(facebook_url, str) and facebook_url.strip():
            payload["facebook_url"] = facebook_url.strip()
        if input_data.get("continuation_token"):
            payload["continuation_token"] = input_data["continuation_token"]
        if input_data.get("media_type"):
            payload["media_type"] = input_data["media_type"]
        if input_data.get("country_code"):
            payload["country_code"] = input_data["country_code"]
        if input_data.get("active_status"):
            payload["active_status"] = input_data["active_status"]

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
    output = MetaAdsOutput.model_validate(mapped).model_dump()
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
    if input_data.get("media_type"):
        payload["media_type"] = input_data["media_type"]
    if input_data.get("continuation_token"):
        payload["continuation_token"] = input_data["continuation_token"]

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
    output = GoogleAdsOutput.model_validate(mapped).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.google",
        "status": "found" if ads else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }

