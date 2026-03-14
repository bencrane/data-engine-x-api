"""External ingest — maps external payloads to canonical fields and bulk-upserts entities."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

from app.database import get_supabase_client
from app.services.entity_relationships import record_entity_relationship
from app.services.entity_state import (
    EntityStateVersionError,
    upsert_company_entity,
    upsert_person_entity,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Field rename maps: Clay field name -> canonical field name
# ---------------------------------------------------------------------------

_COMPANY_FIELD_RENAMES: dict[str, str] = {
    "domain": "canonical_domain",
    "name": "canonical_name",
    "linkedin_company_id": "company_linkedin_id",
    "size": "employee_range",
    "country": "hq_country",
    "annual_revenue": "revenue_band",
}

_PERSON_FIELD_RENAMES: dict[str, str] = {
    "url": "linkedin_url",
    "name": "full_name",
    "latest_experience_title": "title",
    "domain": "current_company_domain",
    "latest_experience_company": "current_company_name",
}


def map_company_payload(raw: dict, source_provider: str) -> dict:
    """Translate a raw external company payload into canonical field names.

    All unmapped fields are preserved in the returned dict so they end up
    in ``canonical_payload`` via ``_merge_non_null``.
    """
    mapped: dict[str, Any] = {}
    for key, value in raw.items():
        canonical_key = _COMPANY_FIELD_RENAMES.get(key, key)
        mapped[canonical_key] = value

    # Cast linkedin_company_id -> string
    if "company_linkedin_id" in mapped and mapped["company_linkedin_id"] is not None:
        mapped["company_linkedin_id"] = str(mapped["company_linkedin_id"])

    # Inject source_providers
    mapped["source_providers"] = [source_provider]

    return mapped


def map_person_payload(raw: dict, source_provider: str) -> dict:
    """Translate a raw external person payload into canonical field names.

    All unmapped fields are preserved in the returned dict so they end up
    in ``canonical_payload`` via ``_merge_non_null``.
    """
    mapped: dict[str, Any] = {}
    for key, value in raw.items():
        canonical_key = _PERSON_FIELD_RENAMES.get(key, key)
        mapped[canonical_key] = value

    # Inject source_providers
    mapped["source_providers"] = [source_provider]

    return mapped


# ---------------------------------------------------------------------------
# Domain normalization (local copy to avoid coupling to entity_state internals)
# ---------------------------------------------------------------------------

def _normalize_domain(value: str) -> str:
    candidate = value.strip().lower()
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    netloc = parsed.netloc or parsed.path
    normalized = netloc.strip().lower()
    if normalized.startswith("www."):
        normalized = normalized[4:]
    return normalized.rstrip("/")


# ---------------------------------------------------------------------------
# Bulk ingest service
# ---------------------------------------------------------------------------

def ingest_entities(
    *,
    org_id: str,
    company_id: str | None,
    entity_type: str,
    source_provider: str,
    payloads: list[dict],
) -> dict:
    """Ingest a batch of external entity payloads.

    Returns a summary dict with counts of created/updated/skipped/errored records.
    """
    created = 0
    updated = 0
    skipped = 0
    errors = 0
    error_details: list[dict[str, Any]] = []

    # Person-only relationship counters
    relationships_created = 0
    relationships_matched = 0
    relationships_unmatched = 0
    relationships_skipped_no_identifier = 0

    operation_id = f"external.ingest.{source_provider}"

    for i, raw_payload in enumerate(payloads):
        try:
            if entity_type == "company":
                mapped = map_company_payload(raw_payload, source_provider)
                record = upsert_company_entity(
                    org_id=org_id,
                    company_id=company_id,
                    canonical_fields=mapped,
                    last_operation_id=operation_id,
                    last_run_id=None,
                )
            else:
                mapped = map_person_payload(raw_payload, source_provider)
                record = upsert_person_entity(
                    org_id=org_id,
                    company_id=company_id,
                    canonical_fields=mapped,
                    last_operation_id=operation_id,
                    last_run_id=None,
                )

            if record.get("record_version", 1) == 1:
                created += 1
            else:
                updated += 1

            # Person: create works_at edge
            if entity_type == "person":
                company_domain_raw = mapped.get("current_company_domain")
                if company_domain_raw and isinstance(company_domain_raw, str) and company_domain_raw.strip():
                    # Determine source_identifier
                    source_identifier = mapped.get("linkedin_url") or mapped.get("work_email")
                    if not source_identifier or not isinstance(source_identifier, str) or not source_identifier.strip():
                        relationships_skipped_no_identifier += 1
                    else:
                        source_identifier = source_identifier.strip()
                        normalized_domain = _normalize_domain(company_domain_raw)

                        # Try to match company entity
                        target_entity_id = _resolve_company_by_domain(org_id, normalized_domain)

                        record_entity_relationship(
                            org_id=org_id,
                            source_entity_type="person",
                            source_entity_id=record["entity_id"],
                            source_identifier=source_identifier,
                            relationship="works_at",
                            target_entity_type="company",
                            target_entity_id=target_entity_id,
                            target_identifier=normalized_domain,
                            metadata={"source": "external_ingest", "source_provider": source_provider},
                            source_operation_id=operation_id,
                        )
                        relationships_created += 1
                        if target_entity_id:
                            relationships_matched += 1
                        else:
                            relationships_unmatched += 1

        except EntityStateVersionError:
            skipped += 1
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.exception(
                "External ingest failed for payload at index %d",
                i,
                extra={"org_id": org_id, "source_provider": source_provider, "index": i},
            )
            if len(error_details) < 10:
                error_details.append({"index": i, "error": str(exc)})

    summary: dict[str, Any] = {
        "entity_type": entity_type,
        "source_provider": source_provider,
        "total_submitted": len(payloads),
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "error_details": error_details,
    }

    if entity_type == "person":
        summary["relationships_created"] = relationships_created
        summary["relationships_matched"] = relationships_matched
        summary["relationships_unmatched"] = relationships_unmatched
        summary["relationships_skipped_no_identifier"] = relationships_skipped_no_identifier

    return summary


def _resolve_company_by_domain(org_id: str, canonical_domain: str) -> str | None:
    """Look up a company entity by canonical_domain within the org. Returns entity_id or None."""
    client = get_supabase_client()
    result = (
        client.table("company_entities")
        .select("entity_id")
        .eq("org_id", org_id)
        .eq("canonical_domain", canonical_domain)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["entity_id"]
    return None
