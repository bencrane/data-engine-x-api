from __future__ import annotations

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


def _as_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


async def verify_email(
    *,
    api_key: str | None,
    email: str,
    timeout_seconds: int,
    inconclusive_statuses: set[str],
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "millionverifier",
                "action": "verify_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            "https://api.millionverifier.com/api/v3",
            params={"api": api_key, "email": email, "timeout": timeout_seconds},
        )
        body = parse_json_or_raw(res.text, res.json)

    provider_error = _as_str(body.get("error"))
    if res.status_code >= 400 or provider_error:
        return {
            "attempt": {
                "provider": "millionverifier",
                "action": "verify_email",
                "status": "failed",
                "http_status": res.status_code,
                "provider_status": provider_error,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    result = (_as_str(body.get("result")) or "").lower()
    inconclusive = result in inconclusive_statuses or not result
    return {
        "attempt": {
            "provider": "millionverifier",
            "action": "verify_email",
            "status": "verified",
            "provider_status": result,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "provider": "millionverifier",
            "status": result,
            "inconclusive": inconclusive,
            "raw_response": body,
        },
    }
