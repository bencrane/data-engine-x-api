from __future__ import annotations

import re
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://data.transportation.gov/api/v3/views"
_FIELD_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _as_non_empty_str(value: Any) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(int(value))
    return None


def _provider_status_for_http_status(status_code: int) -> str:
    if status_code == 400:
        return "bad_request"
    if status_code == 401:
        return "unauthorized"
    if status_code == 403:
        return "forbidden"
    if status_code == 404:
        return "not_found"
    if status_code == 429:
        return "rate_limited"
    if status_code >= 500:
        return "server_error"
    return "http_error"


def quote_identifier(field_name: str) -> str:
    if not _FIELD_NAME_RE.fullmatch(field_name):
        raise ValueError(f"Invalid Socrata field name: {field_name}")
    return f"`{field_name}`"


def soql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def soql_numeric_literal(value: int | str) -> str:
    if isinstance(value, bool):
        raise ValueError("Boolean values are not valid numeric SoQL literals")
    if isinstance(value, int):
        return str(value)
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Numeric SoQL literal cannot be empty")
    parsed = int(cleaned)
    return str(parsed)


def build_exact_match_query(
    *,
    field_name: str,
    value: str | int,
    numeric: bool = False,
) -> str:
    literal = soql_numeric_literal(value) if numeric else soql_string_literal(str(value))
    return f"SELECT * WHERE {quote_identifier(field_name)} = {literal}"


def build_or_query(where_clauses: list[str]) -> str:
    cleaned_clauses = [clause.strip() for clause in where_clauses if clause and clause.strip()]
    if not cleaned_clauses:
        raise ValueError("At least one WHERE clause is required")
    if len(cleaned_clauses) == 1:
        return f"SELECT * WHERE {cleaned_clauses[0]}"
    return "SELECT * WHERE " + " OR ".join(f"({clause})" for clause in cleaned_clauses)


def normalize_dot_number(value: Any) -> str | None:
    raw = _as_non_empty_str(value)
    if raw is None:
        return None
    digits = "".join(character for character in raw if character.isdigit())
    if not digits:
        return None
    return str(int(digits))


def normalize_mc_number(value: Any) -> str | None:
    raw = _as_non_empty_str(value)
    if raw is None:
        return None
    normalized = raw.upper().strip()
    if normalized.startswith("MC"):
        normalized = normalized[2:]
    digits = "".join(character for character in normalized if character.isdigit())
    if not digits or len(digits) > 6:
        return None
    return str(int(digits))


def build_mc_docket_value(mc_number: str) -> str:
    digits = normalize_mc_number(mc_number)
    if digits is None:
        raise ValueError("Invalid MC number")
    return f"MC{int(digits):06d}"


def parse_socrata_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        value = payload.get("value")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    return []


async def query_dataset(
    *,
    dataset_id: str,
    query: str,
    api_key_id: str | None,
    api_key_secret: str | None,
    timeout_seconds: float = 30.0,
) -> ProviderAdapterResult:
    if not api_key_id or not api_key_secret:
        return {
            "attempt": {
                "provider": "socrata",
                "action": "query_dataset",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": {"dataset_id": dataset_id, "rows": []},
        }

    start_ms = now_ms()
    url = f"{_BASE_URL}/{dataset_id}/query.json"
    request_payload = {"query": query}

    try:
        async with httpx.AsyncClient(
            timeout=timeout_seconds,
            auth=httpx.BasicAuth(api_key_id, api_key_secret),
        ) as client:
            response = await client.post(url, json=request_payload)
    except httpx.HTTPError as exc:
        return {
            "attempt": {
                "provider": "socrata",
                "action": "query_dataset",
                "status": "failed",
                "provider_status": "http_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": {
                    "request": {"dataset_id": dataset_id, "query": query},
                    "error": f"{exc.__class__.__name__}: {exc}",
                },
            },
            "mapped": {"dataset_id": dataset_id, "rows": []},
        }

    parsed_response = parse_json_or_raw(response.text, response.json)
    raw_response = {
        "request": {"dataset_id": dataset_id, "query": query},
        "response": parsed_response,
    }

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "socrata",
                "action": "query_dataset",
                "status": "failed",
                "http_status": response.status_code,
                "provider_status": _provider_status_for_http_status(response.status_code),
                "duration_ms": now_ms() - start_ms,
                "raw_response": raw_response,
            },
            "mapped": {"dataset_id": dataset_id, "rows": []},
        }

    if isinstance(parsed_response, dict) and parsed_response.get("error") is True:
        return {
            "attempt": {
                "provider": "socrata",
                "action": "query_dataset",
                "status": "failed",
                "http_status": response.status_code,
                "provider_status": "api_error",
                "duration_ms": now_ms() - start_ms,
                "raw_response": raw_response,
            },
            "mapped": {"dataset_id": dataset_id, "rows": []},
        }

    rows = parse_socrata_rows(parsed_response)
    return {
        "attempt": {
            "provider": "socrata",
            "action": "query_dataset",
            "status": "found" if rows else "not_found",
            "http_status": response.status_code,
            "duration_ms": now_ms() - start_ms,
            "raw_response": raw_response,
        },
        "mapped": {
            "dataset_id": dataset_id,
            "rows": rows,
        },
    }
