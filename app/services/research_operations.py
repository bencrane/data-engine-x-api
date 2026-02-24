from __future__ import annotations

import re
import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_research import (
    CheckVCFundingOutput,
    DiscoverCompetitorsOutput,
    FindSimilarCompaniesOutput,
    LookupAlumniOutput,
    LookupChampionTestimonialsOutput,
    LookupChampionsOutput,
    LookupCustomersOutput,
    ResolveG2UrlOutput,
    ResolvePricingPageUrlOutput,
)
from app.contracts.icp_companies import FetchIcpCompaniesOutput
from app.contracts.job_validation import JobValidationOutput
from app.providers import gemini, openai_provider, revenueinfra


def _normalize_company_domain(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    return cleaned or None


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
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


def _company_research_context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative = input_data.get("cumulative_context")
    if isinstance(cumulative, dict):
        return cumulative
    return {}


def _extract_company_domain(input_data: dict[str, Any]) -> str | None:
    context = _company_research_context(input_data)
    company_profile = context.get("company_profile")
    profile = company_profile if isinstance(company_profile, dict) else {}
    return _normalize_company_domain(
        input_data.get("company_domain")
        or context.get("company_domain")
        or profile.get("company_domain")
    )


def _extract_company_name(input_data: dict[str, Any]) -> str | None:
    context = _company_research_context(input_data)
    company_profile = context.get("company_profile")
    profile = company_profile if isinstance(company_profile, dict) else {}
    return _as_non_empty_str(
        input_data.get("company_name")
        or context.get("company_name")
        or profile.get("company_name")
    )


def _extract_company_linkedin_url(input_data: dict[str, Any]) -> str | None:
    context = _company_research_context(input_data)
    company_profile = context.get("company_profile")
    profile = company_profile if isinstance(company_profile, dict) else {}
    return _as_non_empty_str(
        input_data.get("company_linkedin_url")
        or context.get("company_linkedin_url")
        or profile.get("company_linkedin_url")
    )


def _extract_company_research_discover_competitors_inputs(
    input_data: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    company_domain = _extract_company_domain(input_data)
    company_name = _extract_company_name(input_data)
    company_linkedin_url = _extract_company_linkedin_url(input_data)
    return company_domain, company_name, company_linkedin_url


def _extract_company_research_lookup_customers_inputs(
    input_data: dict[str, Any],
) -> str | None:
    return _extract_company_domain(input_data)


def _extract_company_research_find_similar_companies_inputs(
    input_data: dict[str, Any],
) -> str | None:
    return _extract_company_domain(input_data)


def _extract_company_research_lookup_champions_inputs(
    input_data: dict[str, Any],
) -> str | None:
    return _extract_company_domain(input_data)


def _extract_company_research_lookup_alumni_inputs(
    input_data: dict[str, Any],
) -> str | None:
    return _extract_company_domain(input_data)


def _extract_icp_candidate_limit(input_data: dict[str, Any]) -> int | None:
    raw_limit = (
        input_data.get("limit")
        or (input_data.get("cumulative_context", {}) if isinstance(input_data.get("cumulative_context"), dict) else {}).get("limit")
        or (input_data.get("options", {}) if isinstance(input_data.get("options"), dict) else {}).get("limit")
    )
    if isinstance(raw_limit, int) and raw_limit > 0:
        return raw_limit
    if isinstance(raw_limit, str):
        cleaned = raw_limit.strip()
        if cleaned.isdigit():
            parsed = int(cleaned)
            if parsed > 0:
                return parsed
    return None


def _extract_company_research_check_vc_funding_inputs(
    input_data: dict[str, Any],
) -> str | None:
    return _extract_company_domain(input_data)


def _job_validation_context(input_data: dict[str, Any]) -> dict[str, Any]:
    cumulative = input_data.get("cumulative_context")
    if isinstance(cumulative, dict):
        return cumulative
    return {}


def _extract_job_validation_company_domain(input_data: dict[str, Any]) -> str | None:
    context = _job_validation_context(input_data)
    company_object = context.get("company_object")
    company = company_object if isinstance(company_object, dict) else {}
    return _normalize_company_domain(
        input_data.get("company_domain")
        or context.get("company_domain")
        or company.get("domain")
    )


def _extract_job_validation_job_title(input_data: dict[str, Any]) -> str | None:
    context = _job_validation_context(input_data)
    return _as_non_empty_str(
        input_data.get("job_title")
        or context.get("job_title")
    )


def _extract_job_validation_company_name(input_data: dict[str, Any]) -> str | None:
    context = _job_validation_context(input_data)
    company_object = context.get("company_object")
    company = company_object if isinstance(company_object, dict) else {}
    return _as_non_empty_str(
        input_data.get("company_name")
        or context.get("company_name")
        or company.get("name")
    )


async def execute_job_validate_is_active(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "job.validate.is_active"

    company_domain = _extract_job_validation_company_domain(input_data)
    job_title = _extract_job_validation_job_title(input_data)
    company_name = _extract_job_validation_company_name(input_data)
    if not company_domain or not job_title:
        missing_inputs: list[str] = []
        if not company_domain:
            missing_inputs.append("company_domain")
        if not job_title:
            missing_inputs.append("job_title")
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": missing_inputs,
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.validate_job_active(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        company_domain=company_domain,
        job_title=job_title,
        company_name=company_name,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    normalized_mapped = mapped if isinstance(mapped, dict) else {}
    try:
        output = JobValidationOutput.model_validate(
            {
                "validation_result": normalized_mapped.get("validation_result"),
                "confidence": normalized_mapped.get("confidence"),
                "indeed_found": normalized_mapped.get("indeed_found"),
                "indeed_match_count": normalized_mapped.get("indeed_match_count"),
                "indeed_any_expired": normalized_mapped.get("indeed_any_expired"),
                "indeed_matched_by": normalized_mapped.get("indeed_matched_by"),
                "linkedin_found": normalized_mapped.get("linkedin_found"),
                "linkedin_match_count": normalized_mapped.get("linkedin_match_count"),
                "linkedin_matched_by": normalized_mapped.get("linkedin_matched_by"),
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_check_vc_funding(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.check_vc_funding"

    company_domain = _extract_company_research_check_vc_funding_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.check_vc_funding(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    has_raised_vc = False
    vc_count = 0
    vc_names: list[str] = []
    vcs: list[dict[str, str | None]] = []
    founded_date: str | None = None
    if isinstance(mapped, dict):
        has_raised_vc = bool(mapped.get("has_raised_vc"))
        if isinstance(mapped.get("vc_names"), list):
            vc_names = mapped.get("vc_names") or []
        if isinstance(mapped.get("vcs"), list):
            vcs = mapped.get("vcs") or []
        founded_date = _as_non_empty_str(mapped.get("founded_date"))
        if isinstance(mapped.get("vc_count"), int):
            vc_count = mapped.get("vc_count") or 0

    vc_count = max(vc_count, len(vc_names), len(vcs))

    try:
        output = CheckVCFundingOutput.model_validate(
            {
                "has_raised_vc": has_raised_vc,
                "vc_count": vc_count,
                "vc_names": vc_names,
                "vcs": vcs,
                "founded_date": founded_date,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "found",
        "output": {
            "has_raised_vc": output["has_raised_vc"],
            "vc_count": output["vc_count"],
            "vc_names": output["vc_names"],
            "vcs": output["vcs"],
            "founded_date": output["founded_date"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_research_lookup_customers(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.lookup_customers"

    company_domain = _extract_company_research_lookup_customers_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.lookup_customers(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    customers = []
    customer_count = 0
    if isinstance(mapped, dict):
        if isinstance(mapped.get("customers"), list):
            customers = mapped.get("customers") or []
        if isinstance(mapped.get("customer_count"), int):
            customer_count = mapped.get("customer_count") or 0

    if customer_count != len(customers):
        customer_count = len(customers)

    try:
        output = LookupCustomersOutput.model_validate(
            {
                "customers": customers,
                "customer_count": customer_count,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            "customers": output["customers"],
            "customer_count": output["customer_count"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_research_lookup_alumni(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.lookup_alumni"

    company_domain = _extract_company_research_lookup_alumni_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.lookup_alumni(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    alumni = []
    alumni_count = 0
    if isinstance(mapped, dict):
        if isinstance(mapped.get("alumni"), list):
            alumni = mapped.get("alumni") or []
        if isinstance(mapped.get("alumni_count"), int):
            alumni_count = mapped.get("alumni_count") or 0

    if alumni_count != len(alumni):
        alumni_count = len(alumni)

    try:
        output = LookupAlumniOutput.model_validate(
            {
                "alumni": alumni,
                "alumni_count": alumni_count,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            "alumni": output["alumni"],
            "alumni_count": output["alumni_count"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_fetch_icp_candidates(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.fetch.icp_candidates"

    limit = _extract_icp_candidate_limit(input_data)

    settings = get_settings()
    result = await revenueinfra.fetch_icp_companies(
        base_url=settings.revenueinfra_api_url,
        limit=limit,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    normalized_mapped = mapped if isinstance(mapped, dict) else {}
    results: list[dict[str, Any]] = []
    if isinstance(normalized_mapped.get("results"), list):
        results = [
            item
            for item in (normalized_mapped.get("results") or [])
            if isinstance(item, dict)
        ]

    company_count = normalized_mapped.get("company_count")
    if not isinstance(company_count, int):
        company_count = len(results)

    try:
        output = FetchIcpCompaniesOutput.model_validate(
            {
                "company_count": company_count,
                "results": results,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_lookup_champions(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.lookup_champions"

    company_domain = _extract_company_research_lookup_champions_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.lookup_champions(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    champions = []
    champion_count = 0
    if isinstance(mapped, dict):
        if isinstance(mapped.get("champions"), list):
            champions = mapped.get("champions") or []
        if isinstance(mapped.get("champion_count"), int):
            champion_count = mapped.get("champion_count") or 0

    if champion_count != len(champions):
        champion_count = len(champions)

    try:
        output = LookupChampionsOutput.model_validate(
            {
                "champions": champions,
                "champion_count": champion_count,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            "champions": output["champions"],
            "champion_count": output["champion_count"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_research_lookup_champion_testimonials(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.lookup_champion_testimonials"

    company_domain = _extract_company_research_lookup_champions_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.lookup_champion_testimonials(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status in {"failed", "skipped"}:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }

    champions = []
    champion_count = 0
    if isinstance(mapped, dict):
        if isinstance(mapped.get("champions"), list):
            champions = mapped.get("champions") or []
        if isinstance(mapped.get("champion_count"), int):
            champion_count = mapped.get("champion_count") or 0

    if champion_count != len(champions):
        champion_count = len(champions)

    try:
        output = LookupChampionTestimonialsOutput.model_validate(
            {
                "champions": champions,
                "champion_count": champion_count,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            "champions": output["champions"],
            "champion_count": output["champion_count"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_research_discover_competitors(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.discover_competitors"

    company_domain, company_name, company_linkedin_url = (
        _extract_company_research_discover_competitors_inputs(input_data)
    )

    if not company_domain and not company_name:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain", "company_name"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.discover_competitors(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain or "",
        company_name=company_name or "",
        company_linkedin_url=company_linkedin_url,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status == "failed":
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }
    if status == "skipped":
        missing_inputs: list[str] = []
        if not company_domain:
            missing_inputs.append("company_domain")
        if not company_name:
            missing_inputs.append("company_name")
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": missing_inputs or ["company_domain|company_name"],
            "provider_attempts": attempts,
        }

    competitors = []
    if isinstance(mapped, dict) and isinstance(mapped.get("competitors"), list):
        competitors = mapped.get("competitors") or []

    try:
        output = DiscoverCompetitorsOutput.model_validate(
            {
                "competitors": competitors,
                "competitor_count": len(competitors),
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": output,
        "provider_attempts": attempts,
    }


async def execute_company_research_find_similar_companies(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    attempts: list[dict[str, Any]] = []
    operation_id = "company.research.find_similar_companies"

    company_domain = _extract_company_research_find_similar_companies_inputs(input_data)
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    result = await revenueinfra.find_similar_companies(
        base_url=settings.revenueinfra_api_url,
        domain=company_domain,
    )
    attempt = result.get("attempt") if isinstance(result, dict) else {}
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped") if isinstance(result, dict) else None

    status = attempt.get("status") if isinstance(attempt, dict) else "failed"
    if status == "failed":
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
        }
    if status == "skipped":
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    similar_companies: list[dict[str, Any]] = []
    similar_count = 0
    if isinstance(mapped, dict):
        if isinstance(mapped.get("similar_companies"), list):
            similar_companies = mapped.get("similar_companies") or []
        if isinstance(mapped.get("similar_count"), int):
            similar_count = mapped.get("similar_count") or 0

    if similar_count != len(similar_companies):
        similar_count = len(similar_companies)

    try:
        output = FindSimilarCompaniesOutput.model_validate(
            {
                "similar_companies": similar_companies,
                "similar_count": similar_count,
                "source_provider": "revenueinfra",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": operation_id,
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": operation_id,
        "status": "not_found" if status == "not_found" else "found",
        "output": {
            "similar_companies": output["similar_companies"],
            "similar_count": output["similar_count"],
            "source_provider": output["source_provider"],
        },
        "provider_attempts": attempts,
    }
