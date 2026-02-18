from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path(__file__).resolve().parent / "operations.yaml"


def _load_yaml_text(raw_text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover - only hit if non-JSON YAML is used without PyYAML
            raise RuntimeError(
                "operations.yaml is not JSON-compatible YAML and PyYAML is not installed"
            ) from exc
        parsed = yaml.safe_load(raw_text)

    if not isinstance(parsed, dict):
        raise ValueError("operations registry must parse into an object")
    return parsed


def _normalize_operations(data: dict[str, Any]) -> list[dict[str, Any]]:
    operations = data.get("operations")
    if not isinstance(operations, list):
        raise ValueError("operations registry must contain an 'operations' list")

    normalized: list[dict[str, Any]] = []
    for item in operations:
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("operation_id"), str):
            continue
        normalized.append(item)
    return normalized


@lru_cache(maxsize=1)
def _operations() -> list[dict[str, Any]]:
    raw_text = REGISTRY_PATH.read_text(encoding="utf-8")
    data = _load_yaml_text(raw_text)
    return _normalize_operations(data)


def reload_registry() -> None:
    _operations.cache_clear()
    _operations()


def get_all_operations() -> list[dict[str, Any]]:
    return [dict(op) for op in _operations()]


def get_operation(operation_id: str) -> dict[str, Any] | None:
    for op in _operations():
        if op.get("operation_id") == operation_id:
            return dict(op)
    return None


def get_operations_that_produce(field: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for op in _operations():
        produces = op.get("produces")
        if isinstance(produces, list) and field in produces:
            matches.append(dict(op))
    return matches


def get_operations_by_entity_type(entity_type: str) -> list[dict[str, Any]]:
    return [dict(op) for op in _operations() if op.get("entity_type") == entity_type]


# Load at import time so registry parse errors fail fast at startup.
_operations()
