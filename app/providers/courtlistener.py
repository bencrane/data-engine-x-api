from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://www.courtlistener.com/api/rest/v4"


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
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return int(cleaned)
        except ValueError:
            return None
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _as_str_list(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    parsed: list[str] = []
    for item in value:
        parsed_item = _as_str(item)
        if parsed_item:
            parsed.append(parsed_item)
    return parsed or None


def _to_public_url(value: Any) -> str | None:
    url = _as_str(value)
    if not url:
        return None
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("/"):
        return f"https://www.courtlistener.com{url}"
    return f"https://www.courtlistener.com/{url}"


async def _get_json(
    *,
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any], str | None]:
    try:
        response = await client.get(url, headers=headers, params=params)
    except httpx.HTTPError as exc:
        return 0, {"error": str(exc)}, f"{exc.__class__.__name__}: {exc}"
    body = parse_json_or_raw(response.text, response.json)
    return response.status_code, body, None


def _map_search_result(raw: dict[str, Any]) -> dict[str, Any]:
    meta = _as_dict(raw.get("meta"))
    score = _as_dict(meta.get("score"))
    return {
        "docket_id": _as_int(raw.get("docket_id")),
        "case_name": _as_str(raw.get("caseName")),
        "court": _as_str(raw.get("court")),
        "court_citation": _as_str(raw.get("court_citation_string")),
        "docket_number": _as_str(raw.get("docketNumber")),
        "date_filed": _as_str(raw.get("dateFiled")),
        "date_terminated": _as_str(raw.get("dateTerminated")),
        "judge": _as_str(raw.get("judge")) or _as_str(raw.get("assignedTo")),
        "party_names": _as_str_list(raw.get("party_name")),
        "attorneys": _as_str_list(raw.get("attorney")),
        "relevance_score": _as_float(score.get("bm25")),
        "url": _to_public_url(raw.get("docket_absolute_url")),
    }


def _map_docket_result(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "docket_id": _as_int(raw.get("id")),
        "case_name": _as_str(raw.get("case_name")),
        "case_name_short": _as_str(raw.get("case_name_short")),
        "court_id": _as_str(raw.get("court_id")),
        "court_citation": _as_str(raw.get("court_citation_string")),
        "docket_number": _as_str(raw.get("docket_number")),
        "date_filed": _as_str(raw.get("date_filed")),
        "date_terminated": _as_str(raw.get("date_terminated")),
        "date_last_filing": _as_str(raw.get("date_last_filing")),
        "judge": _as_str(raw.get("assigned_to_str")),
        "pacer_case_id": _as_str(raw.get("pacer_case_id")),
        "url": _to_public_url(raw.get("absolute_url")),
    }


def _extract_party_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for item in value:
        if isinstance(item, str):
            parsed = _as_str(item)
            if parsed:
                names.append(parsed)
            continue
        if isinstance(item, dict):
            parsed = _as_str(item.get("name")) or _as_str(item.get("party_name"))
            if parsed:
                names.append(parsed)
    return names or None


async def search_court_filings(
    *,
    api_key: str | None,
    company_name: str | None,
    court_type: str | None,
    date_filed_gte: str | None,
    date_filed_lte: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_court_filings",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    normalized_company_name = _as_str(company_name)
    if not normalized_company_name:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_court_filings",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    params: dict[str, Any] = {
        "type": "r",
        "q": f'caseName:"{normalized_company_name}"',
    }
    normalized_court_type = _as_str(court_type)
    normalized_gte = _as_str(date_filed_gte)
    normalized_lte = _as_str(date_filed_lte)
    if normalized_court_type:
        params["court"] = normalized_court_type
    if normalized_gte:
        params["filed_after"] = normalized_gte
    if normalized_lte:
        params["filed_before"] = normalized_lte

    headers = {"Authorization": f"Token {api_key}"}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/search/",
            headers=headers,
            params=params,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_court_filings",
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
                "provider": "courtlistener",
                "action": "search_court_filings",
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": {"results": [], "result_count": 0},
        }

    raw_results = [item for item in _as_list(_as_dict(body).get("results")) if isinstance(item, dict)]
    mapped_results = [_map_search_result(item) for item in raw_results]
    result_count = len(mapped_results)
    return {
        "attempt": {
            "provider": "courtlistener",
            "action": "search_court_filings",
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


async def search_bankruptcy_filings(
    *,
    api_key: str | None,
    date_filed_gte: str | None,
    date_filed_lte: str | None,
    courts: list[str] | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_bankruptcy_filings",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    normalized_gte = _as_str(date_filed_gte)
    normalized_lte = _as_str(date_filed_lte)
    if not normalized_gte and not normalized_lte:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "search_bankruptcy_filings",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": {"results": [], "result_count": 0},
        }

    normalized_courts = [court for court in (_as_str_list(courts) or []) if court]
    params: dict[str, Any] = {}
    if normalized_courts:
        params["court"] = normalized_courts
    else:
        params["court__jurisdiction"] = "FB"
    if normalized_gte:
        params["date_filed__gte"] = normalized_gte
    if normalized_lte:
        params["date_filed__lte"] = normalized_lte

    headers = {"Authorization": f"Token {api_key}"}
    start_ms = now_ms()
    raw_pages: list[dict[str, Any]] = []
    mapped_results: list[dict[str, Any]] = []
    next_url: str | None = f"{_BASE_URL}/dockets/"
    first_page = True

    async with httpx.AsyncClient(timeout=30.0) as client:
        while next_url:
            status_code, body, request_error = await _get_json(
                client=client,
                url=next_url,
                headers=headers,
                params=params if first_page else None,
            )
            first_page = False
            if request_error:
                return {
                    "attempt": {
                        "provider": "courtlistener",
                        "action": "search_bankruptcy_filings",
                        "status": "failed",
                        "provider_status": "http_error",
                        "duration_ms": now_ms() - start_ms,
                        "raw_response": {
                            "pages": raw_pages,
                            "error": body,
                        },
                    },
                    "mapped": {"results": [], "result_count": 0},
                }
            if status_code >= 400:
                return {
                    "attempt": {
                        "provider": "courtlistener",
                        "action": "search_bankruptcy_filings",
                        "status": "failed",
                        "http_status": status_code,
                        "duration_ms": now_ms() - start_ms,
                        "raw_response": {
                            "pages": raw_pages,
                            "error": body,
                        },
                    },
                    "mapped": {"results": [], "result_count": 0},
                }

            raw_body = _as_dict(body)
            raw_pages.append(raw_body)
            page_results = [item for item in _as_list(raw_body.get("results")) if isinstance(item, dict)]
            mapped_results.extend(_map_docket_result(item) for item in page_results)
            next_url = _as_str(raw_body.get("next"))

    result_count = len(mapped_results)
    return {
        "attempt": {
            "provider": "courtlistener",
            "action": "search_bankruptcy_filings",
            "status": "found" if result_count else "not_found",
            "http_status": 200,
            "duration_ms": now_ms() - start_ms,
            "raw_response": {
                "pages": raw_pages,
                "page_count": len(raw_pages),
            },
        },
        "mapped": {
            "results": mapped_results,
            "result_count": result_count,
        },
    }


async def get_docket_detail(
    *,
    api_key: str | None,
    docket_id: int | str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "get_docket_detail",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_docket_id = _as_int(docket_id)
    if normalized_docket_id is None:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "get_docket_detail",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    headers = {"Authorization": f"Token {api_key}"}
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        status_code, body, request_error = await _get_json(
            client=client,
            url=f"{_BASE_URL}/dockets/{normalized_docket_id}/",
            headers=headers,
        )

    if request_error:
        return {
            "attempt": {
                "provider": "courtlistener",
                "action": "get_docket_detail",
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
                "provider": "courtlistener",
                "action": "get_docket_detail",
                "status": "failed",
                "http_status": status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mapped = _map_docket_result(_as_dict(body))
    mapped["parties"] = _extract_party_names(_as_dict(body).get("parties"))
    return {
        "attempt": {
            "provider": "courtlistener",
            "action": "get_docket_detail",
            "status": "found",
            "http_status": status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "docket_id": mapped.get("docket_id"),
            "case_name": mapped.get("case_name"),
            "court_id": mapped.get("court_id"),
            "docket_number": mapped.get("docket_number"),
            "date_filed": mapped.get("date_filed"),
            "date_terminated": mapped.get("date_terminated"),
            "parties": mapped.get("parties"),
            "judge": mapped.get("judge"),
            "url": mapped.get("url"),
        },
    }
