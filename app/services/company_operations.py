from __future__ import annotations

import uuid
from typing import Any

from app.config import get_settings
from app.contracts.company_enrich import (
    CardRevenueOutput,
    CompanyEnrichProfileOutput,
    EcommerceEnrichOutput,
    FMCSACarrierEnrichOutput,
    TechnographicsOutput,
)
from app.providers import blitzapi, companyenrich, enigma, fmcsa, leadmagic, prospeo, storeleads_enrich


def _as_non_empty_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _domain_from_website(website: Any) -> str | None:
    if not isinstance(website, str):
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


def _extract_dot_number(input_data: dict[str, Any]) -> str | None:
    direct = _as_non_empty_str(input_data.get("dot_number")) or _as_non_empty_str(input_data.get("dotNumber"))
    if direct:
        return direct

    company_profile = _as_dict(input_data.get("company_profile"))
    from_profile = _as_non_empty_str(company_profile.get("dot_number")) or _as_non_empty_str(company_profile.get("dotNumber"))
    if from_profile:
        return from_profile

    output = _as_dict(input_data.get("output"))
    from_output = _as_non_empty_str(output.get("dot_number")) or _as_non_empty_str(output.get("dotNumber"))
    if from_output:
        return from_output

    for collection in [
        _as_list(input_data.get("results")),
        _as_list(output.get("results")),
        _as_list(_as_dict(input_data.get("company_search")).get("results")),
    ]:
        for item in collection:
            item_dict = _as_dict(item)
            candidate = _as_non_empty_str(item_dict.get("dot_number")) or _as_non_empty_str(item_dict.get("dotNumber"))
            if candidate:
                return candidate

    return None


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
    company_website = _as_non_empty_str(input_data.get("company_website"))
    company_domain = _as_non_empty_str(input_data.get("company_domain"))
    company_linkedin_url = _as_non_empty_str(input_data.get("company_linkedin_url"))
    company_name = _as_non_empty_str(input_data.get("company_name"))
    source_company_id = _as_non_empty_str(input_data.get("source_company_id"))
    data = {
        "company_website": company_website or company_domain,
        "company_linkedin_url": company_linkedin_url,
        "company_name": company_name,
        "company_id": source_company_id,
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
    linkedin_url = _as_non_empty_str(input_data.get("company_linkedin_url"))
    domain = _as_non_empty_str(input_data.get("company_domain")) or _domain_from_website(input_data.get("company_website"))
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
    domain = _as_non_empty_str(input_data.get("company_domain")) or _domain_from_website(input_data.get("company_website"))
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
        "company_domain": _as_non_empty_str(input_data.get("company_domain")) or _domain_from_website(input_data.get("company_website")),
        "profile_url": _as_non_empty_str(input_data.get("company_linkedin_url")),
        "company_name": _as_non_empty_str(input_data.get("company_name")),
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

    current_input: dict[str, Any] = {
        "company_domain": _as_non_empty_str(input_data.get("company_domain")),
        "company_website": _as_non_empty_str(input_data.get("company_website")),
        "company_linkedin_url": _as_non_empty_str(input_data.get("company_linkedin_url")),
        "company_name": _as_non_empty_str(input_data.get("company_name")),
        "source_company_id": _as_non_empty_str(input_data.get("source_company_id")),
    }

    has_identifier = bool(
        current_input.get("company_domain")
        or current_input.get("company_website")
        or current_input.get("company_linkedin_url")
        or current_input.get("company_name")
        or current_input.get("source_company_id")
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
        raw_company = await adapter(input_data=current_input, attempts=attempts)
        if not raw_company:
            continue
        profile = _merge_company_profile(profile, mapper[provider](raw_company))
        sources.append(provider)

        current_input = {
            **current_input,
            "company_name": current_input.get("company_name") or _as_non_empty_str(profile.get("company_name")),
            "company_domain": current_input.get("company_domain") or _as_non_empty_str(profile.get("company_domain")),
            "company_website": current_input.get("company_website") or _as_non_empty_str(profile.get("company_website")),
            "company_linkedin_url": current_input.get("company_linkedin_url") or _as_non_empty_str(profile.get("company_linkedin_url")),
            "source_company_id": current_input.get("source_company_id") or _as_non_empty_str(profile.get("source_company_id")),
        }

    try:
        output = CompanyEnrichProfileOutput.model_validate(
            {
                "company_profile": profile or None,
                "source_providers": sources,
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.profile",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }
    # Flatten profile fields to top level so downstream operations
    # can read company_name, company_domain, etc. from cumulative context.
    flat_output = {**(profile or {}), **output}
    return {
        "run_id": run_id,
        "operation_id": "company.enrich.profile",
        "status": "found" if profile else "not_found",
        "output": flat_output,
        "provider_attempts": attempts,
    }


async def execute_company_enrich_technographics(
    *,
    input_data: dict,
) -> dict:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    company_domain = _as_non_empty_str(input_data.get("company_domain"))
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.technographics",
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    adapter_result = await leadmagic.get_technographics(
        api_key=settings.leadmagic_api_key,
        company_domain=company_domain,
    )
    attempts.append(adapter_result["attempt"])

    mapped = adapter_result.get("mapped") or {}
    try:
        validated_output = TechnographicsOutput.model_validate(
            {
                **mapped,
                "source_provider": "leadmagic",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.technographics",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    status = adapter_result["attempt"].get("status", "failed")
    return {
        "run_id": run_id,
        "operation_id": "company.enrich.technographics",
        "status": status,
        "output": {
            **validated_output,
            "technologies": validated_output["technologies"],
            "categories": validated_output.get("categories"),
            "technology_count": validated_output["technology_count"],
        },
        "provider_attempts": attempts,
    }


async def execute_company_enrich_ecommerce(
    *,
    input_data: dict,
) -> dict:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    company_domain = _as_non_empty_str(input_data.get("company_domain"))
    if not company_domain:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.ecommerce",
            "status": "failed",
            "missing_inputs": ["company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    adapter_result = await storeleads_enrich.enrich_ecommerce(
        api_key=settings.storeleads_api_key,
        domain=company_domain,
    )
    attempts.append(adapter_result["attempt"])

    mapped = adapter_result.get("mapped")
    if mapped is None:
        status = adapter_result["attempt"].get("status", "failed")
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.ecommerce",
            "status": status,
            "provider_attempts": attempts,
        }

    try:
        validated_output = EcommerceEnrichOutput.model_validate(
            {
                **mapped,
                "source_provider": "storeleads",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.ecommerce",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    status = adapter_result["attempt"].get("status", "failed")
    return {
        "run_id": run_id,
        "operation_id": "company.enrich.ecommerce",
        "status": status,
        "output": {
            **validated_output,
        },
        "provider_attempts": attempts,
    }


async def execute_company_enrich_fmcsa(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())
    dot_number = _extract_dot_number(input_data)
    if not dot_number:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.fmcsa",
            "status": "failed",
            "missing_inputs": ["dot_number"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    adapter_result = await fmcsa.enrich_carrier(
        api_key=settings.fmcsa_api_key,
        dot_number=dot_number,
    )
    attempts.append(adapter_result["attempt"])

    mapped = adapter_result.get("mapped")
    if mapped is None:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.fmcsa",
            "status": adapter_result["attempt"].get("status", "failed"),
            "provider_attempts": attempts,
        }

    try:
        validated_output = FMCSACarrierEnrichOutput.model_validate(
            {
                **mapped,
                "source_provider": "fmcsa",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.fmcsa",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": "company.enrich.fmcsa",
        "status": adapter_result["attempt"].get("status", "failed"),
        "output": {
            **validated_output,
        },
        "provider_attempts": attempts,
    }


async def execute_company_enrich_card_revenue(
    *,
    input_data: dict,
) -> dict:
    attempts: list[dict[str, Any]] = []
    run_id = str(uuid.uuid4())

    company_name = _as_non_empty_str(input_data.get("company_name"))
    company_domain = _as_non_empty_str(input_data.get("company_domain")) or _domain_from_website(
        input_data.get("company_website")
    )

    if not company_name and not company_domain:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.card_revenue",
            "status": "failed",
            "missing_inputs": ["company_name|company_domain"],
            "provider_attempts": attempts,
        }

    settings = get_settings()
    adapter_result = await enigma.enrich_card_revenue(
        api_key=settings.enigma_api_key,
        company_name=company_name,
        company_domain=company_domain,
    )
    attempts.append(adapter_result["attempt"])

    mapped = adapter_result.get("mapped")
    status = adapter_result["attempt"].get("status", "failed")
    if mapped is None:
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.card_revenue",
            "status": status,
            "provider_attempts": attempts,
        }

    try:
        validated_output = CardRevenueOutput.model_validate(
            {
                **mapped,
                "source_provider": "enigma",
            }
        ).model_dump()
    except Exception as exc:  # noqa: BLE001
        return {
            "run_id": run_id,
            "operation_id": "company.enrich.card_revenue",
            "status": "failed",
            "provider_attempts": attempts,
            "error": {
                "code": "output_validation_failed",
                "message": str(exc),
            },
        }

    return {
        "run_id": run_id,
        "operation_id": "company.enrich.card_revenue",
        "status": status,
        "output": {
            **validated_output,
        },
        "provider_attempts": attempts,
    }

