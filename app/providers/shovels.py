from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://api.shovels.ai"


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


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
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


def _normalize_param(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned if cleaned else None
    if isinstance(value, list):
        cleaned: list[Any] = []
        for item in value:
            normalized = _normalize_param(item)
            if normalized is None:
                continue
            cleaned.append(normalized)
        return cleaned or None
    if value is None:
        return None
    return value


def _query_from_filters(filters: dict[str, Any], *, allowed_keys: set[str]) -> list[tuple[str, Any]]:
    params: list[tuple[str, Any]] = []
    for key in allowed_keys:
        normalized = _normalize_param(filters.get(key))
        if normalized is None:
            continue
        if isinstance(normalized, list):
            for item in normalized:
                params.append((key, item))
            continue
        params.append((key, normalized))
    return params


def _http_headers(api_key: str) -> dict[str, str]:
    return {
        "X-API-Key": api_key,
        "Accept": "application/json",
    }


def _map_address(address: Any) -> str | None:
    address_dict = _as_dict(address)
    parts = [
        _as_str(address_dict.get("street_no")),
        _as_str(address_dict.get("street")),
        _as_str(address_dict.get("city")),
        _as_str(address_dict.get("state")),
        _as_str(address_dict.get("zip_code")),
    ]
    compact = [part for part in parts if part]
    if not compact:
        return None
    return ", ".join(compact)


def _map_permit_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "permit_id": _as_str(raw.get("id")),
        "number": _as_str(raw.get("number")),
        "description": _as_str(raw.get("description")),
        "status": _as_str(raw.get("status")),
        "file_date": _as_str(raw.get("file_date")),
        "issue_date": _as_str(raw.get("issue_date")),
        "final_date": _as_str(raw.get("final_date")),
        "job_value": _as_int(raw.get("job_value")),
        "fees": _as_int(raw.get("fees")),
        "contractor_id": _as_str(raw.get("contractor_id")),
        "contractor_name": _as_str(raw.get("contractor_name")),
        "address": _map_address(raw.get("address")),
        "property_type": _as_str(raw.get("property_type")),
    }


def _map_contractor_item(raw: dict[str, Any]) -> dict[str, Any]:
    address = _as_dict(raw.get("address"))
    return {
        "id": _as_str(raw.get("id")),
        "name": _as_str(raw.get("name")),
        "business_name": _as_str(raw.get("business_name")),
        "business_type": _as_str(raw.get("business_type")),
        "classification": _as_str(raw.get("classification")),
        "classification_derived": _as_str(raw.get("classification_derived")),
        "primary_email": _as_str(raw.get("primary_email")),
        "primary_phone": _as_str(raw.get("primary_phone")),
        "email": _as_str(raw.get("email")),
        "phone": _as_str(raw.get("phone")),
        "website": _as_str(raw.get("website")),
        "linkedin_url": _as_str(raw.get("linkedin_url")),
        "street_no": _as_str(address.get("street_no")),
        "street": _as_str(address.get("street")),
        "city": _as_str(address.get("city")),
        "state": _as_str(address.get("state")),
        "zipcode": _as_str(address.get("zip_code")),
        "county": _as_str(raw.get("county")),
        "license": _as_str(raw.get("license")),
        "license_issue_date": _as_str(raw.get("license_issue_date")),
        "license_exp_date": _as_str(raw.get("license_exp_date")),
        "employee_count": _as_str(raw.get("employee_count")),
        "revenue": _as_str(raw.get("revenue")),
        "rating": _as_float(raw.get("rating")),
        "review_count": _as_int(raw.get("review_count")),
        "permit_count": _as_int(raw.get("permit_count")),
        "total_job_value": _as_int(raw.get("total_job_value")),
        "avg_job_value": _as_int(raw.get("avg_job_value")),
        "avg_inspection_pass_rate": _as_int(raw.get("avg_inspection_pass_rate")),
        "naics": _as_str(raw.get("naics")),
        "sic": _as_str(raw.get("sic")),
        "primary_industry": _as_str(raw.get("primary_industry")),
    }


def _map_employee_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": _as_str(raw.get("id")),
        "name": _as_str(raw.get("name")),
        "email": _as_str(raw.get("email")),
        "business_email": _as_str(raw.get("business_email")),
        "phone": _as_str(raw.get("phone")),
        "linkedin_url": _as_str(raw.get("linkedin_url")),
        "city": _as_str(raw.get("city")),
        "state": _as_str(raw.get("state")),
        "zip_code": _as_str(raw.get("zip_code")),
    }


def _map_resident_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _as_str(raw.get("name")),
        "personal_emails": _as_str(raw.get("personal_emails")),
        "phone": _as_str(raw.get("phone")),
        "linkedin_url": _as_str(raw.get("linkedin_url")),
        "net_worth": _as_str(raw.get("net_worth")),
        "income_range": _as_str(raw.get("income_range")),
        "is_homeowner": raw.get("is_homeowner") if isinstance(raw.get("is_homeowner"), bool) else None,
        "city": _as_str(raw.get("city")),
        "state": _as_str(raw.get("state")),
        "zip_code": _as_str(raw.get("zip_code")),
    }


def _map_geo_item(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "geo_id": _as_str(raw.get("geo_id")),
        "name": _as_str(raw.get("name")),
        "state": _as_str(raw.get("state")),
    }


def _map_address_search_item(raw: dict[str, Any]) -> dict[str, Any]:
    address = _as_str(raw.get("name")) or _map_address(raw)
    return {
        "geo_id": _as_str(raw.get("geo_id")),
        "address": address,
        "city": _as_str(raw.get("city")),
        "state": _as_str(raw.get("state")),
        "zip_code": _as_str(raw.get("zip_code")),
        "property_type": _as_str(raw.get("property_type")),
    }


def _map_monthly_data_points(*, items: list[dict[str, Any]], metric: str | None) -> list[dict[str, Any]]:
    data_points: list[dict[str, Any]] = []
    for item in items:
        value: Any = item.get("permit_count")
        if metric and metric in item:
            value = item.get(metric)
        data_points.append(
            {
                "month": _as_str(item.get("date")),
                "value": value if isinstance(value, (int, float)) and not isinstance(value, bool) else None,
            }
        )
    return data_points


def _default_geo_search_result() -> dict[str, Any]:
    return {"results": [], "result_count": 0}


def _default_monthly_metrics_result(geo_id: str | None = None, metric: str | None = None) -> dict[str, Any]:
    return {"geo_id": geo_id or "", "metric": metric, "data_points": []}


def _default_current_metrics_result(geo_id: str | None = None) -> dict[str, Any]:
    return {"geo_id": geo_id or "", "metrics": {}}


def _default_geo_detail_result(geo_id: str | None = None) -> dict[str, Any]:
    return {"geo_id": geo_id or "", "name": None, "state": None, "details": {}}


def _default_address_search_result() -> dict[str, Any]:
    return {"results": [], "result_count": 0}


def _build_geo_search_query(*, state: str | None, name_contains: str | None) -> str | None:
    state_text = _as_str(state)
    name_text = _as_str(name_contains)
    if not state_text and not name_text:
        return None
    if state_text and name_text:
        return f"{name_text} {state_text}"
    return name_text or state_text


def _build_zip_search_query(*, state: str | None, zipcode_contains: str | None) -> str | None:
    state_text = _as_str(state)
    zip_text = _as_str(zipcode_contains)
    if not state_text and not zip_text:
        return None
    if state_text and zip_text:
        return f"{zip_text} {state_text}"
    return zip_text or state_text


def _size_param(value: Any) -> int:
    parsed = _as_int(value)
    if parsed is None:
        return 50
    return max(1, min(100, parsed))


async def _get_json(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: list[tuple[str, Any]] | None = None,
) -> tuple[int, dict[str, Any], str | None]:
    try:
        response = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        return 0, {"error": str(exc)}, f"{exc.__class__.__name__}: {exc}"
    body = parse_json_or_raw(response.text, response.json)
    return response.status_code, body, None


def _not_found_status(items: list[Any]) -> str:
    return "found" if items else "not_found"


async def search_permits(
    *,
    api_key: str | None,
    filters: dict[str, Any],
) -> ProviderAdapterResult:
    action = "permit_search_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    required = ["permit_from", "permit_to", "geo_id"]
    missing_required = [key for key in required if not _as_str(filters.get(key))]
    if missing_required:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    allowed_keys = {
        "permit_from",
        "permit_to",
        "geo_id",
        "permit_tags",
        "permit_has_contractor",
        "permit_q",
        "permit_status",
        "permit_min_job_value",
        "property_type",
        "contractor_classification_derived",
        "size",
        "cursor",
    }
    params = _query_from_filters(filters, allowed_keys=allowed_keys)

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/permits/search",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    body_dict = _as_dict(body)
    items = [_map_permit_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    next_cursor = _as_str(body_dict.get("next_cursor"))
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": _not_found_status(items),
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": items,
            "result_count": len(items),
            "next_cursor": next_cursor,
        },
    }


async def get_permits_by_id(
    *,
    api_key: str | None,
    permit_ids: list[str] | None,
) -> ProviderAdapterResult:
    action = "permit_get_by_id_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    normalized_ids = [_as_str(permit_id) for permit_id in (permit_ids or [])]
    compact_ids = [permit_id for permit_id in normalized_ids if permit_id]
    if not compact_ids:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    params = [("id", permit_id) for permit_id in compact_ids]

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/permits",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    body_dict = _as_dict(body)
    items = [_map_permit_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    next_cursor = _as_str(body_dict.get("next_cursor"))
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": _not_found_status(items),
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": items,
            "result_count": len(items),
            "next_cursor": next_cursor,
        },
    }


async def get_contractor(
    *,
    api_key: str | None,
    contractor_id: str | None,
) -> ProviderAdapterResult:
    action = "contractor_enrich_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_contractor_id = _as_str(contractor_id)
    if not normalized_contractor_id:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    params = [("id", normalized_contractor_id)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/contractors",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    body_dict = _as_dict(body)
    items = _as_list(body_dict.get("items"))
    first_item = _as_dict(items[0]) if items else {}
    mapped = _map_contractor_item(first_item) if first_item else None
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": "found" if mapped else "not_found",
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped,
    }


async def search_contractors(
    *,
    api_key: str | None,
    filters: dict[str, Any],
) -> ProviderAdapterResult:
    action = "contractor_search_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    required = ["permit_from", "permit_to", "geo_id"]
    missing_required = [key for key in required if not _as_str(filters.get(key))]
    if missing_required:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    allowed_keys = {
        "permit_from",
        "permit_to",
        "geo_id",
        "permit_tags",
        "contractor_classification_derived",
        "contractor_name",
        "contractor_website",
        "contractor_min_total_job_value",
        "size",
        "cursor",
    }
    params = _query_from_filters(filters, allowed_keys=allowed_keys)

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/contractors/search",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0, "next_cursor": None},
        }

    body_dict = _as_dict(body)
    items = [_map_contractor_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    next_cursor = _as_str(body_dict.get("next_cursor"))
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": _not_found_status(items),
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "results": items,
            "result_count": len(items),
            "next_cursor": next_cursor,
        },
    }


async def get_contractor_employees(
    *,
    api_key: str | None,
    contractor_id: str | None,
    size: int | None = None,
    cursor: str | None = None,
) -> ProviderAdapterResult:
    action = "contractor_search_employees_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"employees": [], "employee_count": 0},
        }

    normalized_contractor_id = _as_str(contractor_id)
    if not normalized_contractor_id:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"employees": [], "employee_count": 0},
        }

    params: list[tuple[str, Any]] = []
    parsed_size = _as_int(size)
    if parsed_size is not None:
        params.append(("size", max(1, min(100, parsed_size))))
    if _as_str(cursor):
        params.append(("cursor", _as_str(cursor)))

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/contractors/{normalized_contractor_id}/employees",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"employees": [], "employee_count": 0},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"employees": [], "employee_count": 0},
        }

    body_dict = _as_dict(body)
    employees = [_map_employee_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": _not_found_status(employees),
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "employees": employees,
            "employee_count": len(employees),
        },
    }


async def get_address_residents(
    *,
    api_key: str | None,
    geo_id: str | None,
    size: int | None = None,
    cursor: str | None = None,
) -> ProviderAdapterResult:
    action = "address_search_residents_shovels"
    if not api_key:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"residents": [], "resident_count": 0},
        }

    normalized_geo_id = _as_str(geo_id)
    if not normalized_geo_id:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"residents": [], "resident_count": 0},
        }

    params: list[tuple[str, Any]] = []
    parsed_size = _as_int(size)
    if parsed_size is not None:
        params.append(("size", max(1, min(100, parsed_size))))
    if _as_str(cursor):
        params.append(("cursor", _as_str(cursor)))

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/v2/addresses/{normalized_geo_id}/residents",
            headers=_http_headers(api_key),
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"residents": [], "resident_count": 0},
        }

    if status_code >= 400:
        return {
            "attempt": {
                "provider": "shovels",
                "action": action,
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"residents": [], "resident_count": 0},
        }

    body_dict = _as_dict(body)
    residents = [_map_resident_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    return {
        "attempt": {
            "provider": "shovels",
            "action": action,
            "status": _not_found_status(residents),
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "residents": residents,
            "resident_count": len(residents),
        },
    }


async def search_cities(
    *,
    api_key: str | None,
    state: str | None,
    name_contains: str | None = None,
    size: int | None = None,
) -> ProviderAdapterResult:
    action = "market_search_cities_shovels"
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_search_result()}

    query = _build_geo_search_query(state=state, name_contains=name_contains)
    if not query or not _as_str(state):
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_search_result()}

    params: list[tuple[str, Any]] = [("q", query), ("size", _size_param(size))]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/cities/search", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}

    body_dict = _as_dict(body)
    normalized_state = _as_str(state)
    items = [_map_geo_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    if normalized_state:
        items = [item for item in items if _as_str(item.get("state")) == normalized_state]
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"results": items, "result_count": len(items)}}


async def search_counties(
    *,
    api_key: str | None,
    state: str | None,
    name_contains: str | None = None,
    size: int | None = None,
) -> ProviderAdapterResult:
    action = "market_search_counties_shovels"
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_search_result()}

    query = _build_geo_search_query(state=state, name_contains=name_contains)
    if not query or not _as_str(state):
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_search_result()}

    params: list[tuple[str, Any]] = [("q", query), ("size", _size_param(size))]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/counties/search", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}

    body_dict = _as_dict(body)
    normalized_state = _as_str(state)
    items = [_map_geo_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    if normalized_state:
        items = [item for item in items if _as_str(item.get("state")) == normalized_state]
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"results": items, "result_count": len(items)}}


async def search_zipcodes(
    *,
    api_key: str | None,
    state: str | None,
    zipcode_contains: str | None = None,
    size: int | None = None,
) -> ProviderAdapterResult:
    action = "market_search_zipcodes_shovels"
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_search_result()}

    query = _build_zip_search_query(state=state, zipcode_contains=zipcode_contains)
    if not query or not _as_str(state):
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_search_result()}

    params: list[tuple[str, Any]] = [("q", query), ("size", _size_param(size))]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/zipcodes/search", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}

    body_dict = _as_dict(body)
    normalized_state = _as_str(state)
    items = [_map_geo_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    if normalized_state:
        items = [item for item in items if _as_str(item.get("state")) == normalized_state]
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"results": items, "result_count": len(items)}}


async def search_jurisdictions(
    *,
    api_key: str | None,
    state: str | None,
    name_contains: str | None = None,
    size: int | None = None,
) -> ProviderAdapterResult:
    action = "market_search_jurisdictions_shovels"
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_search_result()}

    query = _build_geo_search_query(state=state, name_contains=name_contains)
    if not query or not _as_str(state):
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_search_result()}

    params: list[tuple[str, Any]] = [("q", query), ("size", _size_param(size))]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/jurisdictions/search", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_search_result()}

    body_dict = _as_dict(body)
    normalized_state = _as_str(state)
    items = [_map_geo_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    if normalized_state:
        items = [item for item in items if _as_str(item.get("state")) == normalized_state]
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"results": items, "result_count": len(items)}}


async def get_city_metrics_monthly(
    *,
    api_key: str | None,
    geo_id: str | None,
    metric: str | None,
    start_date: str | None,
    end_date: str | None,
) -> ProviderAdapterResult:
    action = "market_city_metrics_monthly_shovels"
    normalized_geo_id = _as_str(geo_id)
    normalized_metric = _as_str(metric) or "all"
    metric_from = _as_str(start_date)
    metric_to = _as_str(end_date)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if not normalized_geo_id or not metric_from or not metric_to:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    params: list[tuple[str, Any]] = [("metric_from", metric_from), ("metric_to", metric_to), ("tag", normalized_metric), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/cities/{normalized_geo_id}/metrics/monthly", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    data_points = _map_monthly_data_points(items=items, metric=normalized_metric)
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metric": normalized_metric, "data_points": data_points}}


async def get_city_metrics_current(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_city_metrics_current_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("tag", "all"), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/cities/{normalized_geo_id}/metrics/current", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    metrics = items[0] if items else {}
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metrics": metrics}}


async def get_county_metrics_monthly(
    *,
    api_key: str | None,
    geo_id: str | None,
    metric: str | None,
    start_date: str | None,
    end_date: str | None,
) -> ProviderAdapterResult:
    action = "market_county_metrics_monthly_shovels"
    normalized_geo_id = _as_str(geo_id)
    normalized_metric = _as_str(metric) or "all"
    metric_from = _as_str(start_date)
    metric_to = _as_str(end_date)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if not normalized_geo_id or not metric_from or not metric_to:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    params: list[tuple[str, Any]] = [("metric_from", metric_from), ("metric_to", metric_to), ("tag", normalized_metric), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/counties/{normalized_geo_id}/metrics/monthly", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    data_points = _map_monthly_data_points(items=items, metric=normalized_metric)
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metric": normalized_metric, "data_points": data_points}}


async def get_county_metrics_current(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_county_metrics_current_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("tag", "all"), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/counties/{normalized_geo_id}/metrics/current", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    metrics = items[0] if items else {}
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metrics": metrics}}


async def get_jurisdiction_metrics_monthly(
    *,
    api_key: str | None,
    geo_id: str | None,
    metric: str | None,
    start_date: str | None,
    end_date: str | None,
) -> ProviderAdapterResult:
    action = "market_jurisdiction_metrics_monthly_shovels"
    normalized_geo_id = _as_str(geo_id)
    normalized_metric = _as_str(metric) or "all"
    metric_from = _as_str(start_date)
    metric_to = _as_str(end_date)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if not normalized_geo_id or not metric_from or not metric_to:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    params: list[tuple[str, Any]] = [("metric_from", metric_from), ("metric_to", metric_to), ("tag", normalized_metric), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/jurisdictions/{normalized_geo_id}/metrics/monthly", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    data_points = _map_monthly_data_points(items=items, metric=normalized_metric)
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metric": normalized_metric, "data_points": data_points}}


async def get_jurisdiction_metrics_current(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_jurisdiction_metrics_current_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("tag", "all"), ("property_type", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/jurisdictions/{normalized_geo_id}/metrics/current", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    metrics = items[0] if items else {}
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metrics": metrics}}


async def get_address_metrics_monthly(
    *,
    api_key: str | None,
    geo_id: str | None,
    metric: str | None,
    start_date: str | None,
    end_date: str | None,
) -> ProviderAdapterResult:
    action = "market_address_metrics_monthly_shovels"
    normalized_geo_id = _as_str(geo_id)
    normalized_metric = _as_str(metric) or "all"
    metric_from = _as_str(start_date)
    metric_to = _as_str(end_date)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if not normalized_geo_id or not metric_from or not metric_to:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    params: list[tuple[str, Any]] = [("metric_from", metric_from), ("metric_to", metric_to), ("tag", normalized_metric), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/addresses/{normalized_geo_id}/metrics/monthly", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_monthly_metrics_result(normalized_geo_id, normalized_metric)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    data_points = _map_monthly_data_points(items=items, metric=normalized_metric)
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metric": normalized_metric, "data_points": data_points}}


async def get_address_metrics_current(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_address_metrics_current_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("tag", "all"), ("size", 100)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/addresses/{normalized_geo_id}/metrics/current", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_current_metrics_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    items = [_as_dict(item) for item in _as_list(body_dict.get("items"))]
    metrics = items[0] if items else {}
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": normalized_geo_id, "metrics": metrics}}


async def get_city_details(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_city_detail_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("geo_id", normalized_geo_id)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/cities", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    details = dict(body_dict)
    return {"attempt": {"provider": "shovels", "action": action, "status": "found" if details else "not_found", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": _as_str(body_dict.get("geo_id")) or normalized_geo_id, "name": _as_str(body_dict.get("name")), "state": _as_str(body_dict.get("state")), "details": details}}


async def get_county_details(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_county_detail_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("geo_id", normalized_geo_id)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/counties", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    details = dict(body_dict)
    return {"attempt": {"provider": "shovels", "action": action, "status": "found" if details else "not_found", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": _as_str(body_dict.get("geo_id")) or normalized_geo_id, "name": _as_str(body_dict.get("name")), "state": _as_str(body_dict.get("state")), "details": details}}


async def get_jurisdiction_details(
    *,
    api_key: str | None,
    geo_id: str | None,
) -> ProviderAdapterResult:
    action = "market_jurisdiction_detail_shovels"
    normalized_geo_id = _as_str(geo_id)
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if not normalized_geo_id:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    params: list[tuple[str, Any]] = [("geo_id", normalized_geo_id)]
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/jurisdictions", headers=_http_headers(api_key), params=params)
    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_geo_detail_result(normalized_geo_id)}

    body_dict = _as_dict(body)
    details = dict(body_dict)
    return {"attempt": {"provider": "shovels", "action": action, "status": "found" if details else "not_found", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"geo_id": _as_str(body_dict.get("geo_id")) or normalized_geo_id, "name": _as_str(body_dict.get("name")), "state": _as_str(body_dict.get("state")), "details": details}}


async def search_addresses(
    *,
    api_key: str | None,
    filters: dict[str, Any],
) -> ProviderAdapterResult:
    action = "address_search_shovels"
    if not api_key:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_provider_api_key"}, "mapped": _default_address_search_result()}

    query = _as_str(filters.get("q"))
    if not query:
        return {"attempt": {"provider": "shovels", "action": action, "status": "skipped", "skip_reason": "missing_required_inputs"}, "mapped": _default_address_search_result()}

    allowed_keys = {
        "q",
        "street_no",
        "street",
        "city",
        "county",
        "state",
        "zip_code",
        "zip_code_ext",
        "jurisdiction",
        "property_type",
        "cursor",
        "size",
    }
    params = _query_from_filters(filters, allowed_keys=allowed_keys)
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(client=client, url=f"{_BASE_URL}/v2/addresses/search", headers=_http_headers(api_key), params=params)

    if request_error:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "provider_status": "http_error", "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_address_search_result()}
    if status_code >= 400:
        return {"attempt": {"provider": "shovels", "action": action, "status": "failed", "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": _default_address_search_result()}

    body_dict = _as_dict(body)
    items = [_map_address_search_item(_as_dict(item)) for item in _as_list(body_dict.get("items"))]
    return {"attempt": {"provider": "shovels", "action": action, "status": _not_found_status(items), "http_status": status_code, "duration_ms": now_ms() - start_ms, "raw_response": body}, "mapped": {"results": items, "result_count": len(items)}}
