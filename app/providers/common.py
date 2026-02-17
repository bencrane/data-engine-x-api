from __future__ import annotations

import time
from typing import Any, TypedDict


class ProviderAdapterResult(TypedDict):
    attempt: dict[str, Any]
    mapped: Any


def now_ms() -> int:
    return int(time.time() * 1000)


def parse_json_or_raw(text: str, parser: Any) -> dict[str, Any]:
    try:
        parsed = parser()
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except Exception:  # noqa: BLE001
        return {"raw": text}
