from __future__ import annotations

from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, parse_json_or_raw
from app.providers.gemini import extract_json_block


async def resolve_structured(
    *,
    api_key: str | None,
    model: str,
    prompt: str,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "openai", "action": "llm_resolve", "status": "failed", "error": "missing_api_key"},
            "mapped": None,
        }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "openai", "action": "llm_resolve", "status": "failed", "http_status": res.status_code, "raw_response": body},
            "mapped": None,
        }
    content = ""
    choices = body.get("choices") or []
    if choices:
        content = (((choices[0] or {}).get("message") or {}).get("content") or "")
    return {
        "attempt": {"provider": "openai", "action": "llm_resolve", "status": "completed", "raw_response": body},
        "mapped": extract_json_block(content),
    }
