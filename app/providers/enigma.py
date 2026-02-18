from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

ENIGMA_GRAPHQL_URL = "https://api.enigma.com/graphql"

SEARCH_BRAND_QUERY = """
query SearchBrand($searchInput: SearchInput!, $cardTransactionConditions: ConnectionConditions!) {
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
      cardTransactions(first: 1, conditions: $cardTransactionConditions) {
        edges {
          node {
            projectedQuantity
            quantityType
            period
            periodStartDate
            periodEndDate
          }
        }
      }
      operatingLocations(first: 1) {
        edges {
          node {
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
                  city
                  state
                }
              }
            }
            ranks(first: 1) {
              edges {
                node {
                  position
                  cohortSize
                  quantityType
                  period
                }
              }
            }
          }
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


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _first_edge_node(connection: Any) -> dict[str, Any]:
    connection_dict = _as_dict(connection)
    edges = _as_list(connection_dict.get("edges"))
    if not edges:
        return {}
    first_edge = _as_dict(edges[0])
    return _as_dict(first_edge.get("node"))


def _build_search_input(*, company_name: str | None, company_domain: str | None) -> dict[str, Any]:
    normalized_name = _as_str(company_name)
    normalized_domain = _as_str(company_domain)
    search_name = normalized_name or normalized_domain
    payload: dict[str, Any] = {
        "entityType": "BRAND",
        "name": search_name,
    }
    # Enigma allows website-only lookup, but omit when empty/null.
    if normalized_domain:
        payload["website"] = normalized_domain
    return payload


def _extract_brand_payload(body: dict[str, Any]) -> dict[str, Any]:
    data = _as_dict(body.get("data"))
    search_results = _as_list(data.get("search"))
    if not search_results:
        return {}

    brand = _as_dict(search_results[0])
    card_transaction = _first_edge_node(brand.get("cardTransactions"))

    top_location = _first_edge_node(brand.get("operatingLocations"))
    top_location_name_node = _first_edge_node(top_location.get("names"))
    top_location_address_node = _first_edge_node(top_location.get("addresses"))
    top_location_rank_node = _first_edge_node(top_location.get("ranks"))

    return {
        "enigma_brand_id": _as_str(brand.get("id")),
        "brand_name": _as_str(_first_edge_node(brand.get("names")).get("name")),
        "location_count": _as_int(brand.get("count")),
        # Per Enigma docs/examples, projectedQuantity for card_revenue_amount is a currency amount
        # unit represented by Enigma (not explicitly guaranteed as cents vs dollars in docs).
        "annual_card_revenue": _as_int(card_transaction.get("projectedQuantity")),
        "card_revenue_period": _as_str(card_transaction.get("period")),
        "card_revenue_period_start": _as_str(card_transaction.get("periodStartDate")),
        "card_revenue_period_end": _as_str(card_transaction.get("periodEndDate")),
        "top_location_name": _as_str(top_location_name_node.get("name")),
        "top_location_address": _as_str(top_location_address_node.get("fullAddress")),
        "top_location_city": _as_str(top_location_address_node.get("city")),
        "top_location_state": _as_str(top_location_address_node.get("state")),
        "top_location_rank_position": _as_int(top_location_rank_node.get("position")),
        "top_location_rank_cohort_size": _as_int(top_location_rank_node.get("cohortSize")),
    }


async def enrich_card_revenue(
    *,
    api_key: str | None,
    company_name: str | None,
    company_domain: str | None,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "card_revenue",
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
                "action": "card_revenue",
                "status": "skipped",
                "skip_reason": "missing_required_inputs",
            },
            "mapped": None,
        }

    variables = {
        "searchInput": _build_search_input(company_name=normalized_name, company_domain=normalized_domain),
        "cardTransactionConditions": {
            "filter": {
                "AND": [
                    {"EQ": ["period", "12m"]},
                    {"EQ": ["quantityType", "card_revenue_amount"]},
                    {"EQ": ["rank", 0]},
                ]
            }
        },
    }

    payload = {
        "query": SEARCH_BRAND_QUERY,
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

    if response.status_code >= 400:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "card_revenue",
                "status": "failed",
                "http_status": response.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "card_revenue",
                "status": "failed",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    mapped = _extract_brand_payload(body)
    if not mapped:
        return {
            "attempt": {
                "provider": "enigma",
                "action": "card_revenue",
                "status": "not_found",
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    return {
        "attempt": {
            "provider": "enigma",
            "action": "card_revenue",
            "status": "found",
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": mapped,
    }
