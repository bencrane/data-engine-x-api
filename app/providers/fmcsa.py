from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://mobile.fmcsa.dot.gov/qc/services"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "t", "yes", "y", "1"}:
            return True
        if normalized in {"false", "f", "no", "n", "0"}:
            return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return bool(value)
    return None


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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _extract_collection(body: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("content", "results", "carriers", "data"):
        raw = body.get(key)
        if isinstance(raw, list):
            return [_as_dict(item) for item in raw if isinstance(item, dict)]
        if isinstance(raw, dict):
            nested = raw.get("content")
            if isinstance(nested, list):
                return [_as_dict(item) for item in nested if isinstance(item, dict)]
    if isinstance(body, list):
        return [_as_dict(item) for item in body if isinstance(item, dict)]
    return []


def _extract_primary_record(body: dict[str, Any]) -> dict[str, Any]:
    for key in ("content", "carrier", "result", "data"):
        candidate = body.get(key)
        if isinstance(candidate, dict):
            return candidate
        if isinstance(candidate, list) and candidate:
            first = candidate[0]
            if isinstance(first, dict):
                return first
    return body


def _map_search_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "dot_number": _as_str(raw.get("dotNumber")),
        "legal_name": _as_str(raw.get("legalName")),
        "dba_name": _as_str(raw.get("dbaName")),
        "allow_to_operate": _as_bool(raw.get("allowToOperate")),
        "city": _as_str(raw.get("phyCity")),
        "state": _as_str(raw.get("phyState")),
        "phone": _as_str(raw.get("telephone")),
    }


def _map_basics_scores(raw: Any) -> list[dict[str, Any]]:
    basics = _extract_collection(_as_dict(raw))
    scores: list[dict[str, Any]] = []
    for item in basics:
        category = _as_str(item.get("basic")) or _as_str(item.get("category"))
        if not category:
            continue
        scores.append(
            {
                "category": category,
                "percentile": _as_float(item.get("percentile")),
                "violation_count": _as_int(item.get("violationCount")),
                "serious_violation_count": _as_int(item.get("seriousViolationCount")),
                "deficiency": _as_bool(item.get("deficiency")),
            }
        )
    return scores


def _map_authority(raw: Any) -> tuple[str | None, str | None]:
    authority = _extract_primary_record(_as_dict(raw))
    status = _as_str(authority.get("operatingStatus")) or _as_str(authority.get("authorityStatus"))
    grant_date = _as_str(authority.get("grantDate")) or _as_str(authority.get("authorityGrantDate"))
    return status, grant_date


async def _get_json(*, client: httpx.AsyncClient, url: str) -> tuple[int, dict[str, Any], str | None]:
    try:
        response = await client.get(url)
    except httpx.HTTPError as exc:
        return 0, {"error": str(exc)}, f"{exc.__class__.__name__}: {exc}"
    body = parse_json_or_raw(response.text, response.json)
    return response.status_code, body, None


async def search_carriers(
    *,
    api_key: str | None,
    name: str | None,
    max_results: int,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_search_fmcsa",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    normalized_name = _as_str(name)
    if not normalized_name:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_search_fmcsa",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    size = max(1, int(max_results))
    encoded_name = quote(normalized_name, safe="")
    url = f"{_BASE_URL}/carriers/name/{encoded_name}?webKey={api_key}&start=1&size={size}"
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=url)

    if request_error:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_search_fmcsa",
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_search_fmcsa",
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    raw_results = _extract_collection(body)
    mapped_results = [_map_search_item(item) for item in raw_results]
    result_count = len(mapped_results)
    return {
        "attempt": {
            "provider": "fmcsa",
            "action": "company_search_fmcsa",
            "status": "found" if result_count else "not_found",
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": mapped_results,
            "result_count": result_count,
        },
    }


async def enrich_carrier(
    *,
    api_key: str | None,
    dot_number: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_enrich_fmcsa",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_dot = _as_str(dot_number)
    if not normalized_dot:
        return {
            "attempt": {
                "provider": "fmcsa",
                "action": "company_enrich_fmcsa",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    base_url = f"{_BASE_URL}/carriers/{quote(normalized_dot, safe='')}?webKey={api_key}"
    basics_url = f"{_BASE_URL}/carriers/{quote(normalized_dot, safe='')}/basics?webKey={api_key}"
    authority_url = f"{_BASE_URL}/carriers/{quote(normalized_dot, safe='')}/authority?webKey={api_key}"

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        base_status, base_body, base_error = await _get_json(client=client, url=base_url)
        if base_error:
            return {
                "attempt": {
                    "provider": "fmcsa",
                    "action": "company_enrich_fmcsa",
                    "status": "failed",
                    "provider_status": "base_http_error",
                    "duration_ms": now_ms() - start_ms,
                    "raw_response": {"base": base_body},
                },
                "mapped": None,
            }
        if base_status >= 400:
            return {
                "attempt": {
                    "provider": "fmcsa",
                    "action": "company_enrich_fmcsa",
                    "status": "failed",
                    "http_status": base_status,
                    "duration_ms": now_ms() - start_ms,
                    "raw_response": {"base": base_body},
                },
                "mapped": None,
            }

        basics_status, basics_body, basics_error = await _get_json(client=client, url=basics_url)
        authority_status, authority_body, authority_error = await _get_json(client=client, url=authority_url)

    base = _extract_primary_record(base_body)
    bus_vehicles = _as_int(base.get("busVehicle"))
    van_vehicles = _as_int(base.get("vanVehicle"))
    passenger_vehicles = _as_int(base.get("passengerVehicle"))
    total_power_units = _as_int(base.get("powerUnit"))
    if total_power_units is None:
        known_fleet_counts = [count for count in [bus_vehicles, van_vehicles, passenger_vehicles] if count is not None]
        if known_fleet_counts:
            total_power_units = sum(known_fleet_counts)

    mapped: dict[str, Any] = {
        "dot_number": _as_str(base.get("dotNumber")) or normalized_dot,
        "legal_name": _as_str(base.get("legalName")),
        "dba_name": _as_str(base.get("dbaName")),
        "allow_to_operate": _as_bool(base.get("allowToOperate")),
        "out_of_service": _as_bool(base.get("outOfService")),
        "out_of_service_date": _as_str(base.get("outOfServiceDate")),
        "total_drivers": _as_int(base.get("driverTotal")),
        "total_power_units": total_power_units,
        "bus_vehicles": bus_vehicles,
        "van_vehicles": van_vehicles,
        "passenger_vehicles": passenger_vehicles,
        "address_street": _as_str(base.get("phyStreet")),
        "address_city": _as_str(base.get("phyCity")),
        "address_state": _as_str(base.get("phyState")),
        "address_zip": _as_str(base.get("phyZipcode")),
        "phone": _as_str(base.get("telephone")),
        "complaint_count": _as_int(base.get("complaintCount")),
    }

    basics_included = False
    authority_included = False

    if not basics_error and basics_status < 400:
        scores = _map_basics_scores(basics_body)
        if scores:
            mapped["basic_scores"] = scores
            basics_included = True

    if not authority_error and authority_status < 400:
        authority_value, authority_grant_date = _map_authority(authority_body)
        if authority_value is not None:
            mapped["authority_status"] = authority_value
            authority_included = True
        if authority_grant_date is not None:
            mapped["authority_grant_date"] = authority_grant_date
            authority_included = True

    provider_status = "full"
    if not basics_included or not authority_included:
        provider_status = "partial"

    return {
        "attempt": {
            "provider": "fmcsa",
            "action": "company_enrich_fmcsa",
            "status": "found",
            "http_status": base_status,
            "duration_ms": now_ms() - start_ms,
            "provider_status": provider_status,
            "raw_response": {
                "base": base_body,
                "basics": basics_body,
                "authority": authority_body,
                "basics_error": basics_error,
                "authority_error": authority_error,
                "basics_http_status": basics_status,
                "authority_http_status": authority_status,
            },
        },
        "mapped": mapped,
    }
