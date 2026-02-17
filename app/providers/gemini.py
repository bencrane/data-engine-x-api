from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.providers.common import ProviderAdapterResult, parse_json_or_raw


def extract_json_block(text: str) -> dict[str, Any] | None:
    text = text.strip()
    try:
        loaded = json.loads(text)
        if isinstance(loaded, dict):
            return loaded
    except Exception:  # noqa: BLE001
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        loaded = json.loads(match.group(0))
    except Exception:  # noqa: BLE001
        return None
    return loaded if isinstance(loaded, dict) else None


async def resolve_structured(
    *,
    api_key: str | None,
    model: str,
    prompt: str,
) -> ProviderAdapterResult:
    if not api_key:
        return {
            "attempt": {"provider": "gemini", "action": "llm_resolve", "status": "failed", "error": "missing_api_key"},
            "mapped": None,
        }
    use_model = model.strip()
    if use_model in {"gemini", "gemini-3", "gemini-2"}:
        use_model = "gemini-2.0-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent"
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0}},
        )
        body = parse_json_or_raw(res.text, res.json)
    if res.status_code >= 400:
        return {
            "attempt": {"provider": "gemini", "action": "llm_resolve", "status": "failed", "http_status": res.status_code, "raw_response": body},
            "mapped": None,
        }
    text = ""
    for candidate in body.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts") or [])
        for part in parts:
            if isinstance(part.get("text"), str):
                text += part["text"]
    return {
        "attempt": {"provider": "gemini", "action": "llm_resolve", "status": "completed", "raw_response": body},
        "mapped": extract_json_block(text),
    }
