from __future__ import annotations

from numbers import Number
from typing import Any

from app.database import get_supabase_client


def _is_numeric(value: Any) -> bool:
    return isinstance(value, Number) and not isinstance(value, bool)


def _as_payload(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_fields_to_watch(
    *,
    current_payload: dict[str, Any],
    previous_payload: dict[str, Any],
    fields_to_watch: list[str] | None,
) -> list[str]:
    if fields_to_watch:
        return [field for field in fields_to_watch if isinstance(field, str) and field.strip()]
    return sorted(set(current_payload.keys()) | set(previous_payload.keys()))


def _numeric_magnitude(previous_value: Number, current_value: Number) -> tuple[float, float | None]:
    absolute_change = abs(float(current_value) - float(previous_value))
    if float(previous_value) == 0:
        return absolute_change, None
    percent_change = (absolute_change / abs(float(previous_value))) * 100.0
    return absolute_change, percent_change


def detect_entity_changes(
    *,
    org_id: str,
    entity_type: str,
    entity_id: str,
    fields_to_watch: list[str] | None,
) -> dict[str, Any]:
    if entity_type not in {"company", "person", "job"}:
        raise ValueError("entity_type must be 'company', 'person', or 'job'")

    client = get_supabase_client()
    result = (
        client.table("entity_snapshots")
        .select("canonical_payload,captured_at")
        .eq("org_id", org_id)
        .eq("entity_type", entity_type)
        .eq("entity_id", entity_id)
        .order("captured_at", desc=True)
        .limit(2)
        .execute()
    )

    snapshots = result.data or []
    if len(snapshots) < 2:
        return {
            "has_changes": False,
            "reason": "insufficient_history",
        }

    current_snapshot = snapshots[0]
    previous_snapshot = snapshots[1]
    current_payload = _as_payload(current_snapshot.get("canonical_payload"))
    previous_payload = _as_payload(previous_snapshot.get("canonical_payload"))
    watched_fields = _normalize_fields_to_watch(
        current_payload=current_payload,
        previous_payload=previous_payload,
        fields_to_watch=fields_to_watch,
    )

    changes: list[dict[str, Any]] = []
    unchanged_fields: list[str] = []
    for field in watched_fields:
        previous_value = previous_payload.get(field)
        current_value = current_payload.get(field)

        if previous_value == current_value:
            unchanged_fields.append(field)
            continue

        if previous_value is None and current_value is not None:
            changes.append(
                {
                    "field": field,
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "change_type": "added",
                }
            )
            continue

        if previous_value is not None and current_value is None:
            changes.append(
                {
                    "field": field,
                    "previous_value": previous_value,
                    "current_value": current_value,
                    "change_type": "removed",
                }
            )
            continue

        if _is_numeric(previous_value) and _is_numeric(current_value):
            change_type = "increased" if float(current_value) > float(previous_value) else "decreased"
            absolute_change, percent_change = _numeric_magnitude(
                previous_value=previous_value,
                current_value=current_value,
            )
            numeric_change: dict[str, Any] = {
                "field": field,
                "previous_value": previous_value,
                "current_value": current_value,
                "change_type": change_type,
                "absolute_change": absolute_change,
            }
            if percent_change is not None:
                numeric_change["percent_change"] = percent_change
            changes.append(numeric_change)
            continue

        changes.append(
            {
                "field": field,
                "previous_value": previous_value,
                "current_value": current_value,
                "change_type": "changed",
            }
        )

    if not changes:
        return {
            "has_changes": False,
            "reason": "no_changes",
            "entity_id": entity_id,
            "entity_type": entity_type,
            "previous_snapshot_at": previous_snapshot.get("captured_at"),
            "current_snapshot_at": current_snapshot.get("captured_at"),
            "changes": [],
            "unchanged_fields": unchanged_fields,
        }

    return {
        "has_changes": True,
        "entity_id": entity_id,
        "entity_type": entity_type,
        "previous_snapshot_at": previous_snapshot.get("captured_at"),
        "current_snapshot_at": current_snapshot.get("captured_at"),
        "changes": changes,
        "unchanged_fields": unchanged_fields,
    }
