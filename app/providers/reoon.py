from __future__ import annotations

import httpx

from app.providers.common import ProviderAdapterResult, now_ms, parse_json_or_raw


async def verify_email(
    *,
    api_key: str | None,
    email: str,
    mode: str,
    inconclusive_statuses: set[str],
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {
                "provider": "reoon",
                "action": "verify_email",
                "status": "skipped",
                "skip_reason": "missing_provider_api_key",
            },
            "mapped": None,
        }

    start_ms = now_ms()
    async with httpx.AsyncClient(timeout=90.0) as client:
        res = await client.get(
            "https://emailverifier.reoon.com/api/v1/verify",
            params={"email": email, "key": api_key, "mode": mode},
        )
        body = parse_json_or_raw(res.text, res.json)

    if res.status_code >= 400:
        return {
            "attempt": {
                "provider": "reoon",
                "action": "verify_email",
                "status": "failed",
                "http_status": res.status_code,
                "duration_ms": now_ms() - start_ms,
                "raw_response": body,
            },
            "mapped": None,
        }

    status = str(body.get("status") or "").lower()
    inconclusive = status in inconclusive_statuses or not status
    return {
        "attempt": {
            "provider": "reoon",
            "action": "verify_email",
            "status": "verified",
            "provider_status": status,
            "duration_ms": now_ms() - start_ms,
            "raw_response": body,
        },
        "mapped": {
            "provider": "reoon",
            "status": status,
            "inconclusive": inconclusive,
            "raw_response": body,
        },
    }
