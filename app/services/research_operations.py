from __future__ import annotations

import json
import re
import time
import uuid
from typing import Any

import httpx

from app.config import get_settings


def _now_ms() -> int:
    return int(time.time() * 1000)


def _extract_json_block(text: str) -> dict[str, Any] | None:
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


def _extract_g2_url(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"https?://(?:www\.)?g2\.com/[^\s\"'<>)]*", value)
    if not match:
        return None
    url = match.group(0).rstrip('.,;:')
    if 'g2.com' not in url:
        return None
    return url


def _extract_url(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"https?://[^\s\"'<>)]*", value)
    if not match:
        return None
    return match.group(0).rstrip(".,;:")


def _domain_from_value(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip().lower()
    if cleaned.startswith("http://"):
        cleaned = cleaned[len("http://") :]
    if cleaned.startswith("https://"):
        cleaned = cleaned[len("https://") :]
    cleaned = cleaned.split("/")[0]
    if cleaned.startswith("www."):
        cleaned = cleaned[len("www.") :]
    return cleaned or None


def _looks_like_pricing_url(url: str | None, company_domain: str | None) -> bool:
    if not url:
        return False
    lowered = url.lower()
    if "/pricing" not in lowered and "pricing" not in lowered:
        return False
    domain = _domain_from_value(url)
    expected = _domain_from_value(company_domain)
    if not expected:
        return True
    if not domain:
        return False
    return domain == expected or domain.endswith(f".{expected}")


def _build_prompt(company_name: str, company_domain: str | None) -> str:
    domain_part = company_domain or "unknown"
    return (
        "Find the official G2 profile URL for this company. "
        "Return JSON only with keys: g2_url, confidence, reason. "
        "If no reliable G2 page exists, set g2_url to null and confidence to 0.\n"
        f"company_name: {company_name}\n"
        f"company_domain: {domain_part}"
    )


def _build_pricing_prompt(company_name: str, company_domain: str | None) -> str:
    domain_part = company_domain or "unknown"
    return (
        "Find the official pricing page URL for this company. "
        "Return JSON only with keys: pricing_page_url, confidence, reason. "
        "If no reliable pricing page exists, set pricing_page_url to null and confidence to 0.\n"
        f"company_name: {company_name}\n"
        f"company_domain: {domain_part}"
    )


async def _call_gemini(*, prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.gemini_api_key:
        return {"ok": False, "error": "missing_api_key"}

    model = settings.llm_primary_model.strip()
    if model in {"gemini", "gemini-3", "gemini-2"}:
        model = "gemini-2.0-flash"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            url,
            params={"key": settings.gemini_api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {"temperature": 0},
            },
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        return {"ok": False, "error": "http_error", "http_status": res.status_code, "raw": body}

    text = ""
    for candidate in body.get("candidates") or []:
        parts = ((candidate.get("content") or {}).get("parts") or [])
        for part in parts:
            if isinstance(part.get("text"), str):
                text += part["text"]
    data = _extract_json_block(text)
    return {"ok": True, "parsed": data, "raw": body}


async def _call_openai(*, prompt: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.openai_api_key:
        return {"ok": False, "error": "missing_api_key"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.llm_fallback_model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": "Return JSON only."},
                    {"role": "user", "content": prompt},
                ],
            },
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        return {"ok": False, "error": "http_error", "http_status": res.status_code, "raw": body}

    content = ""
    choices = body.get("choices") or []
    if choices:
        content = (((choices[0] or {}).get("message") or {}).get("content") or "")
    data = _extract_json_block(content)
    return {"ok": True, "parsed": data, "raw": body}


async def execute_company_research_resolve_g2_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []

    company_name = input_data.get("company_name")
    company_domain = input_data.get("company_domain")
    if not isinstance(company_name, str) or not company_name.strip():
        return {
            "run_id": run_id,
            "operation_id": "company.research.resolve_g2_url",
            "status": "failed",
            "missing_inputs": ["company_name"],
            "provider_attempts": attempts,
        }

    prompt = _build_prompt(company_name=company_name.strip(), company_domain=company_domain if isinstance(company_domain, str) else None)

    start_ms = _now_ms()
    gemini = await _call_gemini(prompt=prompt)
    attempts.append(
        {
            "provider": "gemini",
            "action": "resolve_g2_url",
            "status": "failed" if not gemini.get("ok") else "completed",
            "http_status": gemini.get("http_status"),
            "duration_ms": _now_ms() - start_ms,
            "raw_response": gemini.get("raw") or {"error": gemini.get("error")},
        }
    )

    parsed = gemini.get("parsed") if gemini.get("ok") else None
    g2_url = _extract_g2_url((parsed or {}).get("g2_url") if isinstance(parsed, dict) else None)
    confidence = (parsed or {}).get("confidence") if isinstance(parsed, dict) else None
    if isinstance(confidence, int):
        confidence = float(confidence)
    if not isinstance(confidence, float):
        confidence = 0.0

    provider_used = "gemini" if g2_url else None

    if not g2_url:
        start_ms = _now_ms()
        openai = await _call_openai(prompt=prompt)
        attempts.append(
            {
                "provider": "openai",
                "action": "resolve_g2_url",
                "status": "failed" if not openai.get("ok") else "completed",
                "http_status": openai.get("http_status"),
                "duration_ms": _now_ms() - start_ms,
                "raw_response": openai.get("raw") or {"error": openai.get("error")},
            }
        )

        parsed = openai.get("parsed") if openai.get("ok") else None
        g2_url = _extract_g2_url((parsed or {}).get("g2_url") if isinstance(parsed, dict) else None)
        confidence = (parsed or {}).get("confidence") if isinstance(parsed, dict) else 0.0
        if isinstance(confidence, int):
            confidence = float(confidence)
        if not isinstance(confidence, float):
            confidence = 0.0
        if g2_url:
            provider_used = "openai"

    return {
        "run_id": run_id,
        "operation_id": "company.research.resolve_g2_url",
        "status": "found" if g2_url else "not_found",
        "output": {
            "company_name": company_name,
            "company_domain": company_domain,
            "g2_url": g2_url,
            "confidence": confidence,
            "provider_used": provider_used,
        },
        "provider_attempts": attempts,
    }


async def execute_company_research_resolve_pricing_page_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []

    company_name = input_data.get("company_name")
    company_domain = input_data.get("company_domain")
    if not isinstance(company_name, str) or not company_name.strip():
        return {
            "run_id": run_id,
            "operation_id": "company.research.resolve_pricing_page_url",
            "status": "failed",
            "missing_inputs": ["company_name"],
            "provider_attempts": attempts,
        }

    prompt = _build_pricing_prompt(
        company_name=company_name.strip(),
        company_domain=company_domain if isinstance(company_domain, str) else None,
    )

    start_ms = _now_ms()
    gemini = await _call_gemini(prompt=prompt)
    attempts.append(
        {
            "provider": "gemini",
            "action": "resolve_pricing_page_url",
            "status": "failed" if not gemini.get("ok") else "completed",
            "http_status": gemini.get("http_status"),
            "duration_ms": _now_ms() - start_ms,
            "raw_response": gemini.get("raw") or {"error": gemini.get("error")},
        }
    )

    parsed = gemini.get("parsed") if gemini.get("ok") else None
    candidate = (parsed or {}).get("pricing_page_url") if isinstance(parsed, dict) else None
    pricing_page_url = _extract_url(candidate)
    if not _looks_like_pricing_url(pricing_page_url, company_domain if isinstance(company_domain, str) else None):
        pricing_page_url = None

    confidence = (parsed or {}).get("confidence") if isinstance(parsed, dict) else None
    if isinstance(confidence, int):
        confidence = float(confidence)
    if not isinstance(confidence, float):
        confidence = 0.0

    provider_used = "gemini" if pricing_page_url else None

    if not pricing_page_url:
        start_ms = _now_ms()
        openai = await _call_openai(prompt=prompt)
        attempts.append(
            {
                "provider": "openai",
                "action": "resolve_pricing_page_url",
                "status": "failed" if not openai.get("ok") else "completed",
                "http_status": openai.get("http_status"),
                "duration_ms": _now_ms() - start_ms,
                "raw_response": openai.get("raw") or {"error": openai.get("error")},
            }
        )

        parsed = openai.get("parsed") if openai.get("ok") else None
        candidate = (parsed or {}).get("pricing_page_url") if isinstance(parsed, dict) else None
        pricing_page_url = _extract_url(candidate)
        if not _looks_like_pricing_url(pricing_page_url, company_domain if isinstance(company_domain, str) else None):
            pricing_page_url = None

        confidence = (parsed or {}).get("confidence") if isinstance(parsed, dict) else 0.0
        if isinstance(confidence, int):
            confidence = float(confidence)
        if not isinstance(confidence, float):
            confidence = 0.0
        if pricing_page_url:
            provider_used = "openai"

    return {
        "run_id": run_id,
        "operation_id": "company.research.resolve_pricing_page_url",
        "status": "found" if pricing_page_url else "not_found",
        "output": {
            "company_name": company_name,
            "company_domain": company_domain,
            "pricing_page_url": pricing_page_url,
            "confidence": confidence,
            "provider_used": provider_used,
        },
        "provider_attempts": attempts,
    }
