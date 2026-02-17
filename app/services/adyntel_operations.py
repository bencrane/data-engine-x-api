from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from app.config import get_settings


def _now_ms() -> int:
    return int(time.time() * 1000)


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


async def _adyntel_post(
    *,
    endpoint: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    settings = get_settings()
    url = f"https://api.adyntel.com/{endpoint}"
    async with httpx.AsyncClient(timeout=float(settings.adyntel_timeout_seconds)) as client:
        res = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=payload,
        )
        if res.status_code == 204:
            return res.status_code, {}
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}
    return res.status_code, body


def _validate_adyntel_settings(attempts: list[dict[str, Any]], action: str) -> tuple[str | None, str | None]:
    settings = get_settings()
    if not settings.adyntel_api_key:
        attempts.append(
            {
                "provider": "adyntel",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            }
        )
        return None, None
    if not settings.adyntel_email:
        attempts.append(
            {
                "provider": "adyntel",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_email",
            }
        )
        return None, None
    return settings.adyntel_api_key, settings.adyntel_email


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

    payload: dict[str, Any] = {"api_key": api_key, "email": email}
    if company_domain:
        payload["company_domain"] = company_domain
    if linkedin_page_id:
        payload["linkedin_page_id"] = linkedin_page_id
    if input_data.get("continuation_token"):
        payload["continuation_token"] = input_data["continuation_token"]

    start_ms = _now_ms()
    status_code, body = await _adyntel_post(endpoint="linkedin", payload=payload)
    attempts.append(
        {
            "provider": "adyntel",
            "action": "search_linkedin_ads",
            "status": "found" if status_code == 200 and (body.get("ads") or []) else "not_found" if status_code == 204 else "failed",
            "http_status": status_code,
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )

    ads = body.get("ads") or []
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.linkedin",
        "status": "found" if ads else "not_found",
        "output": {
            "ads": ads,
            "ads_count": len(ads),
            "continuation_token": body.get("continuation_token"),
            "is_last_page": body.get("is_last_page"),
            "page_id": body.get("page_id"),
            "total_ads": body.get("total_ads"),
        },
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

    payload: dict[str, Any] = {"api_key": api_key, "email": email}
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

    start_ms = _now_ms()
    status_code, body = await _adyntel_post(endpoint=endpoint, payload=payload)
    attempts.append(
        {
            "provider": "adyntel",
            "action": "search_meta_ads",
            "status": "found" if status_code == 200 and (body.get("results") or body.get("ads") or []) else "not_found" if status_code == 204 else "failed",
            "http_status": status_code,
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )

    results = body.get("results") or body.get("ads") or []
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.meta",
        "status": "found" if results else "not_found",
        "output": {
            "results": results,
            "results_count": len(results),
            "continuation_token": body.get("continuation_token"),
            "number_of_ads": body.get("number_of_ads"),
            "is_result_complete": body.get("is_result_complete"),
            "search_type": body.get("search_type"),
            "endpoint_used": endpoint,
        },
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

    payload: dict[str, Any] = {
        "api_key": api_key,
        "email": email,
        "company_domain": company_domain,
    }
    if input_data.get("media_type"):
        payload["media_type"] = input_data["media_type"]
    if input_data.get("continuation_token"):
        payload["continuation_token"] = input_data["continuation_token"]

    start_ms = _now_ms()
    status_code, body = await _adyntel_post(endpoint="google", payload=payload)
    attempts.append(
        {
            "provider": "adyntel",
            "action": "search_google_ads",
            "status": "found" if status_code == 200 and (body.get("ads") or []) else "not_found" if status_code == 204 else "failed",
            "http_status": status_code,
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )

    ads = body.get("ads") or []
    return {
        "run_id": run_id,
        "operation_id": "company.ads.search.google",
        "status": "found" if ads else "not_found",
        "output": {
            "ads": ads,
            "ads_count": len(ads),
            "continuation_token": body.get("continuation_token"),
            "country_code": body.get("country_code"),
        },
        "provider_attempts": attempts,
    }

