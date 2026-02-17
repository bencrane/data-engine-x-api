from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, NAMESPACE_URL, uuid5

from app.database import get_supabase_client


class EntityStateVersionError(ValueError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_uuid_str(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_email(value: Any) -> str | None:
    text = _normalize_text(value)
    return text.lower() if text else None


def _normalize_linkedin_url(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    return text.rstrip("/").lower()


def _normalize_domain(value: Any) -> str | None:
    text = _normalize_text(value)
    if not text:
        return None
    candidate = text.lower()
    if "://" in candidate:
        candidate = urlparse(candidate).netloc or candidate
    candidate = candidate.split("/")[0].strip()
    if candidate.startswith("www."):
        candidate = candidate[4:]
    return candidate or None


def _normalize_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _normalize_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (float, int)):
        return float(value)
    text = _normalize_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _extract_str_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        cleaned = [item.strip() for item in value if isinstance(item, str) and item.strip()]
        return cleaned or None
    return None


def _merge_non_null(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(existing or {})
    for key, value in (incoming or {}).items():
        if value is not None:
            merged[key] = value
    return merged


def _merge_str_lists(existing: list[str] | None, incoming: list[str] | None) -> list[str] | None:
    merged: list[str] = []
    for value in (existing or []) + (incoming or []):
        if value not in merged:
            merged.append(value)
    return merged or None


def _stable_identity_fallback(prefix: str, org_id: str, canonical_fields: dict[str, Any]) -> str:
    identity_payload = json.dumps(canonical_fields, sort_keys=True, separators=(",", ":"))
    return str(uuid5(NAMESPACE_URL, f"{prefix}:{org_id}:fallback:{identity_payload}"))


def _company_fields_from_context(canonical_fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "canonical_domain": _normalize_domain(
            canonical_fields.get("canonical_domain")
            or canonical_fields.get("company_domain")
            or canonical_fields.get("domain")
        ),
        "canonical_name": _normalize_text(
            canonical_fields.get("canonical_name")
            or canonical_fields.get("company_name")
            or canonical_fields.get("name")
        ),
        "linkedin_url": _normalize_linkedin_url(
            canonical_fields.get("linkedin_url")
            or canonical_fields.get("company_linkedin_url")
        ),
        "industry": _normalize_text(
            canonical_fields.get("industry")
            or canonical_fields.get("industry_primary")
        ),
        "employee_count": _normalize_int(canonical_fields.get("employee_count")),
        "employee_range": _normalize_text(canonical_fields.get("employee_range")),
        "revenue_band": _normalize_text(
            canonical_fields.get("revenue_band")
            or canonical_fields.get("annual_revenue_range")
        ),
        "hq_country": _normalize_text(
            canonical_fields.get("hq_country")
            or canonical_fields.get("hq_country_code")
        ),
        "description": _normalize_text(
            canonical_fields.get("description")
            or canonical_fields.get("description_raw")
        ),
        "enrichment_confidence": _normalize_float(
            canonical_fields.get("enrichment_confidence")
            or canonical_fields.get("confidence")
        ),
        "source_providers": _extract_str_list(canonical_fields.get("source_providers")),
    }


def _person_fields_from_context(canonical_fields: dict[str, Any]) -> dict[str, Any]:
    verification = canonical_fields.get("verification")
    verification_status = None
    if isinstance(verification, dict):
        verification_status = _normalize_text(verification.get("status"))

    return {
        "full_name": _normalize_text(canonical_fields.get("full_name")),
        "first_name": _normalize_text(canonical_fields.get("first_name")),
        "last_name": _normalize_text(canonical_fields.get("last_name")),
        "linkedin_url": _normalize_linkedin_url(canonical_fields.get("linkedin_url")),
        "title": _normalize_text(
            canonical_fields.get("title")
            or canonical_fields.get("current_title")
            or canonical_fields.get("headline")
        ),
        "seniority": _normalize_text(canonical_fields.get("seniority")),
        "department": _normalize_text(canonical_fields.get("department")),
        "work_email": _normalize_email(
            canonical_fields.get("work_email")
            or canonical_fields.get("email")
        ),
        "email_status": _normalize_text(
            canonical_fields.get("email_status")
            or verification_status
        ),
        "phone_e164": _normalize_text(
            canonical_fields.get("phone_e164")
            or canonical_fields.get("mobile_phone")
        ),
        "contact_confidence": _normalize_float(
            canonical_fields.get("contact_confidence")
            or canonical_fields.get("confidence")
        ),
    }


def _lookup_company_by_natural_key(org_id: str, canonical_domain: str | None) -> dict[str, Any] | None:
    if not canonical_domain:
        return None
    client = get_supabase_client()
    result = (
        client.table("company_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("canonical_domain", canonical_domain)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _lookup_person_by_natural_key(
    org_id: str,
    linkedin_url: str | None,
    work_email: str | None,
) -> dict[str, Any] | None:
    client = get_supabase_client()
    if linkedin_url:
        linkedin_result = (
            client.table("person_entities")
            .select("*")
            .eq("org_id", org_id)
            .eq("linkedin_url", linkedin_url)
            .limit(1)
            .execute()
        )
        if linkedin_result.data:
            return linkedin_result.data[0]
    if work_email:
        email_result = (
            client.table("person_entities")
            .select("*")
            .eq("org_id", org_id)
            .eq("work_email", work_email)
            .limit(1)
            .execute()
        )
        if email_result.data:
            return email_result.data[0]
    return None


def _load_company_by_id(org_id: str, entity_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("company_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("entity_id", entity_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _load_person_by_id(org_id: str, entity_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("person_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("entity_id", entity_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_company_entity(
    *,
    org_id: str,
    company_id: str | None,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
    last_operation_id: str | None = None,
    last_run_id: str | None = None,
    incoming_record_version: int | None = None,
) -> dict[str, Any]:
    normalized_fields = _company_fields_from_context(canonical_fields)
    explicit_entity_id = _as_uuid_str(entity_id)
    company_uuid = _as_uuid_str(company_id)
    run_uuid = _as_uuid_str(last_run_id)

    existing: dict[str, Any] | None = None
    resolved_entity_id = explicit_entity_id
    if resolved_entity_id:
        existing = _load_company_by_id(org_id, resolved_entity_id)
    if not existing:
        existing = _lookup_company_by_natural_key(org_id, normalized_fields.get("canonical_domain"))
        if existing:
            resolved_entity_id = existing["entity_id"]

    if not resolved_entity_id:
        canonical_domain = normalized_fields.get("canonical_domain")
        linkedin_url = normalized_fields.get("linkedin_url")
        canonical_name = normalized_fields.get("canonical_name")
        if canonical_domain:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"company:{org_id}:domain:{canonical_domain}"))
        elif linkedin_url:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"company:{org_id}:linkedin:{linkedin_url}"))
        elif canonical_name:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"company:{org_id}:name:{canonical_name.lower()}"))
        else:
            resolved_entity_id = _stable_identity_fallback("company", org_id, canonical_fields)

    if existing is None:
        existing = _load_company_by_id(org_id, resolved_entity_id)

    existing_version = int(existing.get("record_version", 0)) if existing else 0
    next_version = incoming_record_version if incoming_record_version is not None else existing_version + 1
    if next_version <= existing_version:
        raise EntityStateVersionError(
            f"Incoming record_version ({next_version}) must be greater than existing ({existing_version})"
        )

    merged_payload = _merge_non_null(existing.get("canonical_payload") if existing else {}, canonical_fields)
    merged_providers = _merge_str_lists(
        existing.get("source_providers") if existing else None,
        normalized_fields.get("source_providers"),
    )

    row_to_write = {
        "org_id": org_id,
        "company_id": company_uuid if company_uuid is not None else (existing.get("company_id") if existing else None),
        "entity_id": resolved_entity_id,
        "canonical_domain": normalized_fields["canonical_domain"]
        if normalized_fields["canonical_domain"] is not None
        else (existing.get("canonical_domain") if existing else None),
        "canonical_name": normalized_fields["canonical_name"]
        if normalized_fields["canonical_name"] is not None
        else (existing.get("canonical_name") if existing else None),
        "linkedin_url": normalized_fields["linkedin_url"]
        if normalized_fields["linkedin_url"] is not None
        else (existing.get("linkedin_url") if existing else None),
        "industry": normalized_fields["industry"]
        if normalized_fields["industry"] is not None
        else (existing.get("industry") if existing else None),
        "employee_count": normalized_fields["employee_count"]
        if normalized_fields["employee_count"] is not None
        else (existing.get("employee_count") if existing else None),
        "employee_range": normalized_fields["employee_range"]
        if normalized_fields["employee_range"] is not None
        else (existing.get("employee_range") if existing else None),
        "revenue_band": normalized_fields["revenue_band"]
        if normalized_fields["revenue_band"] is not None
        else (existing.get("revenue_band") if existing else None),
        "hq_country": normalized_fields["hq_country"]
        if normalized_fields["hq_country"] is not None
        else (existing.get("hq_country") if existing else None),
        "description": normalized_fields["description"]
        if normalized_fields["description"] is not None
        else (existing.get("description") if existing else None),
        "enrichment_confidence": normalized_fields["enrichment_confidence"]
        if normalized_fields["enrichment_confidence"] is not None
        else (existing.get("enrichment_confidence") if existing else None),
        "last_enriched_at": _utc_now_iso(),
        "last_operation_id": _normalize_text(last_operation_id)
        if _normalize_text(last_operation_id) is not None
        else (existing.get("last_operation_id") if existing else None),
        "last_run_id": run_uuid if run_uuid is not None else (existing.get("last_run_id") if existing else None),
        "source_providers": merged_providers,
        "record_version": next_version,
        "canonical_payload": merged_payload,
    }

    client = get_supabase_client()
    if existing:
        result = (
            client.table("company_entities")
            .update(row_to_write)
            .eq("org_id", org_id)
            .eq("entity_id", resolved_entity_id)
            .eq("record_version", existing_version)
            .execute()
        )
        if not result.data:
            raise EntityStateVersionError("Version conflict during company entity update")
        return result.data[0]

    result = client.table("company_entities").insert(row_to_write).execute()
    return result.data[0]


def upsert_person_entity(
    *,
    org_id: str,
    company_id: str | None,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
    last_operation_id: str | None = None,
    last_run_id: str | None = None,
    incoming_record_version: int | None = None,
) -> dict[str, Any]:
    normalized_fields = _person_fields_from_context(canonical_fields)
    explicit_entity_id = _as_uuid_str(entity_id)
    company_uuid = _as_uuid_str(company_id)
    run_uuid = _as_uuid_str(last_run_id)

    existing: dict[str, Any] | None = None
    resolved_entity_id = explicit_entity_id
    if resolved_entity_id:
        existing = _load_person_by_id(org_id, resolved_entity_id)
    if not existing:
        existing = _lookup_person_by_natural_key(
            org_id,
            normalized_fields.get("linkedin_url"),
            normalized_fields.get("work_email"),
        )
        if existing:
            resolved_entity_id = existing["entity_id"]

    if not resolved_entity_id:
        linkedin_url = normalized_fields.get("linkedin_url")
        work_email = normalized_fields.get("work_email")
        full_name = normalized_fields.get("full_name")
        if linkedin_url:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"person:{org_id}:linkedin:{linkedin_url}"))
        elif work_email:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"person:{org_id}:work_email:{work_email}"))
        elif full_name:
            resolved_entity_id = str(uuid5(NAMESPACE_URL, f"person:{org_id}:full_name:{full_name.lower()}"))
        else:
            resolved_entity_id = _stable_identity_fallback("person", org_id, canonical_fields)

    if existing is None:
        existing = _load_person_by_id(org_id, resolved_entity_id)

    existing_version = int(existing.get("record_version", 0)) if existing else 0
    next_version = incoming_record_version if incoming_record_version is not None else existing_version + 1
    if next_version <= existing_version:
        raise EntityStateVersionError(
            f"Incoming record_version ({next_version}) must be greater than existing ({existing_version})"
        )

    merged_payload = _merge_non_null(existing.get("canonical_payload") if existing else {}, canonical_fields)

    row_to_write = {
        "org_id": org_id,
        "company_id": company_uuid if company_uuid is not None else (existing.get("company_id") if existing else None),
        "entity_id": resolved_entity_id,
        "full_name": normalized_fields["full_name"]
        if normalized_fields["full_name"] is not None
        else (existing.get("full_name") if existing else None),
        "first_name": normalized_fields["first_name"]
        if normalized_fields["first_name"] is not None
        else (existing.get("first_name") if existing else None),
        "last_name": normalized_fields["last_name"]
        if normalized_fields["last_name"] is not None
        else (existing.get("last_name") if existing else None),
        "linkedin_url": normalized_fields["linkedin_url"]
        if normalized_fields["linkedin_url"] is not None
        else (existing.get("linkedin_url") if existing else None),
        "title": normalized_fields["title"]
        if normalized_fields["title"] is not None
        else (existing.get("title") if existing else None),
        "seniority": normalized_fields["seniority"]
        if normalized_fields["seniority"] is not None
        else (existing.get("seniority") if existing else None),
        "department": normalized_fields["department"]
        if normalized_fields["department"] is not None
        else (existing.get("department") if existing else None),
        "work_email": normalized_fields["work_email"]
        if normalized_fields["work_email"] is not None
        else (existing.get("work_email") if existing else None),
        "email_status": normalized_fields["email_status"]
        if normalized_fields["email_status"] is not None
        else (existing.get("email_status") if existing else None),
        "phone_e164": normalized_fields["phone_e164"]
        if normalized_fields["phone_e164"] is not None
        else (existing.get("phone_e164") if existing else None),
        "contact_confidence": normalized_fields["contact_confidence"]
        if normalized_fields["contact_confidence"] is not None
        else (existing.get("contact_confidence") if existing else None),
        "last_enriched_at": _utc_now_iso(),
        "last_operation_id": _normalize_text(last_operation_id)
        if _normalize_text(last_operation_id) is not None
        else (existing.get("last_operation_id") if existing else None),
        "last_run_id": run_uuid if run_uuid is not None else (existing.get("last_run_id") if existing else None),
        "record_version": next_version,
        "canonical_payload": merged_payload,
    }

    client = get_supabase_client()
    if existing:
        result = (
            client.table("person_entities")
            .update(row_to_write)
            .eq("org_id", org_id)
            .eq("entity_id", resolved_entity_id)
            .eq("record_version", existing_version)
            .execute()
        )
        if not result.data:
            raise EntityStateVersionError("Version conflict during person entity update")
        return result.data[0]

    result = client.table("person_entities").insert(row_to_write).execute()
    return result.data[0]
