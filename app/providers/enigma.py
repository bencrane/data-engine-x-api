# Last updated: 2026-03-18T20:15:00Z
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


SEARCH_BRANDS_BY_PROMPT_QUERY = """
query SearchBrandsByPrompt($searchInput: SearchInput!) {
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
  }
}
""".strip()


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


async def search_brands_by_prompt(
    *,
    api_key: str | None,
    prompt: str,
    state: str | None = None,
    city: str | None = None,
    limit: int = 10,
    page_token: str | None = None,
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

    safe_limit = max(1, min(int(limit), 100))

    search_input: dict[str, Any] = {
        "entityType": "BRAND",
        "prompt": normalized_prompt,
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

    request_payload = {
        "query": SEARCH_BRANDS_BY_PROMPT_QUERY,
        "variables": {"searchInput": search_input},
    }
    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            ENIGMA_GRAPHQL_URL,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            json=request_payload,
        )
        body = parse_json_or_raw(response.text, response.json)

    attempt: dict[str, Any] = {
        "provider": "enigma",
        "action": "search_brands_by_prompt",
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

    data = _as_dict(body.get("data"))
    search_results = _as_list(data.get("search"))
    if not search_results:
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    brands: list[dict[str, Any]] = []
    for result_item in search_results:
        brand = _as_dict(result_item)
        if not brand:
            continue

        brand_id = _as_str(brand.get("id")) or _as_str(brand.get("enigmaId"))
        if not brand_id:
            continue

        website_node = _first_edge_node(brand.get("websites"))
        industries_connection = _as_dict(brand.get("industries"))
        industries_edges = _as_list(industries_connection.get("edges"))
        industry_list: list[str] = []
        for ind_edge in industries_edges:
            ind_node = _as_dict(_as_dict(ind_edge).get("node"))
            desc = _as_str(ind_node.get("industryDesc"))
            if desc:
                industry_list.append(desc)

        brands.append({
            "enigma_brand_id": brand_id,
            "brand_name": _extract_brand_name(brand),
            "website": _as_str(website_node.get("website")),
            "location_count": _as_int(brand.get("count")),
            "industries": industry_list,
        })

    if not brands:
        attempt["status"] = "not_found"
        return {"attempt": attempt, "mapped": None}

    attempt["status"] = "found"

    current_offset = 0
    if page_token is not None:
        try:
            current_offset = int(page_token)
        except (TypeError, ValueError):
            current_offset = 0

    has_next = len(brands) >= safe_limit
    mapped = {
        "brands": brands,
        "total_returned": len(brands),
        "has_next_page": has_next,
        "next_page_token": str(current_offset + safe_limit) if has_next else None,
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
