from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_enrich import CompanyEnrichProfileOutput
from app.providers import blitzapi, companyenrich, leadmagic, prospeo


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
    data = {
        "company_website": input_data.get("company_website") or input_data.get("company_domain"),
        "company_linkedin_url": input_data.get("company_linkedin_url"),
        "company_name": input_data.get("company_name"),
        "company_id": input_data.get("source_company_id"),
    }
    result = await prospeo.enrich_company(api_key=settings.prospeo_api_key, data=data)
    attempts.append(result["attempt"])
    return result.get("mapped")


async def _blitzapi_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    linkedin_url = input_data.get("company_linkedin_url")
    domain = input_data.get("company_domain") or _domain_from_website(input_data.get("company_website"))
    if not linkedin_url and domain:
        bridge = await blitzapi.domain_to_linkedin(api_key=settings.blitzapi_api_key, domain=domain)
        attempts.append(bridge["attempt"])
        linkedin_url = (bridge.get("mapped") or {}).get("company_linkedin_url")
    result = await blitzapi.enrich_company(
        api_key=settings.blitzapi_api_key,
        company_linkedin_url=linkedin_url,
    )
    attempts.append(result["attempt"])
    return result.get("mapped")


async def _companyenrich_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    domain = input_data.get("company_domain") or _domain_from_website(input_data.get("company_website"))
    result = await companyenrich.enrich_company(
        api_key=settings.companyenrich_api_key,
        domain=domain,
    )
    attempts.append(result["attempt"])
    return result.get("mapped")


async def _leadmagic_company_enrich(
    *,
    input_data: dict[str, Any],
    attempts: list[dict[str, Any]],
) -> dict[str, Any] | None:
    settings = get_settings()
    payload = {
        "company_domain": input_data.get("company_domain") or _domain_from_website(input_data.get("company_website")),
        "profile_url": input_data.get("company_linkedin_url"),
        "company_name": input_data.get("company_name"),
    }
    result = await leadmagic.enrich_company(api_key=settings.leadmagic_api_key, payload=payload)
    attempts.append(result["attempt"])
    return result.get("mapped")


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

    output = CompanyEnrichProfileOutput.model_validate(
        {
            "company_profile": profile or None,
            "source_providers": sources,
        }
    ).model_dump()
    return {
        "run_id": run_id,
        "operation_id": "company.enrich.profile",
        "status": "found" if profile else "not_found",
        "output": output,
        "provider_attempts": attempts,
    }

