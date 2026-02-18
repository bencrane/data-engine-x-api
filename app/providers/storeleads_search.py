from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(float(stripped))
        except ValueError:
            return None
    return None


def _build_storeleads_query_params(filters: dict[str, Any]) -> dict[str, Any]:
    params: dict[str, Any] = {}

    def _set_if_present(target_key: str, value: Any) -> None:
        if value is None:
            return
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                params[target_key] = cleaned
            return
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            params[target_key] = int(value)

    _set_if_present("f:p", filters.get("platform"))
    _set_if_present("f:cc", filters.get("country_code"))
    _set_if_present("f:an", filters.get("app_installed"))
    _set_if_present("f:cat", filters.get("category"))
    _set_if_present("f:rk:min", filters.get("rank_min"))
    _set_if_present("f:rk:max", filters.get("rank_max"))
    _set_if_present("f:mas:min", filters.get("monthly_app_spend_min"))
    _set_if_present("f:mas:max", filters.get("monthly_app_spend_max"))

    domain_state = _as_str(filters.get("domain_state")) or "Active"
    params["f:ds"] = domain_state
    params["page"] = _as_int(filters.get("page")) if _as_int(filters.get("page")) is not None else 0
    page_size = _as_int(filters.get("page_size"))
    params["page_size"] = page_size if page_size is not None else 50

    return params


def _map_domain_to_canonical(domain: dict[str, Any]) -> dict[str, Any]:
    return {
        "merchant_name": _as_str(domain.get("merchant_name")),
        "domain": _as_str(domain.get("name")) or _as_str(domain.get("domain")),
        "platform": _as_str(domain.get("platform")),
        "plan": _as_str(domain.get("plan")),
        "estimated_monthly_sales_cents": _as_int(domain.get("estimated_sales")),
        "rank": _as_int(domain.get("rank")),
        "country_code": _as_str(domain.get("country_code")),
        "description": _as_str(domain.get("description")),
    }


async def search_ecommerce(
    *,
    api_key: str | None,
    filters: dict[str, Any],
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_search_ecommerce",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    params = _build_storeleads_query_params(filters)
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(
            "https://storeleads.app/json/api/v1/all/domain",
            params=params,
            headers={"Authorization": api_key},
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_search_ecommerce",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    raw_domains = _as_list(_as_dict(body).get("domains"))
    mapped_results = [_map_domain_to_canonical(_as_dict(item)) for item in raw_domains]
    result_count = len(mapped_results)

    return {
        "attempt": {
            "provider": "storeleads",
            "action": "company_search_ecommerce",
            "status": "found" if result_count else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": mapped_results,
            "result_count": result_count,
        },
    }
