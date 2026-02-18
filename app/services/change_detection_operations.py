from __future__ import annotations

import uuid
from typing import Any

from app.services.change_detection import detect_entity_changes
from app.services.entity_state import resolve_company_entity_id, resolve_person_entity_id


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _extract_context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative = input_data.get("cumulative_context")
    if isinstance(cumulative, dict):
        return cumulative
    return input_data


def _extract_org_id(input_data: dict[str, Any], context: dict[str, Any]) -> str | None:
    return _as_str(input_data.get("org_id")) or _as_str(context.get("org_id"))


def _extract_fields_to_watch(input_data: dict[str, Any], context: dict[str, Any]) -> list[str] | None:
    step_config = _as_dict(input_data.get("step_config"))
    fields = step_config.get("fields_to_watch")
    if fields is None:
        fields = context.get("fields_to_watch")
    if not isinstance(fields, list):
        return None
    normalized = [field.strip() for field in fields if isinstance(field, str) and field.strip()]
    return normalized or None


async def execute_company_derive_detect_changes(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.derive.detect_changes"
    provider_attempts: list[dict[str, Any]] = []

    context = _extract_context(input_data)
    org_id = _extract_org_id(input_data, context)
    if not org_id:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["org_id"],
            "provider_attempts": provider_attempts,
        }

    company_profile = _as_dict(context.get("company_profile"))
    canonical_fields = {
        **company_profile,
        **context,
    }
    explicit_entity_id = _as_str(context.get("entity_id")) or _as_str(context.get("company_entity_id"))
    entity_id = resolve_company_entity_id(
        org_id=org_id,
        canonical_fields=canonical_fields,
        entity_id=explicit_entity_id,
    )
    fields_to_watch = _extract_fields_to_watch(input_data, context)

    detection = detect_entity_changes(
        org_id=org_id,
        entity_type="company",
        entity_id=entity_id,
        fields_to_watch=fields_to_watch,
    )
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "found" if detection.get("has_changes") else "not_found",
        "output": detection,
        "provider_attempts": provider_attempts,
    }


async def execute_person_derive_detect_changes(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "person.derive.detect_changes"
    provider_attempts: list[dict[str, Any]] = []

    context = _extract_context(input_data)
    org_id = _extract_org_id(input_data, context)
    if not org_id:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["org_id"],
            "provider_attempts": provider_attempts,
        }

    person_profile = _as_dict(context.get("person_profile"))
    canonical_fields = {
        **person_profile,
        **context,
    }
    explicit_entity_id = _as_str(context.get("entity_id")) or _as_str(context.get("person_entity_id"))
    entity_id = resolve_person_entity_id(
        org_id=org_id,
        canonical_fields=canonical_fields,
        entity_id=explicit_entity_id,
    )
    fields_to_watch = _extract_fields_to_watch(input_data, context)

    detection = detect_entity_changes(
        org_id=org_id,
        entity_type="person",
        entity_id=entity_id,
        fields_to_watch=fields_to_watch,
    )
    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "found" if detection.get("has_changes") else "not_found",
        "output": detection,
        "provider_attempts": provider_attempts,
    }
