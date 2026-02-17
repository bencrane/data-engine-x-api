from __future__ import annotations

import time
import uuid
from typing import Any

import httpx

from app.config import get_settings


def _now_ms() -> int:
    return int(time.time() * 1000)


def _domain_from_website(website: str | None) -> str | None:
    if not website:
        return None
    normalized = website.strip().lower()
    if normalized.startswith("http://"):
        normalized = normalized[len("http://") :]
    if normalized.startswith("https://"):
        normalized = normalized[len("https://") :]
    normalized = normalized.split("/")[0]
    if normalized.startswith("www."):
        normalized = normalized[len("www.") :]
    return normalized or None


def _canonical_company_from_prospeo(company: dict[str, Any]) -> dict[str, Any]:
    location = company.get("location") or {}
    return {
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_website": company.get("website"),
        "company_linkedin_url": company.get("linkedin_url"),
        "company_type": company.get("type"),
        "industry_primary": company.get("industry"),
        "employee_count": company.get("employee_count"),
        "employee_range": company.get("employee_range"),
        "founded_year": company.get("founded"),
        "hq_locality": location.get("city"),
        "hq_country_code": location.get("country_code"),
        "description_raw": company.get("description"),
        "specialties": company.get("keywords"),
        "annual_revenue_range": company.get("revenue_range_printed"),
        "follower_count": None,
        "logo_url": company.get("logo_url"),
        "source_company_id": company.get("company_id"),
    }


def _canonical_company_from_blitz(company: dict[str, Any]) -> dict[str, Any]:
    hq = company.get("hq") or {}
    return {
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_website": company.get("website"),
        "company_linkedin_url": company.get("linkedin_url"),
        "company_linkedin_id": str(company.get("linkedin_id")) if company.get("linkedin_id") is not None else None,
        "company_type": company.get("type"),
        "industry_primary": company.get("industry"),
        "employee_count": company.get("employees_on_linkedin"),
        "employee_range": company.get("size"),
        "founded_year": company.get("founded_year"),
        "hq_locality": hq.get("city"),
        "hq_country_code": hq.get("country_code"),
        "description_raw": company.get("about"),
        "specialties": company.get("specialties"),
        "follower_count": company.get("followers"),
    }


def _canonical_company_from_companyenrich(company: dict[str, Any]) -> dict[str, Any]:
    socials = company.get("socials") or {}
    location = company.get("location") or {}
    country = location.get("country") or {}
    city = location.get("city") or {}
    state = location.get("state") or {}
    locality = city.get("name") or state.get("name")
    return {
        "company_name": company.get("name"),
        "company_domain": company.get("domain"),
        "company_website": company.get("website"),
        "company_linkedin_url": socials.get("linkedin_url"),
        "company_linkedin_id": socials.get("linkedin_id"),
        "company_type": company.get("type"),
        "industry_primary": company.get("industry"),
        "industry_derived": company.get("industries"),
        "employee_range": company.get("employees"),
        "founded_year": company.get("founded_year"),
        "hq_locality": locality,
        "hq_country_code": country.get("code"),
        "description_raw": company.get("description"),
        "specialties": company.get("categories"),
        "annual_revenue_range": company.get("revenue"),
        "logo_url": company.get("logo_url"),
        "source_company_id": company.get("id"),
    }


def _canonical_company_from_leadmagic(company: dict[str, Any]) -> dict[str, Any]:
    hq = company.get("headquarter") or {}
    start = (company.get("employeeCountRange") or {}).get("start")
    end = (company.get("employeeCountRange") or {}).get("end")
    employee_range = company.get("employee_range")
    if not employee_range and (start is not None or end is not None):
        employee_range = f"{start}-{end}"
    return {
        "company_name": company.get("companyName"),
        "company_domain": _domain_from_website(company.get("websiteUrl")),
        "company_website": company.get("websiteUrl"),
        "company_linkedin_url": company.get("b2b_profile_url"),
        "company_type": company.get("ownership_status"),
        "industry_primary": company.get("industry"),
        "employee_count": company.get("employeeCount"),
        "employee_range": employee_range,
        "founded_year": company.get("founded_year"),
        "hq_locality": hq.get("city"),
        "hq_country_code": hq.get("country"),
        "description_raw": company.get("description"),
        "specialties": company.get("specialities"),
        "annual_revenue_range": company.get("revenue_formatted"),
        "follower_count": company.get("followerCount"),
        "logo_url": company.get("logo_url"),
        "source_company_id": company.get("companyId"),
    }


def _merge_company_profile(base: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in candidate.items():
        if value is None:
            continue
        if merged.get(key) in (None, "", [], {}):
            merged[key] = value
    return merged


def _provider_order() -> list[str]:
    settings = get_settings()
    parsed = [
        item.strip()
        for item in settings.company_enrich_profile_order.split(",")
        if item.strip()
    ]
    allowed = {"prospeo", "blitzapi", "companyenrich", "leadmagic"}
    filtered = [item for item in parsed if item in allowed]
    return filtered or ["prospeo", "blitzapi", "companyenrich", "leadmagic"]


async def _prospeo_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.prospeo_api_key:
        attempts.append(
            {"provider": "prospeo", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return None

    data = {
        "company_website": input_data.get("company_website") or input_data.get("company_domain"),
        "company_linkedin_url": input_data.get("company_linkedin_url"),
        "company_name": input_data.get("company_name"),
        "company_id": input_data.get("source_company_id"),
    }
    data = {k: v for k, v in data.items() if v}
    if not data:
        attempts.append(
            {"provider": "prospeo", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.prospeo.io/enrich-company",
            headers={"X-KEY": settings.prospeo_api_key, "Content-Type": "application/json"},
            json={"data": data},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        error_code = body.get("error_code")
        attempts.append(
            {
                "provider": "prospeo",
                "action": "company_enrich",
                "status": "not_found" if error_code == "NO_MATCH" else "failed",
                "http_status": res.status_code,
                "provider_status": error_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    company = body.get("company")
    found = bool(company and isinstance(company, dict))
    attempts.append(
        {
            "provider": "prospeo",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "provider_status": "free_enrichment" if body.get("free_enrichment") else "ok",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return company if found else None


async def _blitzapi_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.blitzapi_api_key:
        attempts.append(
            {"provider": "blitzapi", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return None

    linkedin_url = input_data.get("company_linkedin_url")
    domain = input_data.get("company_domain") or _domain_from_website(input_data.get("company_website"))
    start_ms = _now_ms()

    async with httpx.AsyncClient(timeout=30.0) as client:
        if not linkedin_url and domain:
            bridge_res = await client.post(
                "https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin",
                headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
                json={"domain": domain},
            )
            try:
                bridge_body = bridge_res.json()
            except Exception:  # noqa: BLE001
                bridge_body = {"raw": bridge_res.text}

            if bridge_res.status_code < 400 and bridge_body.get("found"):
                linkedin_url = bridge_body.get("company_linkedin_url")
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "found",
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )
            else:
                attempts.append(
                    {
                        "provider": "blitzapi",
                        "action": "domain_to_linkedin",
                        "status": "not_found" if bridge_res.status_code in {404, 422} else "failed",
                        "http_status": bridge_res.status_code,
                        "duration_ms": _now_ms() - start_ms,
                        "raw_response": bridge_body,
                    }
                )

        if not linkedin_url:
            attempts.append(
                {"provider": "blitzapi", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"}
            )
            return None

        res = await client.post(
            "https://api.blitz-api.ai/v2/enrichment/company",
            headers={"x-api-key": settings.blitzapi_api_key, "Content-Type": "application/json"},
            json={"company_linkedin_url": linkedin_url},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "blitzapi",
                "action": "company_enrich",
                "status": "not_found" if res.status_code == 404 else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    company = body.get("company")
    found = bool(body.get("found") and isinstance(company, dict))
    attempts.append(
        {
            "provider": "blitzapi",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return company if found else None


async def _companyenrich_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.companyenrich_api_key:
        attempts.append(
            {"provider": "companyenrich", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return None

    domain = input_data.get("company_domain") or _domain_from_website(input_data.get("company_website"))
    if not domain:
        attempts.append(
            {"provider": "companyenrich", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.get(
            "https://api.companyenrich.com/companies/enrich",
            params={"domain": domain},
            headers={"Authorization": f"Bearer {settings.companyenrich_api_key}", "accept": "application/json"},
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "companyenrich",
                "action": "company_enrich",
                "status": "not_found" if res.status_code == 404 else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    found = bool(body.get("id") or body.get("domain") or body.get("name"))
    attempts.append(
        {
            "provider": "companyenrich",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return body if found else None


async def _leadmagic_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.leadmagic_api_key:
        attempts.append(
            {"provider": "leadmagic", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_provider_api_key"}
        )
        return None

    payload = {
        "company_domain": input_data.get("company_domain") or _domain_from_website(input_data.get("company_website")),
        "profile_url": input_data.get("company_linkedin_url"),
        "company_name": input_data.get("company_name"),
    }
    payload = {k: v for k, v in payload.items() if v}
    if not payload:
        attempts.append(
            {"provider": "leadmagic", "action": "company_enrich", "status": "skipped", "skip_reason": "missing_required_inputs"}
        )
        return None

    start_ms = _now_ms()
    async with httpx.AsyncClient(timeout=30.0) as client:
        res = await client.post(
            "https://api.leadmagic.io/v1/companies/company-search",
            headers={"X-API-Key": settings.leadmagic_api_key, "Content-Type": "application/json"},
            json=payload,
        )
        try:
            body = res.json()
        except Exception:  # noqa: BLE001
            body = {"raw": res.text}

    if res.status_code >= 400:
        attempts.append(
            {
                "provider": "leadmagic",
                "action": "company_enrich",
                "status": "not_found" if res.status_code == 404 else "failed",
                "http_status": res.status_code,
                "duration_ms": _now_ms() - start_ms,
                "raw_response": body,
            }
        )
        return None

    found = bool(body.get("companyName") or body.get("companyId"))
    attempts.append(
        {
            "provider": "leadmagic",
            "action": "company_enrich",
            "status": "found" if found else "not_found",
            "provider_status": body.get("message"),
            "duration_ms": _now_ms() - start_ms,
            "raw_response": body,
        }
    )
    return body if found else None


async def execute_company_enrich_profile(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())
    profile: dict[str, Any] = {}
    sources: list[str] = []

    has_identifier = bool(
        input_data.get("company_domain")
        or input_data.get("company_website")
        or input_data.get("company_linkedin_url")
        or input_data.get("company_name")
        or input_data.get("source_company_id")
    )
    if not has_identifier:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.profile",
            "status": "failed",
            "missing_inputs": ["company_domain|company_website|company_linkedin_url|company_name|source_company_id"],
            "provider_attempts": attempts,
        }

    providers: dict[str, Any] = {
        "prospeo": _prospeo_company_enrich,
        "blitzapi": _blitzapi_company_enrich,
        "companyenrich": _companyenrich_company_enrich,
        "leadmagic": _leadmagic_company_enrich,
    }
    mapper: dict[str, Any] = {
        "prospeo": _canonical_company_from_prospeo,
        "blitzapi": _canonical_company_from_blitz,
        "companyenrich": _canonical_company_from_companyenrich,
        "leadmagic": _canonical_company_from_leadmagic,
    }

    for provider in _provider_order():
        adapter = providers.get(provider)
        if not adapter:
            continue
        raw_company = await adapter(input_data=input_data, attempts=attempts)
        if not raw_company:
            continue
        profile = _merge_company_profile(profile, mapper[provider](raw_company))
        sources.append(provider)

        input_data = {
            **input_data,
            "company_name": input_data.get("company_name") or profile.get("company_name"),
            "company_domain": input_data.get("company_domain") or profile.get("company_domain"),
            "company_website": input_data.get("company_website") or profile.get("company_website"),
            "company_linkedin_url": input_data.get("company_linkedin_url") or profile.get("company_linkedin_url"),
            "source_company_id": input_data.get("source_company_id") or profile.get("source_company_id"),
        }

    return {
        "run_id": run_id,
        "operation_id": "company.enrich.profile",
        "status": "found" if profile else "not_found",
        "output": {
            "company_profile": profile or None,
            "source_providers": sources,
        },
        "provider_attempts": attempts,
    }

