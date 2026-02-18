from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw

_BASE_URL = "https://api.revenueinfra.com"
_PROVIDER = "revenueinfra"


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _configured_base_url() -> str:
    configured = _as_str(get_settings().revenueinfra_api_url)
    return (configured or _BASE_URL).rstrip("/")
