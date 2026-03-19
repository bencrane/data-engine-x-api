from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

from app.auth.models import AuthContext
from app.services.company_ads import upsert_company_ads
from app.services.company_customers import upsert_company_customers
from app.services.company_intel_briefings import upsert_company_intel_briefing
from app.services.enigma_brand_discoveries import upsert_enigma_brand_discoveries
from app.services.entity_state import (
    EntityStateVersionError,
    upsert_company_entity,
    upsert_job_posting_entity,
    upsert_person_entity,
)
from app.services.gemini_icp_job_titles import upsert_gemini_icp_job_titles
from app.services.icp_job_titles import upsert_icp_job_titles
from app.services.person_intel_briefings import upsert_person_intel_briefing
from app.services.salesnav_prospects import upsert_salesnav_prospects

logger = logging.getLogger(__name__)


@dataclass
class DedicatedTableEntry:
    table_name: str
    extract_and_write: Callable  # (org_id, company_id, operation_id, output, input_data, run_id) -> dict


def _get_domain(output: dict, input_data: dict) -> str | None:
    return (
        output.get("company_domain")
        or output.get("domain")
        or output.get("canonical_domain")
        or input_data.get("company_domain")
        or input_data.get("domain")
    )


def _parse_raw(value: Any, fallback: dict) -> dict:
    """Parse a raw output value that may be a JSON string, dict, or absent."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return fallback


def _lookup_company_entity_id(*, org_id: str, company_domain: str) -> str | None:
    from app.database import get_supabase_client

    try:
        client = get_supabase_client()
        result = (
            client.schema("entities")
            .table("company_entities")
            .select("entity_id")
            .eq("org_id", org_id)
            .eq("canonical_domain", company_domain)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["entity_id"]
    except Exception as exc:
        logger.warning("Company entity lookup failed for domain %s: %s", company_domain, exc)
    return None


# ---------------------------------------------------------------------------
# Per-operation extract-and-write functions
# ---------------------------------------------------------------------------


def _write_icp_job_titles(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "icp_job_titles"
    company_domain = (
        output.get("domain") or output.get("company_domain") or input_data.get("company_domain")
    )
    if not company_domain:
        return {"status": "skipped", "reason": "missing_company_domain", "table": table}

    raw = _parse_raw(output.get("parallel_raw_response"), fallback=output)

    try:
        upsert_icp_job_titles(
            org_id=org_id,
            company_domain=company_domain,
            company_name=output.get("company_name"),
            company_description=output.get("company_description") or output.get("description"),
            raw_parallel_output=raw,
            parallel_run_id=output.get("parallel_run_id"),
            processor=output.get("processor"),
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("icp_job_titles write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_company_intel_briefing(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "company_intel_briefings"
    company_domain = (
        output.get("domain")
        or output.get("target_company_domain")
        or output.get("company_domain")
        or input_data.get("company_domain")
    )
    if not company_domain:
        return {"status": "skipped", "reason": "missing_company_domain", "table": table}

    raw = _parse_raw(
        output.get("parallel_raw_response") or output.get("raw_parallel_output"),
        fallback=output,
    )

    try:
        upsert_company_intel_briefing(
            org_id=org_id,
            company_domain=company_domain,
            company_name=output.get("company_name"),
            client_company_name=output.get("client_company_name"),
            client_company_domain=output.get("client_company_domain"),
            client_company_description=output.get("client_company_description"),
            raw_parallel_output=raw,
            parallel_run_id=output.get("parallel_run_id"),
            processor=output.get("processor"),
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("company_intel_briefings write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_person_intel_briefing(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "person_intel_briefings"
    person_full_name = (
        output.get("full_name")
        or output.get("person_full_name")
        or input_data.get("full_name")
        or input_data.get("person_full_name")
    )
    if not person_full_name:
        return {"status": "skipped", "reason": "missing_person_full_name", "table": table}

    raw = _parse_raw(
        output.get("parallel_raw_response") or output.get("raw_parallel_output"),
        fallback=output,
    )

    try:
        upsert_person_intel_briefing(
            org_id=org_id,
            person_full_name=person_full_name,
            person_linkedin_url=output.get("person_linkedin_url") or output.get("linkedin_url"),
            person_current_company_name=(
                output.get("person_current_company_name") or output.get("current_company_name")
            ),
            person_current_company_domain=(
                output.get("person_current_company_domain") or output.get("current_company_domain")
            ),
            person_current_job_title=(
                output.get("person_current_job_title")
                or output.get("current_title")
                or output.get("title")
            ),
            client_company_name=output.get("client_company_name"),
            client_company_description=output.get("client_company_description"),
            customer_company_name=output.get("customer_company_name"),
            customer_company_domain=output.get("customer_company_domain"),
            raw_parallel_output=raw,
            parallel_run_id=output.get("parallel_run_id"),
            processor=output.get("processor"),
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("person_intel_briefings write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_company_customers(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "company_customers"
    company_domain = _get_domain(output, input_data)
    if not company_domain:
        return {"status": "skipped", "reason": "missing_company_domain", "table": table}

    customers = output.get("customers") or []
    if not isinstance(customers, list) or not customers:
        return {"status": "skipped", "reason": "empty_customers_list", "table": table}

    company_entity_id = _lookup_company_entity_id(org_id=org_id, company_domain=company_domain)
    if not company_entity_id:
        return {"status": "skipped", "reason": "company_entity_not_found", "table": table}

    try:
        upsert_company_customers(
            org_id=org_id,
            company_entity_id=company_entity_id,
            company_domain=company_domain,
            customers=customers,
            discovered_by_operation_id=operation_id,
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("company_customers write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_gemini_icp_job_titles(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "gemini_icp_job_titles"
    company_domain = (
        output.get("domain")
        or output.get("company_domain")
        or input_data.get("company_domain")
    )
    if not company_domain:
        return {"status": "skipped", "reason": "missing_company_domain", "table": table}

    try:
        upsert_gemini_icp_job_titles(
            org_id=org_id,
            company_domain=company_domain,
            company_name=output.get("company_name"),
            company_description=output.get("company_description") or output.get("description"),
            inferred_product=output.get("inferred_product"),
            buyer_persona=output.get("buyer_persona"),
            titles=output.get("titles"),
            champion_titles=output.get("champion_titles"),
            evaluator_titles=output.get("evaluator_titles"),
            decision_maker_titles=output.get("decision_maker_titles"),
            raw_response=output,
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("gemini_icp_job_titles write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_company_ads_platform(
    *, org_id, company_id, operation_id, output, input_data, run_id, platform: str, ads_key: str
) -> dict:
    table = "company_ads"
    company_domain = _get_domain(output, input_data)
    if not company_domain:
        return {"status": "skipped", "reason": "missing_company_domain", "table": table}

    ads = output.get(ads_key) or []
    if not isinstance(ads, list) or not ads:
        return {"status": "skipped", "reason": f"empty_{ads_key}_list", "table": table}

    try:
        upsert_company_ads(
            org_id=org_id,
            company_domain=company_domain,
            platform=platform,
            ads=ads,
            discovered_by_operation_id=operation_id,
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("company_ads (%s) write failed: %s", platform, exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_company_ads_linkedin(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    return _write_company_ads_platform(
        org_id=org_id, company_id=company_id, operation_id=operation_id,
        output=output, input_data=input_data, run_id=run_id,
        platform="linkedin", ads_key="ads",
    )


def _write_company_ads_meta(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    return _write_company_ads_platform(
        org_id=org_id, company_id=company_id, operation_id=operation_id,
        output=output, input_data=input_data, run_id=run_id,
        platform="meta", ads_key="results",
    )


def _write_company_ads_google(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    return _write_company_ads_platform(
        org_id=org_id, company_id=company_id, operation_id=operation_id,
        output=output, input_data=input_data, run_id=run_id,
        platform="google", ads_key="ads",
    )


def _write_salesnav_prospects(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "salesnav_prospects"
    source_company_domain = _get_domain(output, input_data)
    if not source_company_domain:
        return {"status": "skipped", "reason": "missing_source_company_domain", "table": table}

    prospects = output.get("results") or []
    if not isinstance(prospects, list) or not prospects:
        return {"status": "skipped", "reason": "empty_results_list", "table": table}

    try:
        upsert_salesnav_prospects(
            org_id=org_id,
            source_company_domain=source_company_domain,
            source_company_name=output.get("company_name") or input_data.get("company_name"),
            source_salesnav_url=output.get("salesnav_url") or input_data.get("salesnav_url"),
            prospects=prospects,
            discovered_by_operation_id=operation_id,
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("salesnav_prospects write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


def _write_enigma_brand_discoveries(
    *, org_id, company_id, operation_id, output, input_data, run_id
) -> dict:
    table = "enigma_brand_discoveries"
    discovery_prompt = output.get("prompt") or input_data.get("prompt")
    if not discovery_prompt:
        return {"status": "skipped", "reason": "missing_discovery_prompt", "table": table}

    brands = output.get("brands") or []
    if not isinstance(brands, list) or not brands:
        return {"status": "skipped", "reason": "empty_brands_list", "table": table}

    try:
        upsert_enigma_brand_discoveries(
            org_id=org_id,
            company_id=company_id,
            discovery_prompt=discovery_prompt,
            brands=brands,
            discovered_by_operation_id=operation_id,
        )
        return {"status": "succeeded", "table": table}
    except Exception as exc:
        logger.error("enigma_brand_discoveries write failed: %s", exc)
        return {"status": "failed", "error": str(exc), "table": table}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

DEDICATED_TABLE_REGISTRY: dict[str, DedicatedTableEntry] = {
    "company.derive.icp_job_titles": DedicatedTableEntry(
        table_name="icp_job_titles",
        extract_and_write=_write_icp_job_titles,
    ),
    "company.derive.intel_briefing": DedicatedTableEntry(
        table_name="company_intel_briefings",
        extract_and_write=_write_company_intel_briefing,
    ),
    "person.derive.intel_briefing": DedicatedTableEntry(
        table_name="person_intel_briefings",
        extract_and_write=_write_person_intel_briefing,
    ),
    "company.research.discover_customers_gemini": DedicatedTableEntry(
        table_name="company_customers",
        extract_and_write=_write_company_customers,
    ),
    "company.research.lookup_customers_resolved": DedicatedTableEntry(
        table_name="company_customers",
        extract_and_write=_write_company_customers,
    ),
    "company.research.icp_job_titles_gemini": DedicatedTableEntry(
        table_name="gemini_icp_job_titles",
        extract_and_write=_write_gemini_icp_job_titles,
    ),
    "company.ads.search.linkedin": DedicatedTableEntry(
        table_name="company_ads",
        extract_and_write=_write_company_ads_linkedin,
    ),
    "company.ads.search.meta": DedicatedTableEntry(
        table_name="company_ads",
        extract_and_write=_write_company_ads_meta,
    ),
    "company.ads.search.google": DedicatedTableEntry(
        table_name="company_ads",
        extract_and_write=_write_company_ads_google,
    ),
    "person.search.sales_nav_url": DedicatedTableEntry(
        table_name="salesnav_prospects",
        extract_and_write=_write_salesnav_prospects,
    ),
    "company.search.enigma.brands": DedicatedTableEntry(
        table_name="enigma_brand_discoveries",
        extract_and_write=_write_enigma_brand_discoveries,
    ),
}


# ---------------------------------------------------------------------------
# Top-level function
# ---------------------------------------------------------------------------


def persist_standalone_result(
    *,
    auth: AuthContext,
    entity_type: str,
    operation_id: str,
    input_data: dict[str, Any],
    result: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Attempt entity upsert and dedicated table write for a standalone execute result.
    Returns a persistence status dict for inclusion in the response, or None if
    the result is not eligible for persistence (not found, no output, etc.).
    """
    if result.get("status") != "found":
        return None
    output = result.get("output")
    if not output or not isinstance(output, dict):
        return None

    # --- Entity upsert ---
    entity_upsert_result: dict[str, Any]
    try:
        upserted = None
        if entity_type == "company":
            upserted = upsert_company_entity(
                org_id=auth.org_id,
                company_id=auth.company_id,
                canonical_fields=output,
                last_operation_id=operation_id,
                last_run_id=result.get("run_id"),
            )
        elif entity_type == "person":
            upserted = upsert_person_entity(
                org_id=auth.org_id,
                company_id=auth.company_id,
                canonical_fields=output,
                last_operation_id=operation_id,
                last_run_id=result.get("run_id"),
            )
        elif entity_type == "job":
            upserted = upsert_job_posting_entity(
                org_id=auth.org_id,
                company_id=auth.company_id,
                canonical_fields=output,
                last_operation_id=operation_id,
                last_run_id=result.get("run_id"),
            )
        else:
            entity_upsert_result = {"status": "skipped", "reason": "unknown_entity_type"}

        if upserted is not None:
            entity_upsert_result = {"status": "succeeded", "entity_id": upserted.get("entity_id")}
        elif "entity_upsert_result" not in locals():
            entity_upsert_result = {"status": "skipped", "reason": "no_upsert_performed"}
    except EntityStateVersionError as exc:
        entity_upsert_result = {"status": "failed", "error": str(exc)}
    except Exception as exc:
        logger.error(
            "Entity upsert failed during standalone persist (operation=%s): %s", operation_id, exc
        )
        entity_upsert_result = {"status": "failed", "error": str(exc)}

    # --- Dedicated table write (independent of entity upsert outcome) ---
    entry = DEDICATED_TABLE_REGISTRY.get(operation_id)
    if entry:
        dedicated_table_result = entry.extract_and_write(
            org_id=auth.org_id,
            company_id=auth.company_id,
            operation_id=operation_id,
            output=output,
            input_data=input_data,
            run_id=result.get("run_id"),
        )
    else:
        dedicated_table_result = {"status": "skipped", "reason": "no_registry_entry"}

    return {
        "entity_upsert": entity_upsert_result,
        "dedicated_table": dedicated_table_result,
    }
