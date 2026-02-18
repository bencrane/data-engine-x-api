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
            "attempt": {"provider": "anthropic", "action": "llm_resolve", "status": "failed", "error": "missing_api_key"},
            "mapped": None,
        }
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "anthropic", "action": "llm_resolve", "status": "failed", "http_status": res.status_code, "raw_response": body},
            "mapped": None,
        }
    content = ""
    content_blocks = body.get("content") or []
    if isinstance(content_blocks, list):
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    content += text
    mapped = extract_json_block(content)
    return {
        "attempt": {
            "provider": "anthropic",
            "action": "llm_resolve",
            "status": "completed" if mapped is not None else "failed",
            "provider_status": "invalid_json_output" if mapped is None else "ok",
            "raw_response": body,
        },
        "mapped": mapped,
    }
