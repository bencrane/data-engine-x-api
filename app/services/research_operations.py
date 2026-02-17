from __future__ import annotations

import re
import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_research import ResolveG2UrlOutput, ResolvePricingPageUrlOutput
from app.providers import gemini, openai_provider


def _normalize_company_domain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _safe_confidence(value: Any) -> float:
    if isinstance(value, int):
        return float(value)
    if isinstance(value, float):
        return value
    return 0.0


def _attempt_status(*, ok: bool, has_match: bool) -> str:
    if not ok:
        return "failed"
    return "found" if has_match else "not_found"


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
    try:
        settings = get_settings()
        result = await gemini.resolve_structured(
            api_key=settings.gemini_api_key,
            model=settings.llm_primary_model,
            prompt=prompt,
        )
        attempt = result.get("attempt") if isinstance(result, dict) else None
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"gemini_exception:{exc.__class__.__name__}",
            "http_status": None,
            "parsed": None,
            "raw": {"error": str(exc)},
        }
    return {
        "ok": bool(isinstance(attempt, dict) and attempt.get("status") == "completed"),
        "error": attempt.get("error") if isinstance(attempt, dict) else "invalid_attempt",
        "http_status": attempt.get("http_status") if isinstance(attempt, dict) else None,
        "parsed": result.get("mapped") if isinstance(result, dict) else None,
        "raw": attempt.get("raw_response") if isinstance(attempt, dict) else None,
    }


async def _call_openai(*, prompt: str) -> dict[str, Any]:
    try:
        settings = get_settings()
        result = await openai_provider.resolve_structured(
            api_key=settings.openai_api_key,
            model=settings.llm_fallback_model,
            prompt=prompt,
        )
        attempt = result.get("attempt") if isinstance(result, dict) else None
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "error": f"openai_exception:{exc.__class__.__name__}",
            "http_status": None,
            "parsed": None,
            "raw": {"error": str(exc)},
        }
    return {
        "ok": bool(isinstance(attempt, dict) and attempt.get("status") == "completed"),
        "error": attempt.get("error") if isinstance(attempt, dict) else "invalid_attempt",
        "http_status": attempt.get("http_status") if isinstance(attempt, dict) else None,
        "parsed": result.get("mapped") if isinstance(result, dict) else None,
        "raw": attempt.get("raw_response") if isinstance(attempt, dict) else None,
    }


async def execute_company_research_resolve_g2_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []

    company_name = input_data.get("company_name")
    company_domain = _normalize_company_domain(input_data.get("company_domain"))
    if not isinstance(company_name, str) or not company_name.strip():
        return {
            "run_id": run_id,
            "operation_id": "company.research.resolve_g2_url",
            "status": "failed",
            "missing_inputs": ["company_name"],
            "provider_attempts": attempts,
        }

    prompt = _build_prompt(company_name=company_name.strip(), company_domain=company_domain if isinstance(company_domain, str) else None)

    gemini = await _call_gemini(prompt=prompt)
    parsed = gemini.get("parsed") if gemini.get("ok") else None
    g2_url = _extract_g2_url((parsed or {}).get("g2_url") if isinstance(parsed, dict) else None)
    attempts.append(
        {
            "provider": "gemini",
            "action": "resolve_g2_url",
            "status": _attempt_status(ok=bool(gemini.get("ok")), has_match=bool(g2_url)),
            "http_status": gemini.get("http_status"),
            "raw_response": gemini.get("raw") or {"error": gemini.get("error")},
        }
    )
    confidence = _safe_confidence((parsed or {}).get("confidence") if isinstance(parsed, dict) else None)

    provider_used = "gemini" if g2_url else None

    if not g2_url:
        openai = await _call_openai(prompt=prompt)
        parsed = openai.get("parsed") if openai.get("ok") else None
        g2_url = _extract_g2_url((parsed or {}).get("g2_url") if isinstance(parsed, dict) else None)
        attempts.append(
            {
                "provider": "openai",
                "action": "resolve_g2_url",
                "status": _attempt_status(ok=bool(openai.get("ok")), has_match=bool(g2_url)),
                "http_status": openai.get("http_status"),
                "raw_response": openai.get("raw") or {"error": openai.get("error")},
            }
        )
        confidence = _safe_confidence((parsed or {}).get("confidence") if isinstance(parsed, dict) else None)
        if g2_url:
            provider_used = "openai"

    try:
        output = ResolveG2UrlOutput.model_validate(
            {
                "company_name": company_name.strip(),
                "company_domain": company_domain,
                "g2_url": g2_url,
                "confidence": confidence,
                "provider_used": provider_used,
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.research.resolve_g2_url",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "company.research.resolve_g2_url",
        "status": "found" if g2_url else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_resolve_pricing_page_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []

    company_name = input_data.get("company_name")
    company_domain = _normalize_company_domain(input_data.get("company_domain"))
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

    gemini = await _call_gemini(prompt=prompt)
    parsed = gemini.get("parsed") if gemini.get("ok") else None
    candidate = (parsed or {}).get("pricing_page_url") if isinstance(parsed, dict) else None
    pricing_page_url = _extract_url(candidate)
    if not _looks_like_pricing_url(pricing_page_url, company_domain if isinstance(company_domain, str) else None):
        pricing_page_url = None
    attempts.append(
        {
            "provider": "gemini",
            "action": "resolve_pricing_page_url",
            "status": _attempt_status(ok=bool(gemini.get("ok")), has_match=bool(pricing_page_url)),
            "http_status": gemini.get("http_status"),
            "raw_response": gemini.get("raw") or {"error": gemini.get("error")},
        }
    )

    confidence = _safe_confidence((parsed or {}).get("confidence") if isinstance(parsed, dict) else None)

    provider_used = "gemini" if pricing_page_url else None

    if not pricing_page_url:
        openai = await _call_openai(prompt=prompt)
        parsed = openai.get("parsed") if openai.get("ok") else None
        candidate = (parsed or {}).get("pricing_page_url") if isinstance(parsed, dict) else None
        pricing_page_url = _extract_url(candidate)
        if not _looks_like_pricing_url(pricing_page_url, company_domain if isinstance(company_domain, str) else None):
            pricing_page_url = None
        attempts.append(
            {
                "provider": "openai",
                "action": "resolve_pricing_page_url",
                "status": _attempt_status(ok=bool(openai.get("ok")), has_match=bool(pricing_page_url)),
                "http_status": openai.get("http_status"),
                "raw_response": openai.get("raw") or {"error": openai.get("error")},
            }
        )

        confidence = _safe_confidence((parsed or {}).get("confidence") if isinstance(parsed, dict) else None)
        if pricing_page_url:
            provider_used = "openai"

    try:
        output = ResolvePricingPageUrlOutput.model_validate(
            {
                "company_name": company_name.strip(),
                "company_domain": company_domain,
                "pricing_page_url": pricing_page_url,
                "confidence": confidence,
                "provider_used": provider_used,
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.research.resolve_pricing_page_url",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    return {
        "run_id": run_id,
        "operation_id": "company.research.resolve_pricing_page_url",
        "status": "found" if pricing_page_url else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }
