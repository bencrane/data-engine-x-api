"""MCP tool-to-table persistence mapping.

Maps MCP tool names to dedicated table write functions following the same
registry pattern as persistence_routing.py. Each extractor handles the
MCP response shape challenge (structured JSON vs narrative text).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable

from app.services.enigma_brand_discoveries import upsert_enigma_brand_discoveries
from app.services.enigma_location_enrichments import upsert_enigma_location_enrichments

logger = logging.getLogger(__name__)


@dataclass
class McpPersistenceEntry:
    """Maps an MCP tool to its persistence target."""

    table_name: str
    extract_and_write: Callable[..., dict[str, Any]]


# ---------------------------------------------------------------------------
# Field mapping helpers
# ---------------------------------------------------------------------------
# MCP segment/search responses use Enigma ontology field names which differ
# from our upsert service's expected field names. These helpers normalize.
#
# Ontology field names (from ENIGMA_MCP_REFERENCE.md Section 2):
#   brand:   brand_id (int), name, standardized_name
#   location: operating_location_id (int), name, operating_status, entity_ref__brand_id
#   address:  full_address, street_address1, city, state, zip
#
# The MCP text response is JSON-parsed by call_tool(); the exact keys depend
# on how the MCP server serializes the ontology. We try multiple variants.


def _extract_str(obj: dict, *keys: str) -> str | None:
    """Return the first non-empty string value found among keys."""
    for k in keys:
        val = obj.get(k)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return None


def _extract_id(obj: dict, *keys: str) -> str | None:
    """Return the first non-None value found among keys, coerced to str."""
    for k in keys:
        val = obj.get(k)
        if val is not None:
            return str(val).strip() or None
    return None


def _slugify(text: str) -> str:
    """Simple slug for synthetic IDs."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80]


# ---------------------------------------------------------------------------
# Brand mapping: MCP response → upsert_enigma_brand_discoveries shape
# ---------------------------------------------------------------------------

def _map_brand(item: dict) -> dict[str, Any]:
    """Map a single MCP brand result to the upsert service's expected dict."""
    brand: dict[str, Any] = {}

    # Required: enigma_brand_id
    bid = _extract_id(item, "enigma_brand_id", "brand_id", "id")
    if bid:
        brand["enigma_brand_id"] = bid

    brand["brand_name"] = _extract_str(item, "brand_name", "name", "standardized_name")
    brand["brand_website"] = _extract_str(item, "brand_website", "website", "standardized_website")

    # Numeric fields — pass through if present
    for field in ("location_count", "annual_card_revenue", "annual_card_revenue_yoy_growth",
                  "annual_avg_daily_customers", "annual_transaction_count"):
        val = item.get(field)
        if isinstance(val, (int, float)):
            brand[field] = val

    # Industries — may be a list or comma-separated string
    industries = item.get("industries")
    if isinstance(industries, list):
        brand["industries"] = industries
    elif isinstance(industries, str) and industries.strip():
        brand["industries"] = [industries.strip()]

    monthly = item.get("monthly_revenue")
    if isinstance(monthly, list):
        brand["monthly_revenue"] = monthly

    return brand


# ---------------------------------------------------------------------------
# Location mapping: MCP response → upsert_enigma_location_enrichments shape
# ---------------------------------------------------------------------------

def _map_location(item: dict) -> dict[str, Any]:
    """Map a single MCP location result to the upsert service's expected dict."""
    loc: dict[str, Any] = {}

    lid = _extract_id(item, "enigma_location_id", "operating_location_id", "location_id", "id")
    if lid:
        loc["enigma_location_id"] = lid

    loc["location_name"] = _extract_str(item, "location_name", "name", "standardized_name")
    loc["full_address"] = _extract_str(item, "full_address", "standardized_full_address")
    loc["street"] = _extract_str(item, "street", "street_address1")
    loc["city"] = _extract_str(item, "city")
    loc["state"] = _extract_str(item, "state")
    loc["postal_code"] = _extract_str(item, "postal_code", "zip")
    loc["operating_status"] = _extract_str(item, "operating_status")
    loc["phone"] = _extract_str(item, "phone", "phone_number")
    loc["website"] = _extract_str(item, "website")

    for field in ("annual_card_revenue", "annual_card_revenue_yoy_growth",
                  "annual_avg_daily_customers", "annual_transaction_count",
                  "competitive_rank", "competitive_rank_total",
                  "review_count", "review_avg_rating"):
        val = item.get(field)
        if isinstance(val, (int, float)):
            loc[field] = val

    contacts = item.get("contacts")
    if isinstance(contacts, list) and contacts:
        loc["contacts"] = contacts

    return loc


# ---------------------------------------------------------------------------
# Extractor functions
# ---------------------------------------------------------------------------

def _write_brands_segment(
    *,
    org_id: str,
    company_id: str | None,
    tool_name: str,
    parsed_result: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Persist generate_brands_segment results to enigma_brand_discoveries."""
    try:
        if not isinstance(parsed_result, list) or not parsed_result:
            return {"status": "skipped", "reason": "non_structured_or_empty_result",
                    "table": "enigma_brand_discoveries"}

        discovery_prompt = arguments.get("industry_description", "mcp_segment_discovery")
        states = arguments.get("states")
        geography_state = states[0] if isinstance(states, list) and states else (
            states if isinstance(states, str) else None
        )
        cities = arguments.get("cities")
        geography_city = cities[0] if isinstance(cities, list) and cities else (
            cities if isinstance(cities, str) else None
        )

        mapped_brands = [_map_brand(item) for item in parsed_result if isinstance(item, dict)]
        mapped_brands = [b for b in mapped_brands if b.get("enigma_brand_id")]

        if not mapped_brands:
            return {"status": "skipped", "reason": "no_brands_with_valid_id",
                    "table": "enigma_brand_discoveries"}

        result = upsert_enigma_brand_discoveries(
            org_id=org_id,
            company_id=company_id,
            discovery_prompt=discovery_prompt,
            geography_state=geography_state,
            geography_city=geography_city,
            brands=mapped_brands,
            discovered_by_operation_id=f"mcp.{tool_name}",
        )
        return {"status": "succeeded", "table": "enigma_brand_discoveries", "count": len(result)}
    except Exception as exc:
        logger.exception("MCP persistence failed for %s", tool_name)
        return {"status": "failed", "error": str(exc), "table": "enigma_brand_discoveries"}


def _write_locations_segment(
    *,
    org_id: str,
    company_id: str | None,
    tool_name: str,
    parsed_result: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Persist generate_locations_segment results to enigma_location_enrichments.

    Design decision: locations from segment discovery may not have a single parent
    brand. If the MCP response includes a brand_id per location, we use it.
    Otherwise we use a synthetic brand ID derived from the industry description
    so all locations from the same segment query share one parent key.
    """
    try:
        if not isinstance(parsed_result, list) or not parsed_result:
            return {"status": "skipped", "reason": "non_structured_or_empty_result",
                    "table": "enigma_location_enrichments"}

        industry_desc = arguments.get("industry_description", "unknown_segment")
        fallback_brand_id = f"mcp_segment_{_slugify(industry_desc)}"

        mapped_locations = [_map_location(item) for item in parsed_result if isinstance(item, dict)]
        mapped_locations = [loc for loc in mapped_locations if loc.get("enigma_location_id")]

        if not mapped_locations:
            return {"status": "skipped", "reason": "no_locations_with_valid_id",
                    "table": "enigma_location_enrichments"}

        # Group by brand_id if present, else use fallback
        brand_groups: dict[str, list[dict]] = {}
        for loc in mapped_locations:
            bid = _extract_id(loc, "entity_ref__brand_id", "brand_id") or fallback_brand_id
            brand_groups.setdefault(bid, []).append(loc)

        total_written = 0
        for brand_id, locs in brand_groups.items():
            result = upsert_enigma_location_enrichments(
                org_id=org_id,
                company_id=company_id,
                enigma_brand_id=brand_id,
                locations=locs,
                enriched_by_operation_id=f"mcp.{tool_name}",
            )
            total_written += len(result)

        return {"status": "succeeded", "table": "enigma_location_enrichments",
                "count": total_written}
    except Exception as exc:
        logger.exception("MCP persistence failed for %s", tool_name)
        return {"status": "failed", "error": str(exc), "table": "enigma_location_enrichments"}


def _write_search_business(
    *,
    org_id: str,
    company_id: str | None,
    tool_name: str,
    parsed_result: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Persist search_business results to enigma_brand_discoveries."""
    try:
        # search_business may return a dict (single brand) or a list
        items = parsed_result if isinstance(parsed_result, list) else [parsed_result]
        items = [i for i in items if isinstance(i, dict)]
        if not items:
            return {"status": "skipped", "reason": "non_structured_or_empty_result",
                    "table": "enigma_brand_discoveries"}

        discovery_prompt = arguments.get("query", "mcp_search_business")
        mapped_brands = [_map_brand(item) for item in items]
        mapped_brands = [b for b in mapped_brands if b.get("enigma_brand_id")]

        if not mapped_brands:
            return {"status": "skipped", "reason": "no_brands_with_valid_id",
                    "table": "enigma_brand_discoveries"}

        result = upsert_enigma_brand_discoveries(
            org_id=org_id,
            company_id=company_id,
            discovery_prompt=discovery_prompt,
            brands=mapped_brands,
            discovered_by_operation_id=f"mcp.{tool_name}",
        )
        return {"status": "succeeded", "table": "enigma_brand_discoveries", "count": len(result)}
    except Exception as exc:
        logger.exception("MCP persistence failed for %s", tool_name)
        return {"status": "failed", "error": str(exc), "table": "enigma_brand_discoveries"}


def _write_brand_locations(
    *,
    org_id: str,
    company_id: str | None,
    tool_name: str,
    parsed_result: Any,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Persist get_brand_locations results to enigma_location_enrichments."""
    try:
        items = parsed_result if isinstance(parsed_result, list) else [parsed_result]
        items = [i for i in items if isinstance(i, dict)]
        if not items:
            return {"status": "skipped", "reason": "non_structured_or_empty_result",
                    "table": "enigma_location_enrichments"}

        enigma_brand_id = str(arguments.get("brand_id", ""))
        if not enigma_brand_id:
            return {"status": "skipped", "reason": "missing_brand_id_in_arguments",
                    "table": "enigma_location_enrichments"}

        mapped_locations = [_map_location(item) for item in items]
        mapped_locations = [loc for loc in mapped_locations if loc.get("enigma_location_id")]

        if not mapped_locations:
            return {"status": "skipped", "reason": "no_locations_with_valid_id",
                    "table": "enigma_location_enrichments"}

        result = upsert_enigma_location_enrichments(
            org_id=org_id,
            company_id=company_id,
            enigma_brand_id=enigma_brand_id,
            locations=mapped_locations,
            enriched_by_operation_id=f"mcp.{tool_name}",
        )
        return {"status": "succeeded", "table": "enigma_location_enrichments",
                "count": len(result)}
    except Exception as exc:
        logger.exception("MCP persistence failed for %s", tool_name)
        return {"status": "failed", "error": str(exc), "table": "enigma_location_enrichments"}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

MCP_PERSISTENCE_REGISTRY: dict[str, McpPersistenceEntry] = {
    "generate_brands_segment": McpPersistenceEntry(
        table_name="enigma_brand_discoveries",
        extract_and_write=_write_brands_segment,
    ),
    "generate_locations_segment": McpPersistenceEntry(
        table_name="enigma_location_enrichments",
        extract_and_write=_write_locations_segment,
    ),
    "search_business": McpPersistenceEntry(
        table_name="enigma_brand_discoveries",
        extract_and_write=_write_search_business,
    ),
    "get_brand_locations": McpPersistenceEntry(
        table_name="enigma_location_enrichments",
        extract_and_write=_write_brand_locations,
    ),
}


# ---------------------------------------------------------------------------
# Top-level persistence function
# ---------------------------------------------------------------------------


def persist_mcp_result(
    *,
    org_id: str,
    company_id: str | None,
    tool_name: str,
    parsed_result: Any | None,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Persist MCP tool results to the appropriate dedicated table.

    Returns a persistence status dict with keys: status, table, count/reason/error.
    """
    if parsed_result is None:
        return {"status": "skipped", "reason": "narrative_text_response"}

    entry = MCP_PERSISTENCE_REGISTRY.get(tool_name)
    if entry is None:
        return {"status": "skipped", "reason": "no_registry_entry"}

    return entry.extract_and_write(
        org_id=org_id,
        company_id=company_id,
        tool_name=tool_name,
        parsed_result=parsed_result,
        arguments=arguments,
    )
