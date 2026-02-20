from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, NAMESPACE_URL, uuid5

from app.database import get_supabase_client

logger = logging.getLogger(__name__)


class EntityStateVersionError(ValueError):
    pass


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    parsed_value = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(parsed_value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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


def resolve_company_entity_id(
    *,
    org_id: str,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
) -> str:
    explicit_entity_id = _as_uuid_str(entity_id)
    if explicit_entity_id:
        return explicit_entity_id

    normalized_fields = _company_fields_from_context(canonical_fields)
    canonical_domain = normalized_fields.get("canonical_domain")
    linkedin_url = normalized_fields.get("linkedin_url")
    canonical_name = normalized_fields.get("canonical_name")
    if canonical_domain:
        return str(uuid5(NAMESPACE_URL, f"company:{org_id}:domain:{canonical_domain}"))
    if linkedin_url:
        return str(uuid5(NAMESPACE_URL, f"company:{org_id}:linkedin:{linkedin_url}"))
    if canonical_name:
        return str(uuid5(NAMESPACE_URL, f"company:{org_id}:name:{canonical_name.lower()}"))
    return _stable_identity_fallback("company", org_id, canonical_fields)


def resolve_person_entity_id(
    *,
    org_id: str,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
) -> str:
    explicit_entity_id = _as_uuid_str(entity_id)
    if explicit_entity_id:
        return explicit_entity_id

    normalized_fields = _person_fields_from_context(canonical_fields)
    linkedin_url = normalized_fields.get("linkedin_url")
    work_email = normalized_fields.get("work_email")
    full_name = normalized_fields.get("full_name")
    if linkedin_url:
        return str(uuid5(NAMESPACE_URL, f"person:{org_id}:linkedin:{linkedin_url}"))
    if work_email:
        return str(uuid5(NAMESPACE_URL, f"person:{org_id}:work_email:{work_email}"))
    if full_name:
        return str(uuid5(NAMESPACE_URL, f"person:{org_id}:full_name:{full_name.lower()}"))
    return _stable_identity_fallback("person", org_id, canonical_fields)


def resolve_job_posting_entity_id(
    *,
    org_id: str,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
) -> str:
    explicit_entity_id = _as_uuid_str(entity_id)
    if explicit_entity_id:
        return explicit_entity_id

    normalized_fields = _job_posting_fields_from_context(canonical_fields)
    theirstack_job_id = normalized_fields.get("theirstack_job_id")
    job_url = normalized_fields.get("job_url")
    job_title = normalized_fields.get("job_title")
    company_domain = normalized_fields.get("company_domain")
    if theirstack_job_id:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:theirstack:{theirstack_job_id}"))
    if job_url:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:url:{job_url}"))
    if job_title and company_domain:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:title_domain:{job_title.lower()}:{company_domain}"))
    return _stable_identity_fallback("job", org_id, canonical_fields)


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


def _job_posting_fields_from_context(canonical_fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "theirstack_job_id": _normalize_int(
            canonical_fields.get("theirstack_job_id")
            or canonical_fields.get("job_id")
        ),
        "job_url": _normalize_text(
            canonical_fields.get("job_url")
            or canonical_fields.get("url")
        ),
        "job_title": _normalize_text(canonical_fields.get("job_title")),
        "normalized_title": _normalize_text(canonical_fields.get("normalized_title")),
        "company_name": _normalize_text(canonical_fields.get("company_name")),
        "company_domain": _normalize_domain(
            canonical_fields.get("company_domain")
            or canonical_fields.get("domain")
        ),
        "location": _normalize_text(
            canonical_fields.get("location")
            or canonical_fields.get("short_location")
        ),
        "short_location": _normalize_text(canonical_fields.get("short_location")),
        "state_code": _normalize_text(canonical_fields.get("state_code")),
        "country_code": _normalize_text(canonical_fields.get("country_code")),
        "remote": canonical_fields.get("remote") if isinstance(canonical_fields.get("remote"), bool) else None,
        "hybrid": canonical_fields.get("hybrid") if isinstance(canonical_fields.get("hybrid"), bool) else None,
        "seniority": _normalize_text(canonical_fields.get("seniority")),
        "employment_statuses": _extract_str_list(canonical_fields.get("employment_statuses")),
        "date_posted": _normalize_text(canonical_fields.get("date_posted")),
        "discovered_at": _normalize_text(canonical_fields.get("discovered_at")),
        "salary_string": _normalize_text(canonical_fields.get("salary_string")),
        "min_annual_salary_usd": _normalize_float(canonical_fields.get("min_annual_salary_usd")),
        "max_annual_salary_usd": _normalize_float(canonical_fields.get("max_annual_salary_usd")),
        "description": _normalize_text(canonical_fields.get("description")),
        "technology_slugs": _extract_str_list(canonical_fields.get("technology_slugs")),
        "enrichment_confidence": _normalize_float(
            canonical_fields.get("enrichment_confidence")
            or canonical_fields.get("confidence")
        ),
        "source_providers": _extract_str_list(canonical_fields.get("source_providers")),
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


def _lookup_company_by_linkedin_url(org_id: str, linkedin_url: str | None) -> dict[str, Any] | None:
    if not linkedin_url:
        return None
    client = get_supabase_client()
    result = (
        client.table("company_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("linkedin_url", linkedin_url)
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


def _lookup_job_posting_by_theirstack_id(org_id: str, theirstack_job_id: int | None) -> dict[str, Any] | None:
    if theirstack_job_id is None:
        return None
    client = get_supabase_client()
    result = (
        client.table("job_posting_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("theirstack_job_id", theirstack_job_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _compute_age_hours(last_enriched_at: Any, *, now: datetime) -> float | None:
    enriched_at = _parse_iso_datetime(last_enriched_at)
    if enriched_at is None:
        return None
    return (now - enriched_at).total_seconds() / 3600


def check_entity_freshness(
    *,
    org_id: str,
    entity_type: str,
    identifiers: dict[str, Any] | None,
    max_age_hours: float,
) -> dict[str, Any]:
    normalized_identifiers = identifiers if isinstance(identifiers, dict) else {}
    now = datetime.now(timezone.utc)

    if entity_type == "person":
        linkedin_url = _normalize_linkedin_url(normalized_identifiers.get("linkedin_url"))
        work_email = _normalize_email(
            normalized_identifiers.get("work_email")
            or normalized_identifiers.get("email")
        )
        if not linkedin_url and not work_email:
            return {"fresh": False, "entity_id": None}
        entity = _lookup_person_by_natural_key(org_id, linkedin_url, work_email)
    elif entity_type == "job":
        theirstack_job_id = _normalize_int(
            normalized_identifiers.get("theirstack_job_id")
            or normalized_identifiers.get("job_id")
        )
        if not theirstack_job_id:
            return {"fresh": False, "entity_id": None}
        entity = _lookup_job_posting_by_theirstack_id(org_id, theirstack_job_id)
    else:
        canonical_domain = _normalize_domain(
            normalized_identifiers.get("company_domain")
            or normalized_identifiers.get("canonical_domain")
            or normalized_identifiers.get("domain")
        )
        company_linkedin_url = _normalize_linkedin_url(
            normalized_identifiers.get("company_linkedin_url")
            or normalized_identifiers.get("linkedin_url")
        )
        if not canonical_domain and not company_linkedin_url:
            return {"fresh": False, "entity_id": None}

        entity = _lookup_company_by_natural_key(org_id, canonical_domain)
        if entity is None and company_linkedin_url:
            entity = _lookup_company_by_linkedin_url(org_id, company_linkedin_url)

    if entity is None:
        return {"fresh": False, "entity_id": None}

    age_hours = _compute_age_hours(entity.get("last_enriched_at"), now=now)
    if age_hours is None or age_hours > max_age_hours:
        return {"fresh": False, "entity_id": None}

    return {
        "fresh": True,
        "entity_id": entity.get("entity_id"),
        "last_enriched_at": entity.get("last_enriched_at"),
        "age_hours": age_hours,
        "canonical_payload": entity.get("canonical_payload") if isinstance(entity.get("canonical_payload"), dict) else {},
    }


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


def _load_job_posting_by_id(org_id: str, entity_id: str) -> dict[str, Any] | None:
    client = get_supabase_client()
    result = (
        client.table("job_posting_entities")
        .select("*")
        .eq("org_id", org_id)
        .eq("entity_id", entity_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _capture_entity_snapshot(
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    record_version: int,
    canonical_payload: dict[str, Any],
    source_run_id: str | None,
) -> None:
    try:
        client = get_supabase_client()
        client.table("entity_snapshots").insert(
            {
                "org_id": org_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "record_version": record_version,
                "canonical_payload": canonical_payload,
                "source_run_id": source_run_id,
            }
        ).execute()
    except Exception:  # noqa: BLE001
        logger.exception(
            "Failed to capture entity snapshot",
            extra={
                "org_id": org_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "record_version": record_version,
                "source_run_id": source_run_id,
            },
        )


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
        resolved_entity_id = resolve_company_entity_id(
            org_id=org_id,
            canonical_fields=canonical_fields,
        )

    if existing is None:
        existing = _load_company_by_id(org_id, resolved_entity_id)

    existing_version = int(existing.get("record_version", 0)) if existing else 0
    next_version = incoming_record_version if incoming_record_version is not None else existing_version + 1
    if next_version <= existing_version:
        raise EntityStateVersionError(
            f"Incoming record_version ({next_version}) must be greater than existing ({existing_version})"
        )

    if existing:
        _capture_entity_snapshot(
            org_id=str(existing.get("org_id") or org_id),
            entity_type="company",
            entity_id=str(existing["entity_id"]),
            record_version=existing_version,
            canonical_payload=existing.get("canonical_payload")
            if isinstance(existing.get("canonical_payload"), dict)
            else {},
            source_run_id=run_uuid,
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
        resolved_entity_id = resolve_person_entity_id(
            org_id=org_id,
            canonical_fields=canonical_fields,
        )

    if existing is None:
        existing = _load_person_by_id(org_id, resolved_entity_id)

    existing_version = int(existing.get("record_version", 0)) if existing else 0
    next_version = incoming_record_version if incoming_record_version is not None else existing_version + 1
    if next_version <= existing_version:
        raise EntityStateVersionError(
            f"Incoming record_version ({next_version}) must be greater than existing ({existing_version})"
        )

    if existing:
        _capture_entity_snapshot(
            org_id=str(existing.get("org_id") or org_id),
            entity_type="person",
            entity_id=str(existing["entity_id"]),
            record_version=existing_version,
            canonical_payload=existing.get("canonical_payload")
            if isinstance(existing.get("canonical_payload"), dict)
            else {},
            source_run_id=run_uuid,
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


def upsert_job_posting_entity(
    *,
    org_id: str,
    company_id: str | None,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
    last_operation_id: str | None = None,
    last_run_id: str | None = None,
    incoming_record_version: int | None = None,
) -> dict[str, Any]:
    normalized_fields = _job_posting_fields_from_context(canonical_fields)
    explicit_entity_id = _as_uuid_str(entity_id)
    company_uuid = _as_uuid_str(company_id)
    run_uuid = _as_uuid_str(last_run_id)

    existing: dict[str, Any] | None = None
    resolved_entity_id = explicit_entity_id
    if resolved_entity_id:
        existing = _load_job_posting_by_id(org_id, resolved_entity_id)
    if not existing:
        existing = _lookup_job_posting_by_theirstack_id(org_id, normalized_fields.get("theirstack_job_id"))
        if existing:
            resolved_entity_id = existing["entity_id"]

    if not resolved_entity_id:
        resolved_entity_id = resolve_job_posting_entity_id(
            org_id=org_id,
            canonical_fields=canonical_fields,
        )

    if existing is None:
        existing = _load_job_posting_by_id(org_id, resolved_entity_id)

    existing_version = int(existing.get("record_version", 0)) if existing else 0
    next_version = incoming_record_version if incoming_record_version is not None else existing_version + 1
    if next_version <= existing_version:
        raise EntityStateVersionError(
            f"Incoming record_version ({next_version}) must be greater than existing ({existing_version})"
        )

    if existing:
        _capture_entity_snapshot(
            org_id=str(existing.get("org_id") or org_id),
            entity_type="job",
            entity_id=str(existing["entity_id"]),
            record_version=existing_version,
            canonical_payload=existing.get("canonical_payload")
            if isinstance(existing.get("canonical_payload"), dict)
            else {},
            source_run_id=run_uuid,
        )

    merged_payload = _merge_non_null(existing.get("canonical_payload") if existing else {}, canonical_fields)
    merged_providers = _merge_str_lists(
        existing.get("source_providers") if existing else None,
        normalized_fields.get("source_providers"),
    )
    incoming_hiring_team = canonical_fields.get("hiring_team")
    hiring_team = (
        incoming_hiring_team
        if incoming_hiring_team is not None
        else (existing.get("hiring_team") if existing else None)
    )
    posting_status_incoming = _normalize_text(canonical_fields.get("posting_status"))

    row_to_write = {
        "org_id": org_id,
        "company_id": company_uuid if company_uuid is not None else (existing.get("company_id") if existing else None),
        "entity_id": resolved_entity_id,
        "theirstack_job_id": normalized_fields["theirstack_job_id"]
        if normalized_fields["theirstack_job_id"] is not None
        else (existing.get("theirstack_job_id") if existing else None),
        "job_url": normalized_fields["job_url"]
        if normalized_fields["job_url"] is not None
        else (existing.get("job_url") if existing else None),
        "job_title": normalized_fields["job_title"]
        if normalized_fields["job_title"] is not None
        else (existing.get("job_title") if existing else None),
        "normalized_title": normalized_fields["normalized_title"]
        if normalized_fields["normalized_title"] is not None
        else (existing.get("normalized_title") if existing else None),
        "company_name": normalized_fields["company_name"]
        if normalized_fields["company_name"] is not None
        else (existing.get("company_name") if existing else None),
        "company_domain": normalized_fields["company_domain"]
        if normalized_fields["company_domain"] is not None
        else (existing.get("company_domain") if existing else None),
        "location": normalized_fields["location"]
        if normalized_fields["location"] is not None
        else (existing.get("location") if existing else None),
        "short_location": normalized_fields["short_location"]
        if normalized_fields["short_location"] is not None
        else (existing.get("short_location") if existing else None),
        "state_code": normalized_fields["state_code"]
        if normalized_fields["state_code"] is not None
        else (existing.get("state_code") if existing else None),
        "country_code": normalized_fields["country_code"]
        if normalized_fields["country_code"] is not None
        else (existing.get("country_code") if existing else None),
        "remote": normalized_fields["remote"]
        if normalized_fields["remote"] is not None
        else (existing.get("remote") if existing else None),
        "hybrid": normalized_fields["hybrid"]
        if normalized_fields["hybrid"] is not None
        else (existing.get("hybrid") if existing else None),
        "seniority": normalized_fields["seniority"]
        if normalized_fields["seniority"] is not None
        else (existing.get("seniority") if existing else None),
        "employment_statuses": normalized_fields["employment_statuses"]
        if normalized_fields["employment_statuses"] is not None
        else (existing.get("employment_statuses") if existing else None),
        "date_posted": normalized_fields["date_posted"]
        if normalized_fields["date_posted"] is not None
        else (existing.get("date_posted") if existing else None),
        "discovered_at": normalized_fields["discovered_at"]
        if normalized_fields["discovered_at"] is not None
        else (existing.get("discovered_at") if existing else None),
        "salary_string": normalized_fields["salary_string"]
        if normalized_fields["salary_string"] is not None
        else (existing.get("salary_string") if existing else None),
        "min_annual_salary_usd": normalized_fields["min_annual_salary_usd"]
        if normalized_fields["min_annual_salary_usd"] is not None
        else (existing.get("min_annual_salary_usd") if existing else None),
        "max_annual_salary_usd": normalized_fields["max_annual_salary_usd"]
        if normalized_fields["max_annual_salary_usd"] is not None
        else (existing.get("max_annual_salary_usd") if existing else None),
        "description": normalized_fields["description"]
        if normalized_fields["description"] is not None
        else (existing.get("description") if existing else None),
        "technology_slugs": normalized_fields["technology_slugs"]
        if normalized_fields["technology_slugs"] is not None
        else (existing.get("technology_slugs") if existing else None),
        "hiring_team": hiring_team,
        "posting_status": posting_status_incoming
        if posting_status_incoming is not None
        else (existing.get("posting_status") if existing else "active"),
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
            client.table("job_posting_entities")
            .update(row_to_write)
            .eq("org_id", org_id)
            .eq("entity_id", resolved_entity_id)
            .eq("record_version", existing_version)
            .execute()
        )
        if not result.data:
            raise EntityStateVersionError("Version conflict during job posting entity update")
        return result.data[0]

    result = client.table("job_posting_entities").insert(row_to_write).execute()
    return result.data[0]
