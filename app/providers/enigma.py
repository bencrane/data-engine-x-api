# Last updated: 2026-03-18T21:30:00Z
from __future__ import annotations

import asyncio
import logging
import uuid as uuid_mod
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

logger = logging.getLogger(__name__)

ENIGMA_GRAPHQL_URL = "https://api.enigma.com/graphql"

SEARCH_BRAND_QUERY = """
query SearchBrand($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      names(first: 1) {
        edges {
          node {
            name
          }
        }
      }
      count(field: "operatingLocations")
    }
  }
}
""".strip()

GET_BRAND_ANALYTICS_QUERY = """
query GetBrandAnalytics(
  $searchInput: SearchInput!,
  $monthsBack: Int!,
  $oneMonthRevenueConditions: ConnectionConditions!,
  $twelveMonthRevenueConditions: ConnectionConditions!,
  $oneMonthGrowthConditions: ConnectionConditions!,
  $twelveMonthGrowthConditions: ConnectionConditions!,
  $oneMonthCustomersConditions: ConnectionConditions!,
  $twelveMonthCustomersConditions: ConnectionConditions!,
  $oneMonthTransactionsConditions: ConnectionConditions!,
  $twelveMonthTransactionsConditions: ConnectionConditions!,
  $oneMonthAvgTxnConditions: ConnectionConditions!,
  $twelveMonthAvgTxnConditions: ConnectionConditions!,
  $oneMonthRefundsConditions: ConnectionConditions!,
  $twelveMonthRefundsConditions: ConnectionConditions!
) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      namesConnection(first: 1) {
        edges {
          node {
            name
          }
        }
      }
      oneMonthCardRevenueAmountsConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthRevenueConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthCardRevenueAmountsConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthRevenueConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
      oneMonthCardRevenueYoyGrowthsConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthGrowthConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthCardRevenueYoyGrowthsConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthGrowthConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
      oneMonthCardCustomersAverageDailyCountsConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthCustomersConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthCardCustomersAverageDailyCountsConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthCustomersConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
      oneMonthCardTransactionsCountsConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthTransactionsConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthCardTransactionsCountsConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthTransactionsConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
      oneMonthAvgTransactionSizesConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthAvgTxnConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthAvgTransactionSizesConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthAvgTxnConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
      oneMonthRefundsAmountsConnection: cardTransactions(
        first: $monthsBack,
        conditions: $oneMonthRefundsConditions
      ) {
        edges {
          node {
            projectedQuantity
            periodStartDate
          }
        }
      }
      twelveMonthRefundsAmountsConnection: cardTransactions(
        first: 1,
        conditions: $twelveMonthRefundsConditions
      ) {
        edges {
          node {
            projectedQuantity
          }
        }
      }
    }
  }
}
""".strip()

GET_BRAND_LOCATIONS_QUERY = """
query GetBrandLocations($searchInput: SearchInput!, $locationLimit: Int!, $locationConditions: ConnectionConditions) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      namesConnection(first: 1) {
        edges {
          node {
            name
          }
        }
      }
      totalLocationCount: count(field: "operatingLocations")
      operatingLocationsConnection(first: $locationLimit, conditions: $locationConditions) {
        totalCount
        edges {
          node {
            id
            names(first: 1) {
              edges {
                node {
                  name
                }
              }
            }
            addresses(first: 1) {
              edges {
                node {
                  fullAddress
                  streetAddress1
                  city
                  state
                  postalCode
                }
              }
            }
            operatingStatuses(first: 1) {
              edges {
                node {
                  operatingStatus
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
""".strip()


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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


def _first_edge_node(connection: Any) -> dict[str, Any]:
    connection_dict = _as_dict(connection)
    edges = _as_list(connection_dict.get("edges"))
    if not edges:
        return {}
    first_edge = _as_dict(edges[0])
    return _as_dict(first_edge.get("node"))


def _first_brand(body: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(body.get("data"))
    search_results = _as_list(data.get("search"))
    if not search_results:
        return {}
    return _as_dict(search_results[0])


def _extract_brand_name(brand: dict[str, Any]) -> str | None:
    name = _as_str(_first_edge_node(brand.get("names")).get("name"))
    if name:
        return name
    return _as_str(_first_edge_node(brand.get("namesConnection")).get("name"))


def _conditions(*, period: str, quantity_type: str) -> dict[str, Any]:
    return {
        "filter": {
            "AND": [
                {"EQ": ["period", period]},
                {"EQ": ["quantityType", quantity_type]},
            ]
        }
    }


def _series(connection: Any) -> list[dict[str, Any]] | None:
    connection_dict = _as_dict(connection)
    edges = _as_list(connection_dict.get("edges"))
    if not edges:
        return None
    points: list[dict[str, Any]] = []
    for edge in edges:
        node = _as_dict(_as_dict(edge).get("node"))
        period_start = _as_str(node.get("periodStartDate"))
        if not period_start:
            continue
        points.append(
            {
                "period_start": period_start,
                "value": _as_float(node.get("projectedQuantity")),
            }
        )
    return points or None


def _annual_metric(connection: Any) -> float | None:
    node = _first_edge_node(connection)
    return _as_float(node.get("projectedQuantity"))


def _map_operating_location(node: dict[str, Any]) -> dict[str, Any]:
    address_node = _first_edge_node(node.get("addresses"))
    operating_status_node = _first_edge_node(node.get("operatingStatuses"))
    return {
        "enigma_location_id": _as_str(node.get("id")),
        "location_name": _as_str(_first_edge_node(node.get("names")).get("name")),
        "full_address": _as_str(address_node.get("fullAddress")),
        "street": _as_str(address_node.get("streetAddress1")),
        "city": _as_str(address_node.get("city")),
        "state": _as_str(address_node.get("state")),
        "postal_code": _as_str(address_node.get("postalCode")),
        "operating_status": _as_str(operating_status_node.get("operatingStatus")),
    }


def _match_search_input(*, company_name: str | None, company_domain: str | None) -> dict[str, Any]:
    normalized_name = _as_str(company_name)
    normalized_domain = _as_str(company_domain)
    payload: dict[str, Any] = {
        "entityType": "BRAND",
        "name": normalized_name or normalized_domain,
    }
    if normalized_domain:
        payload["website"] = normalized_domain
    return payload


def _analytics_search_input(*, brand_id: str) -> dict[str, Any]:
    return {
        "entityType": "BRAND",
        "id": brand_id,
    }


async def _graphql_post(
    *,
    api_key: str,
    action: str,
    query: str,
    variables: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    payload = {
        "query": query,
        "variables": variables,
    }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            ENIGMA_GRAPHQL_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    attempt: dict[str, Any] = {
        "provider": "enigma",
        "action": action,
        "duration_ms": now_ms() - start_ms,
        "raw_response": body,
    }
    if response.status_code >= 400:
        attempt["status"] = "failed"
        attempt["http_status"] = response.status_code
        return attempt, {}, False

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        attempt["status"] = "failed"
        return attempt, {}, False

    brand = _first_brand(body)
    if not brand:
        attempt["status"] = "not_found"
        return attempt, {}, True

    attempt["status"] = "found"
    return attempt, brand, True


POLL_BACKGROUND_TASK_QUERY = """
query PollBackgroundTask($taskId: String!) {
  backgroundTask(id: $taskId) {
    id
    status
    result
    lastError
    executionAttempts
    createdTimestamp
    updatedTimestamp
  }
}
""".strip()


async def _graphql_post_async(
    *,
    api_key: str,
    action: str,
    query: str,
    variables: dict[str, Any],
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = 300.0,
) -> tuple[dict[str, Any], dict[str, Any] | list[Any], bool]:
    """Submit a GraphQL query that may return 202 Accepted (async background task).

    Handles the full async lifecycle: submit, poll backgroundTask(id), retrieve result.
    Falls back to synchronous handling if the API returns 200 directly.

    Returns the same 3-tuple as _graphql_post(): (attempt_dict, data, is_terminal).
    """
    payload = {
        "query": query,
        "variables": variables,
    }
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    start_ms = now_ms()

    # --- Submit ---
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(ENIGMA_GRAPHQL_URL, headers=headers, json=payload)
        body = parse_json_or_raw(response.text, response.json)

    attempt: dict[str, Any] = {
        "provider": "enigma",
        "action": action,
        "duration_ms": now_ms() - start_ms,
        "raw_response": body,
    }

    # Rate limit / payment errors — do not retry
    if response.status_code == 429:
        attempt["status"] = "failed"
        attempt["http_status"] = 429
        attempt["skip_reason"] = "rate_limited"
        return attempt, {}, False

    if response.status_code == 402:
        attempt["status"] = "failed"
        attempt["http_status"] = 402
        attempt["skip_reason"] = "insufficient_credits"
        return attempt, {}, False

    if response.status_code >= 400:
        attempt["status"] = "failed"
        attempt["http_status"] = response.status_code
        return attempt, {}, False

    errors = body.get("errors") if isinstance(body, dict) else None
    if isinstance(errors, list) and errors:
        attempt["status"] = "failed"
        return attempt, {}, False

    # --- Synchronous fallback (200 with inline results) ---
    if response.status_code == 200:
        data = _as_dict(body.get("data")) if isinstance(body, dict) else {}
        search_results = _as_list(data.get("search"))
        if not search_results:
            attempt["status"] = "not_found"
            return attempt, {}, True
        attempt["status"] = "found"
        return attempt, search_results, True

    # --- Async path (202 Accepted) ---
    if response.status_code != 202:
        attempt["status"] = "failed"
        attempt["http_status"] = response.status_code
        return attempt, {}, False

    # Extract background task ID from 202 response.
    # The exact shape is not fully documented — log it and try multiple paths.
    logger.info(
        "Enigma async 202 response body (action=%s): %s",
        action,
        body,
    )
    task_id: str | None = None
    if isinstance(body, dict):
        # Try common paths: data.search[0].id, data.backgroundTask.id, taskId, id
        bg_task = _as_dict(body.get("data", {})).get("backgroundTask")
        if isinstance(bg_task, dict):
            task_id = _as_str(bg_task.get("id"))
        if not task_id:
            task_id = _as_str(body.get("taskId")) or _as_str(body.get("id"))
        if not task_id:
            # Some APIs return the task ID nested in data
            task_id = _as_str(_as_dict(body.get("data")).get("taskId"))
            if not task_id:
                task_id = _as_str(_as_dict(body.get("data")).get("id"))

    if not task_id:
        attempt["status"] = "failed"
        attempt["error"] = "async_task_id_not_found"
        logger.error(
            "Could not extract background task ID from 202 response (action=%s): %s",
            action,
            body,
        )
        return attempt, {}, False

    attempt["background_task_id"] = task_id
    logger.info(
        "Enigma async task submitted (action=%s, task_id=%s, prompt entity_type in variables)",
        action,
        task_id,
    )

    # --- Poll loop ---
    poll_count = 0
    elapsed_seconds = 0.0
    current_interval = poll_interval_seconds

    async with httpx.AsyncClient(timeout=30.0) as client:
        while elapsed_seconds < max_wait_seconds:
            await asyncio.sleep(current_interval)
            elapsed_seconds += current_interval
            poll_count += 1

            # Escalate interval: after 5 polls, double (capped at 30s)
            if poll_count == 5:
                current_interval = min(current_interval * 2, 30.0)

            poll_response = await client.post(
                ENIGMA_GRAPHQL_URL,
                headers=headers,
                json={
                    "query": POLL_BACKGROUND_TASK_QUERY,
                    "variables": {"taskId": task_id},
                },
            )
            poll_body = parse_json_or_raw(poll_response.text, poll_response.json)

            if poll_response.status_code >= 400:
                logger.warning(
                    "Enigma poll request failed (task_id=%s, status=%s): %s",
                    task_id,
                    poll_response.status_code,
                    poll_body,
                )
                continue  # Transient poll failure — retry

            task_data = _as_dict(
                _as_dict(poll_body.get("data") if isinstance(poll_body, dict) else {}).get("backgroundTask")
            )
            status = _as_str(task_data.get("status")) or ""

            logger.info(
                "Enigma poll (task_id=%s, poll=%d, elapsed=%.1fs, status=%s)",
                task_id,
                poll_count,
                elapsed_seconds,
                status,
            )

            if status == "SUCCESS":
                result = task_data.get("result")
                # Log the raw result shape on first success for future reference
                # ASSUMPTION: result is either inline JSON data (list/dict) or a URL string
                logger.info(
                    "Enigma async task SUCCESS (task_id=%s). Result type=%s, raw_result=%s",
                    task_id,
                    type(result).__name__,
                    str(result)[:2000],
                )

                # If result is a URL string (S3 pre-signed), fetch it
                if isinstance(result, str) and result.startswith("http"):
                    async with httpx.AsyncClient(timeout=60.0) as download_client:
                        download_resp = await download_client.get(result)
                        if download_resp.status_code == 200:
                            result = parse_json_or_raw(download_resp.text, download_resp.json)
                        else:
                            attempt["status"] = "failed"
                            attempt["error"] = f"download_failed_{download_resp.status_code}"
                            return attempt, {}, False

                attempt["status"] = "found"
                attempt["duration_ms"] = now_ms() - start_ms
                attempt["poll_count"] = poll_count
                attempt["background_task_status"] = "SUCCESS"

                # Return result as-is — caller handles mapping
                if isinstance(result, list):
                    return attempt, result, True
                if isinstance(result, dict):
                    # Check if result wraps search results
                    search_in_result = _as_list(result.get("search")) or _as_list(result.get("data", {}).get("search") if isinstance(result.get("data"), dict) else [])
                    if search_in_result:
                        return attempt, search_in_result, True
                    return attempt, result, True
                # Unexpected shape
                logger.warning(
                    "Enigma async result has unexpected type %s (task_id=%s)",
                    type(result).__name__,
                    task_id,
                )
                attempt["status"] = "found"
                return attempt, result if isinstance(result, (dict, list)) else {}, True

            if status in ("FAILED", "CANCELLED"):
                last_error = _as_str(task_data.get("lastError")) or status
                attempt["status"] = "failed"
                attempt["error"] = last_error
                attempt["background_task_status"] = status
                attempt["duration_ms"] = now_ms() - start_ms
                attempt["poll_count"] = poll_count
                return attempt, {}, False

            # Still PROCESSING — continue polling

    # Timeout
    attempt["status"] = "failed"
    attempt["error"] = "background_task_timeout"
    attempt["duration_ms"] = now_ms() - start_ms
    attempt["poll_count"] = poll_count
    return attempt, {}, False


async def match_business(
    *,
    api_key: str | None,
    company_name: str | None,
    company_domain: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "match_business",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_name = _as_str(company_name)
    normalized_domain = _as_str(company_domain)
    if not normalized_name and not normalized_domain:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "match_business",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    attempt, brand, is_terminal = await _graphql_post(
        api_key=api_key,
        action="match_business",
        query=SEARCH_BRAND_QUERY,
        variables={
            "searchInput": _match_search_input(company_name=normalized_name, company_domain=normalized_domain),
        },
    )
    if not is_terminal or attempt.get("status") != "found":
        return {"attempt": attempt, "mapped": None}

    mapped = {
        "enigma_brand_id": _as_str(brand.get("id")) or _as_str(brand.get("enigmaId")),
        "brand_name": _extract_brand_name(brand),
        "location_count": _as_int(brand.get("count")),
    }
    if not mapped["enigma_brand_id"]:
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    return {"attempt": attempt, "mapped": mapped}


async def get_card_analytics(
    *,
    api_key: str | None,
    brand_id: str | None,
    months_back: int,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_card_analytics",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }
    normalized_brand_id = _as_str(brand_id)
    if not normalized_brand_id:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_card_analytics",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    safe_months_back = max(1, min(int(months_back), 24))
    variables = {
        "searchInput": _analytics_search_input(brand_id=normalized_brand_id),
        "monthsBack": safe_months_back,
        "oneMonthRevenueConditions": _conditions(period="1m", quantity_type="card_revenue_amount"),
        "twelveMonthRevenueConditions": _conditions(period="12m", quantity_type="card_revenue_amount"),
        "oneMonthGrowthConditions": _conditions(period="1m", quantity_type="card_revenue_yoy_growth"),
        "twelveMonthGrowthConditions": _conditions(period="12m", quantity_type="card_revenue_yoy_growth"),
        "oneMonthCustomersConditions": _conditions(period="1m", quantity_type="card_customers_average_daily_count"),
        "twelveMonthCustomersConditions": _conditions(period="12m", quantity_type="card_customers_average_daily_count"),
        "oneMonthTransactionsConditions": _conditions(period="1m", quantity_type="card_transactions_count"),
        "twelveMonthTransactionsConditions": _conditions(period="12m", quantity_type="card_transactions_count"),
        "oneMonthAvgTxnConditions": _conditions(period="1m", quantity_type="average_transaction_size"),
        "twelveMonthAvgTxnConditions": _conditions(period="12m", quantity_type="average_transaction_size"),
        "oneMonthRefundsConditions": _conditions(period="1m", quantity_type="refunds_amount"),
        "twelveMonthRefundsConditions": _conditions(period="12m", quantity_type="refunds_amount"),
    }

    attempt, brand, is_terminal = await _graphql_post(
        api_key=api_key,
        action="get_card_analytics",
        query=GET_BRAND_ANALYTICS_QUERY,
        variables=variables,
    )
    if not is_terminal or attempt.get("status") != "found":
        return {"attempt": attempt, "mapped": None}

    mapped = {
        "brand_name": _extract_brand_name(brand),
        "annual_card_revenue": _annual_metric(brand.get("twelveMonthCardRevenueAmountsConnection")),
        "annual_card_revenue_yoy_growth": _annual_metric(brand.get("twelveMonthCardRevenueYoyGrowthsConnection")),
        "annual_avg_daily_customers": _annual_metric(brand.get("twelveMonthCardCustomersAverageDailyCountsConnection")),
        "annual_transaction_count": _annual_metric(brand.get("twelveMonthCardTransactionsCountsConnection")),
        "annual_avg_transaction_size": _annual_metric(brand.get("twelveMonthAvgTransactionSizesConnection")),
        "annual_refunds": _annual_metric(brand.get("twelveMonthRefundsAmountsConnection")),
        "monthly_revenue": _series(brand.get("oneMonthCardRevenueAmountsConnection")),
        "monthly_revenue_growth": _series(brand.get("oneMonthCardRevenueYoyGrowthsConnection")),
        "monthly_avg_daily_customers": _series(brand.get("oneMonthCardCustomersAverageDailyCountsConnection")),
        "monthly_transactions": _series(brand.get("oneMonthCardTransactionsCountsConnection")),
        "monthly_avg_transaction_size": _series(brand.get("oneMonthAvgTransactionSizesConnection")),
        "monthly_refunds": _series(brand.get("oneMonthRefundsAmountsConnection")),
    }
    return {"attempt": attempt, "mapped": mapped}


async def get_brand_locations(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 25,
    operating_status_filter: str | None = None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_brand_locations",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_brand_id = _as_str(brand_id)
    if not normalized_brand_id:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_brand_locations",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 25
    safe_limit = max(1, min(parsed_limit, 100))

    normalized_status_filter = _as_str(operating_status_filter)
    location_conditions = None
    if normalized_status_filter:
        location_conditions = {
            "filter": {"EQ": ["operatingStatuses.operatingStatus", normalized_status_filter]},
        }

    variables = {
        "searchInput": _analytics_search_input(brand_id=normalized_brand_id),
        "locationLimit": safe_limit,
        "locationConditions": location_conditions,
    }
    attempt, brand, is_terminal = await _graphql_post(
        api_key=api_key,
        action="get_brand_locations",
        query=GET_BRAND_LOCATIONS_QUERY,
        variables=variables,
    )
    if not is_terminal or attempt.get("status") != "found":
        return {"attempt": attempt, "mapped": None}

    locations_connection = _as_dict(brand.get("operatingLocationsConnection"))
    edges = _as_list(locations_connection.get("edges"))
    locations = [
        _map_operating_location(_as_dict(edge).get("node"))
        for edge in edges
        if _as_dict(_as_dict(edge).get("node"))
    ]
    page_info = _as_dict(locations_connection.get("pageInfo"))
    has_next_page_raw = page_info.get("hasNextPage")
    has_next_page = has_next_page_raw if isinstance(has_next_page_raw, bool) else None
    end_cursor = _as_str(page_info.get("endCursor"))

    mapped = {
        "brand_name": _extract_brand_name(brand),
        "enigma_brand_id": _as_str(brand.get("id")),
        "total_location_count": _as_int(brand.get("totalLocationCount")),
        "locations": locations,
        "location_count": len(locations),
        "open_count": sum(1 for loc in locations if loc.get("operating_status") == "Open"),
        "closed_count": sum(
            1 for loc in locations if loc.get("operating_status") in ("Closed", "Temporarily Closed")
        ),
        "has_next_page": has_next_page,
        "end_cursor": end_cursor,
    }
    return {"attempt": attempt, "mapped": mapped}


SEARCH_BRANDS_BY_PROMPT_BRAND_FRAGMENT = """
    ... on Brand {
      id
      enigmaId
      names(first: 1) {
        edges {
          node {
            name
          }
        }
      }
      websites(first: 1) {
        edges {
          node {
            website
          }
        }
      }
      count(field: "operatingLocations")
      industries(first: 3) {
        edges {
          node {
            industryDesc
          }
        }
      }
    }
""".strip()

SEARCH_BRANDS_BY_PROMPT_LOCATION_FRAGMENT = """
    ... on OperatingLocation {
      id
      enigmaId
      names(first: 1) { edges { node { name } } }
      addresses(first: 1) {
        edges {
          node {
            fullAddress
            streetAddress1
            city
            state
            postalCode
          }
        }
      }
      operatingStatuses(first: 1) { edges { node { operatingStatus } } }
      websites(first: 1) { edges { node { website } } }
      phoneNumbers(first: 1) { edges { node { phoneNumber } } }
      brands(first: 1) {
        edges {
          node {
            id
            names(first: 1) { edges { node { name } } }
          }
        }
      }
    }
""".strip()


def _build_search_by_prompt_query(entity_type: str) -> str:
    if entity_type == "OPERATING_LOCATION":
        fragment = SEARCH_BRANDS_BY_PROMPT_LOCATION_FRAGMENT
    else:
        fragment = SEARCH_BRANDS_BY_PROMPT_BRAND_FRAGMENT
    return f"query SearchByPrompt($searchInput: SearchInput!) {{\n  search(searchInput: $searchInput) {{\n    {fragment}\n  }}\n}}"


# Keep for backwards compatibility with any direct references
SEARCH_BRANDS_BY_PROMPT_QUERY = _build_search_by_prompt_query("BRAND")


def _build_locations_enriched_query(
    *,
    include_card_transactions: bool = False,
    include_ranks: bool = False,
    include_reviews: bool = False,
    include_roles: bool = False,
) -> str:
    card_txn_fragment = ""
    if include_card_transactions:
        card_txn_fragment = """
            twelveMonthRevenueConnection: cardTransactions(
              first: 1,
              conditions: {filter: {AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_revenue_amount"]}]}}
            ) { edges { node { projectedQuantity } } }
            twelveMonthGrowthConnection: cardTransactions(
              first: 1,
              conditions: {filter: {AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_revenue_yoy_growth"]}]}}
            ) { edges { node { projectedQuantity } } }
            twelveMonthCustomersConnection: cardTransactions(
              first: 1,
              conditions: {filter: {AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_customers_average_daily_count"]}]}}
            ) { edges { node { projectedQuantity } } }
            twelveMonthTransactionsConnection: cardTransactions(
              first: 1,
              conditions: {filter: {AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_transactions_count"]}]}}
            ) { edges { node { projectedQuantity } } }
"""

    ranks_fragment = ""
    if include_ranks:
        ranks_fragment = """
            ranks(first: 1) {
              edges {
                node {
                  position
                  cohortSize
                }
              }
            }
"""

    reviews_fragment = ""
    if include_reviews:
        reviews_fragment = """
            reviewSummaries(first: 1) {
              edges {
                node {
                  reviewCount
                  reviewScoreAvg
                }
              }
            }
"""

    roles_fragment = ""
    if include_roles:
        roles_fragment = """
            roles(first: 10) {
              edges {
                node {
                  jobTitle
                  jobFunction
                  managementLevel
                  emailAddresses(first: 3) {
                    edges {
                      node {
                        emailAddress
                      }
                    }
                  }
                  phoneNumbers(first: 3) {
                    edges {
                      node {
                        phoneNumber
                      }
                    }
                  }
                  legalEntities(first: 1) {
                    edges {
                      node {
                        persons(first: 1) {
                          edges {
                            node {
                              fullName
                              firstName
                              lastName
                            }
                          }
                        }
                      }
                    }
                  }
                }
              }
            }
"""

    return f"""
query GetLocationsEnriched($searchInput: SearchInput!, $locationLimit: Int!, $locationConditions: ConnectionConditions) {{
  search(searchInput: $searchInput) {{
    ... on Brand {{
      id
      namesConnection(first: 1) {{
        edges {{
          node {{
            name
          }}
        }}
      }}
      totalLocationCount: count(field: "operatingLocations")
      operatingLocationsConnection(first: $locationLimit, conditions: $locationConditions) {{
        totalCount
        edges {{
          node {{
            id
            names(first: 1) {{
              edges {{
                node {{
                  name
                }}
              }}
            }}
            addresses(first: 1) {{
              edges {{
                node {{
                  fullAddress
                  streetAddress1
                  city
                  state
                  postalCode
                }}
              }}
            }}
            operatingStatuses(first: 1) {{
              edges {{
                node {{
                  operatingStatus
                }}
              }}
            }}
            phoneNumbers(first: 1) {{
              edges {{
                node {{
                  phoneNumber
                }}
              }}
            }}
            websites(first: 1) {{
              edges {{
                node {{
                  website
                }}
              }}
            }}
            {card_txn_fragment}
            {ranks_fragment}
            {reviews_fragment}
            {roles_fragment}
          }}
        }}
        pageInfo {{
          hasNextPage
          endCursor
        }}
      }}
    }}
  }}
}}
""".strip()


def _map_enriched_location(node: dict[str, Any]) -> dict[str, Any]:
    base = _map_operating_location(node)

    phone_node = _first_edge_node(node.get("phoneNumbers"))
    base["phone"] = _as_str(phone_node.get("phoneNumber"))

    website_node = _first_edge_node(node.get("websites"))
    base["website"] = _as_str(website_node.get("website"))

    revenue_node = _first_edge_node(node.get("twelveMonthRevenueConnection"))
    if revenue_node:
        base["annual_card_revenue"] = _as_float(revenue_node.get("projectedQuantity"))

    growth_node = _first_edge_node(node.get("twelveMonthGrowthConnection"))
    if growth_node:
        base["annual_card_revenue_yoy_growth"] = _as_float(growth_node.get("projectedQuantity"))

    customers_node = _first_edge_node(node.get("twelveMonthCustomersConnection"))
    if customers_node:
        base["annual_avg_daily_customers"] = _as_float(customers_node.get("projectedQuantity"))

    txn_node = _first_edge_node(node.get("twelveMonthTransactionsConnection"))
    if txn_node:
        base["annual_transaction_count"] = _as_float(txn_node.get("projectedQuantity"))

    rank_node = _first_edge_node(node.get("ranks"))
    if rank_node:
        base["competitive_rank"] = _as_int(rank_node.get("position"))
        base["competitive_rank_total"] = _as_int(rank_node.get("cohortSize"))

    review_node = _first_edge_node(node.get("reviewSummaries"))
    if review_node:
        base["review_count"] = _as_int(review_node.get("reviewCount"))
        base["review_avg_rating"] = _as_float(review_node.get("reviewScoreAvg"))

    roles_connection = _as_dict(node.get("roles"))
    roles_edges = _as_list(roles_connection.get("edges"))
    if roles_edges:
        contacts: list[dict[str, Any]] = []
        for role_edge in roles_edges:
            role_node = _as_dict(_as_dict(role_edge).get("node"))
            if not role_node:
                continue

            email_node = _first_edge_node(role_node.get("emailAddresses"))
            phone_contact_node = _first_edge_node(role_node.get("phoneNumbers"))

            legal_entity_node = _first_edge_node(role_node.get("legalEntities"))
            person_node = _first_edge_node(legal_entity_node.get("persons")) if legal_entity_node else {}
            full_name = _as_str(person_node.get("fullName"))
            if not full_name:
                first = _as_str(person_node.get("firstName")) or ""
                last = _as_str(person_node.get("lastName")) or ""
                combined = f"{first} {last}".strip()
                full_name = combined if combined else None

            contacts.append({
                "full_name": full_name,
                "job_title": _as_str(role_node.get("jobTitle")),
                "job_function": _as_str(role_node.get("jobFunction")),
                "management_level": _as_str(role_node.get("managementLevel")),
                "email": _as_str(email_node.get("emailAddress")),
                "phone": _as_str(phone_contact_node.get("phoneNumber")),
            })
        if contacts:
            base["contacts"] = contacts

    return base


def _map_brand_result(brand: dict[str, Any]) -> dict[str, Any] | None:
    """Map a Brand GraphQL result to the standard brand item dict."""
    brand_id = _as_str(brand.get("id")) or _as_str(brand.get("enigmaId"))
    if not brand_id:
        return None

    website_node = _first_edge_node(brand.get("websites"))
    industries_connection = _as_dict(brand.get("industries"))
    industries_edges = _as_list(industries_connection.get("edges"))
    industry_list: list[str] = []
    for ind_edge in industries_edges:
        ind_node = _as_dict(_as_dict(ind_edge).get("node"))
        desc = _as_str(ind_node.get("industryDesc"))
        if desc:
            industry_list.append(desc)

    return {
        "enigma_brand_id": brand_id,
        "brand_name": _extract_brand_name(brand),
        "website": _as_str(website_node.get("website")),
        "location_count": _as_int(brand.get("count")),
        "industries": industry_list,
    }


def _map_location_result(loc: dict[str, Any]) -> dict[str, Any] | None:
    """Map an OperatingLocation GraphQL result to the location item dict."""
    loc_id = _as_str(loc.get("id")) or _as_str(loc.get("enigmaId"))
    if not loc_id:
        return None

    address_node = _first_edge_node(loc.get("addresses"))
    status_node = _first_edge_node(loc.get("operatingStatuses"))
    website_node = _first_edge_node(loc.get("websites"))
    phone_node = _first_edge_node(loc.get("phoneNumbers"))

    # Extract parent brand info if available
    brand_node = _first_edge_node(loc.get("brands"))
    parent_brand_id = _as_str(brand_node.get("id")) if brand_node else None
    parent_brand_name = _as_str(_first_edge_node(brand_node.get("names")).get("name")) if brand_node else None

    return {
        "enigma_location_id": loc_id,
        "location_name": _as_str(_first_edge_node(loc.get("names")).get("name")),
        "full_address": _as_str(address_node.get("fullAddress")),
        "street": _as_str(address_node.get("streetAddress1")),
        "city": _as_str(address_node.get("city")),
        "state": _as_str(address_node.get("state")),
        "postal_code": _as_str(address_node.get("postalCode")),
        "operating_status": _as_str(status_node.get("operatingStatus")),
        "website": _as_str(website_node.get("website")),
        "phone": _as_str(phone_node.get("phoneNumber")),
        "parent_brand_id": parent_brand_id,
        "parent_brand_name": parent_brand_name,
    }


async def search_brands_by_prompt(
    *,
    api_key: str | None,
    prompt: str,
    entity_type: str = "BRAND",
    state: str | None = None,
    city: str | None = None,
    limit: int = 10,
    page_token: str | None = None,
    poll_interval_seconds: float = 5.0,
    max_wait_seconds: float = 300.0,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "search_brands_by_prompt",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_prompt = _as_str(prompt)
    if not normalized_prompt:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "search_brands_by_prompt",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    # Validate entity type
    valid_entity_types = {"BRAND", "OPERATING_LOCATION"}
    resolved_entity_type = entity_type.upper() if entity_type and entity_type.upper() in valid_entity_types else "BRAND"

    safe_limit = max(1, min(int(limit), 100))

    search_input: dict[str, Any] = {
        "entityType": resolved_entity_type,
        "prompt": normalized_prompt,
        "output": {
            "filename": f"brand_discovery_{uuid_mod.uuid4().hex[:12]}",
        },
        "conditions": {"limit": safe_limit},
    }
    if page_token:
        search_input["conditions"]["pageToken"] = page_token

    normalized_state = _as_str(state)
    normalized_city = _as_str(city)
    if normalized_state or normalized_city:
        address: dict[str, str] = {}
        if normalized_state:
            address["state"] = normalized_state
        if normalized_city:
            address["city"] = normalized_city
        search_input["address"] = address

    # Log credit usage for rate limit tracking
    logger.info(
        "Enigma async search submission (entity_type=%s, prompt=%s, limit=%d)",
        resolved_entity_type,
        normalized_prompt[:200],
        safe_limit,
    )

    query = _build_search_by_prompt_query(resolved_entity_type)

    attempt, data, is_terminal = await _graphql_post_async(
        api_key=api_key,
        action="search_brands_by_prompt",
        query=query,
        variables={"searchInput": search_input},
        poll_interval_seconds=poll_interval_seconds,
        max_wait_seconds=max_wait_seconds,
    )

    if not is_terminal or attempt.get("status") != "found":
        return {"attempt": attempt, "mapped": None}

    # --- Map results based on entity type ---
    # The async result from _graphql_post_async returns either:
    # - a list of result items (from search results array)
    # - a dict that may contain search results nested inside
    # ASSUMPTION: The background task result contains the same GraphQL entity objects
    # as the synchronous search response would. If the shape differs, this mapping
    # will log a warning and return not_found so the issue is visible.
    result_items: list[Any] = []
    if isinstance(data, list):
        result_items = data
    elif isinstance(data, dict):
        # Try to extract from common wrapper shapes
        result_items = _as_list(data.get("search")) or _as_list(data.get("results")) or _as_list(data.get("data"))
        if not result_items:
            # The dict itself might be a single result — wrap it
            result_items = [data] if data else []

    if not result_items:
        logger.warning(
            "Enigma async result had no extractable items (entity_type=%s, data_type=%s)",
            resolved_entity_type,
            type(data).__name__,
        )
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    # Log result shape for documentation
    logger.info(
        "Enigma async result mapping: entity_type=%s, item_count=%d, first_item_keys=%s",
        resolved_entity_type,
        len(result_items),
        list(_as_dict(result_items[0]).keys())[:15] if result_items else [],
    )

    if resolved_entity_type == "OPERATING_LOCATION":
        locations: list[dict[str, Any]] = []
        for item in result_items:
            mapped_loc = _map_location_result(_as_dict(item))
            if mapped_loc:
                locations.append(mapped_loc)

        if not locations:
            attempt["status"] = "not_found"
            return {"attempt": attempt, "mapped": None}

        # Async results are assumed to be complete (no pagination)
        mapped: dict[str, Any] = {
            "locations": locations,
            "brands": None,
            "entity_type": "OPERATING_LOCATION",
            "total_returned": len(locations),
            "has_next_page": False,
            "next_page_token": None,
        }
        return {"attempt": attempt, "mapped": mapped}

    # BRAND entity type
    brands: list[dict[str, Any]] = []
    for item in result_items:
        mapped_brand = _map_brand_result(_as_dict(item))
        if mapped_brand:
            brands.append(mapped_brand)

    if not brands:
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    # Async results are assumed to be complete (no pagination)
    mapped = {
        "brands": brands,
        "locations": None,
        "entity_type": "BRAND",
        "total_returned": len(brands),
        "has_next_page": False,
        "next_page_token": None,
    }
    return {"attempt": attempt, "mapped": mapped}


async def get_locations_enriched(
    *,
    api_key: str | None,
    brand_id: str,
    limit: int = 25,
    operating_status_filter: str | None = None,
    include_card_transactions: bool = False,
    include_ranks: bool = False,
    include_reviews: bool = False,
    include_roles: bool = False,
    page_token: str | None = None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_locations_enriched",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    normalized_brand_id = _as_str(brand_id)
    if not normalized_brand_id:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "get_locations_enriched",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    try:
        parsed_limit = int(limit)
    except (TypeError, ValueError):
        parsed_limit = 25
    safe_limit = max(1, min(parsed_limit, 100))

    normalized_status_filter = _as_str(operating_status_filter)
    location_conditions: dict[str, Any] | None = None
    if normalized_status_filter:
        location_conditions = {
            "filter": {"EQ": ["operatingStatuses.operatingStatus", normalized_status_filter]},
        }
    if page_token:
        if location_conditions is None:
            location_conditions = {}
        location_conditions["pageToken"] = page_token

    query = _build_locations_enriched_query(
        include_card_transactions=include_card_transactions,
        include_ranks=include_ranks,
        include_reviews=include_reviews,
        include_roles=include_roles,
    )

    variables = {
        "searchInput": _analytics_search_input(brand_id=normalized_brand_id),
        "locationLimit": safe_limit,
        "locationConditions": location_conditions,
    }

    request_payload = {
        "query": query,
        "variables": variables,
    }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            ENIGMA_GRAPHQL_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=request_payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    attempt: dict[str, Any] = {
        "provider": "enigma",
        "action": "get_locations_enriched",
        "duration_ms": now_ms() - start_ms,
        "raw_response": body,
    }
    if response.status_code >= 400:
        attempt["status"] = "failed"
        attempt["http_status"] = response.status_code
        return {"attempt": attempt, "mapped": None}

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        attempt["status"] = "failed"
        return {"attempt": attempt, "mapped": None}

    brand = _first_brand(body)
    if not brand:
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    attempt["status"] = "found"

    locations_connection = _as_dict(brand.get("operatingLocationsConnection"))
    edges = _as_list(locations_connection.get("edges"))
    locations = [
        _map_enriched_location(_as_dict(_as_dict(edge).get("node")))
        for edge in edges
        if _as_dict(_as_dict(edge).get("node"))
    ]
    page_info = _as_dict(locations_connection.get("pageInfo"))
    has_next_page_raw = page_info.get("hasNextPage")
    has_next_page = has_next_page_raw if isinstance(has_next_page_raw, bool) else None
    end_cursor = _as_str(page_info.get("endCursor"))

    mapped = {
        "brand_name": _extract_brand_name(brand),
        "enigma_brand_id": _as_str(brand.get("id")),
        "total_location_count": _as_int(brand.get("totalLocationCount")),
        "locations": locations,
        "location_count": len(locations),
        "open_count": sum(1 for loc in locations if loc.get("operating_status") == "Open"),
        "closed_count": sum(
            1 for loc in locations if loc.get("operating_status") in ("Closed", "Temporarily Closed")
        ),
        "has_next_page": has_next_page,
        "end_cursor": end_cursor,
    }
    return {"attempt": attempt, "mapped": mapped}
