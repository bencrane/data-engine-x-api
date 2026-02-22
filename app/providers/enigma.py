from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

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
