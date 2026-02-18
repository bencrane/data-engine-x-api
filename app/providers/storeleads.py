from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


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


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _map_app(item: Any) -> dict[str, Any] | None:
    app = _as_dict(item)
    name = _as_str(app.get("name"))
    if not name:
        return None
    return {
        "name": name,
        "categories": [category for category in (_as_str(c) for c in _as_list(app.get("categories"))) if category] or None,
        "monthly_cost": _as_str(app.get("monthly_cost")),
    }


def _map_technology(item: Any) -> dict[str, Any] | None:
    technology = _as_dict(item)
    name = _as_str(technology.get("name"))
    if not name:
        return None
    return {
        "name": name,
        "description": _as_str(technology.get("description")),
    }


def _map_contact(item: Any) -> dict[str, Any] | None:
    contact = _as_dict(item)
    contact_type = _as_str(contact.get("type"))
    value = _as_str(contact.get("value"))
    if not contact_type or not value:
        return None
    return {
        "type": contact_type,
        "value": value,
        "source": _as_str(contact.get("source")),
    }


def _map_domain(raw: dict[str, Any]) -> dict[str, Any]:
    installed_apps = [app for app in (_map_app(item) for item in _as_list(raw.get("apps"))) if app]
    technologies = [tech for tech in (_map_technology(item) for item in _as_list(raw.get("technologies"))) if tech]
    contact_info = [contact for contact in (_map_contact(item) for item in _as_list(raw.get("contact_info"))) if contact]
    return {
        "merchant_name": _as_str(raw.get("merchant_name")),
        "ecommerce_platform": _as_str(raw.get("platform")),
        "ecommerce_plan": _as_str(raw.get("plan")),
        "estimated_monthly_sales_cents": _as_int(raw.get("estimated_sales")),
        "employee_count": _as_int(raw.get("employee_count")),
        "product_count": _as_int(raw.get("product_count")),
        "global_rank": _as_int(raw.get("rank")),
        "platform_rank": _as_int(raw.get("platform_rank")),
        "monthly_app_spend_cents": _as_int(raw.get("monthly_app_spend")),
        "installed_apps": installed_apps or None,
        "technologies": technologies or None,
        "contact_info": contact_info or None,
        "country_code": _as_str(raw.get("country_code")),
        "city": _as_str(raw.get("city")),
        "domain_state": _as_str(raw.get("state")),
        "description": _as_str(raw.get("description")),
        "store_created_at": _as_str(raw.get("created_at")),
        "shipping_carriers": [carrier for carrier in (_as_str(v) for v in _as_list(raw.get("shipping_carriers"))) if carrier] or None,
        "sales_carriers": [carrier for carrier in (_as_str(v) for v in _as_list(raw.get("sales_carriers"))) if carrier] or None,
        "features": [feature for feature in (_as_str(v) for v in _as_list(raw.get("features"))) if feature] or None,
    }


async def enrich_ecommerce(
    *,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_enrich_ecommerce",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    normalized_domain = _as_str(domain)
    if not normalized_domain:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_enrich_ecommerce",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"https://storeleads.app/json/api/v1/all/domain/{normalized_domain}",
            headers={"Authorization": api_key},
        )
        body = parse_json_or_raw(response.text, response.json)

    if response.status_code == 404:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_enrich_ecommerce",
                "status": "not_found",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }
    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "storeleads",
                "action": "company_enrich_ecommerce",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mapped = _map_domain(body)
    has_payload = any(value is not None for value in mapped.values())
    return {
        "attempt": {
            "provider": "storeleads",
            "action": "company_enrich_ecommerce",
            "status": "found" if has_payload else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped if has_payload else None,
    }
