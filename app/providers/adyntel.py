from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _flatten_results(value: Any) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            flat.append(item)
            continue
        if isinstance(item, list):
            for nested in item:
                if isinstance(nested, dict):
                    flat.append(nested)
    return flat


def _extract_provider_error(body: dict[str, Any]) -> str | None:
    error_obj = _as_dict(body.get("error"))
    for candidate in (error_obj.get("message"), body.get("message")):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


async def _post(
    *,
    endpoint: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> tuple[int, dict[str, Any]]:
    url = f"https://api.adyntel.com/{endpoint}"
    async with httpx.AsyncClient(timeout=float(timeout_seconds)) as client:
        res = await client.post(url, headers={"Content-Type": "application/json"}, json=payload)
        if res.status_code == 204:
            return res.status_code, {}
        return res.status_code, parse_json_or_raw(res.text, res.json)


def validate_credentials(
    *,
    api_key: str | None,
    email: str | None,
    action: str,
) -> ProviderAdapterResult | None:
    if not api_key:
        return {
            "attempt": {"provider": "adyntel", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"},
            "mapped": None,
        }
    if not email:
        return {
            "attempt": {"provider": "adyntel", "action": action, "status": "skipped", "skip_reason": "missing_provider_email"},
            "mapped": None,
        }
    return None


async def search_linkedin_ads(
    *,
    api_key: str,
    email: str,
    timeout_seconds: int,
    payload: dict[str, Any],
) -> ProviderAdapterResult:
    start_ms = now_ms()
    status_code, body = await _post(endpoint="linkedin", payload={"api_key": api_key, "email": email, **payload}, timeout_seconds=timeout_seconds)
    ads = _flatten_results(body.get("ads"))
    provider_error = _extract_provider_error(body)
    status = "found" if status_code == 200 and ads else "not_found" if status_code == 204 else "failed"
    if status_code == 200 and not ads and provider_error:
        status = "failed"
    return {
        "attempt": {
            "provider": "adyntel",
            "action": "search_linkedin_ads",
            "status": status,
            "http_status": status_code,
            "provider_status": provider_error,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "ads": ads,
            "ads_count": len(ads),
            "continuation_token": body.get("continuation_token"),
            "is_last_page": body.get("is_last_page"),
            "page_id": body.get("page_id"),
            "total_ads": body.get("total_ads"),
        },
    }


async def search_meta_ads(
    *,
    api_key: str,
    email: str,
    timeout_seconds: int,
    endpoint: str,
    payload: dict[str, Any],
) -> ProviderAdapterResult:
    start_ms = now_ms()
    status_code, body = await _post(endpoint=endpoint, payload={"api_key": api_key, "email": email, **payload}, timeout_seconds=timeout_seconds)
    results = _flatten_results(body.get("results"))
    if not results:
        results = _flatten_results(body.get("ads"))
    provider_error = _extract_provider_error(body)
    status = "found" if status_code == 200 and results else "not_found" if status_code == 204 else "failed"
    if status_code == 200 and not results and provider_error:
        status = "failed"
    return {
        "attempt": {
            "provider": "adyntel",
            "action": "search_meta_ads",
            "status": status,
            "http_status": status_code,
            "provider_status": provider_error,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": results,
            "results_count": len(results),
            "continuation_token": body.get("continuation_token"),
            "number_of_ads": body.get("number_of_ads"),
            "is_result_complete": body.get("is_result_complete"),
            "search_type": body.get("search_type"),
            "endpoint_used": endpoint,
        },
    }


async def search_google_ads(
    *,
    api_key: str,
    email: str,
    timeout_seconds: int,
    payload: dict[str, Any],
) -> ProviderAdapterResult:
    start_ms = now_ms()
    status_code, body = await _post(endpoint="google", payload={"api_key": api_key, "email": email, **payload}, timeout_seconds=timeout_seconds)
    ads = _flatten_results(body.get("ads"))
    provider_error = _extract_provider_error(body)
    status = "found" if status_code == 200 and ads else "not_found" if status_code == 204 else "failed"
    if status_code == 200 and not ads and provider_error:
        status = "failed"
    return {
        "attempt": {
            "provider": "adyntel",
            "action": "search_google_ads",
            "status": status,
            "http_status": status_code,
            "provider_status": provider_error,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "ads": ads,
            "ads_count": len(ads),
            "continuation_token": body.get("continuation_token"),
            "country_code": body.get("country_code"),
        },
    }
