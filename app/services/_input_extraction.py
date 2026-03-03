"""Unified input extraction from input_data + cumulative_context.

Every operation service function should use these helpers instead of
defining its own alias tuples. When a new field name variant appears
in pipeline context, add it here ONCE and every operation benefits.
"""

from __future__ import annotations

from typing import Any


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _as_list(value: Any) -> list[Any] | None:
    if isinstance(value, list):
        return value
    return None


def _ctx(input_data: dict[str, Any]) -> dict[str, Any]:
    context = input_data.get("cumulative_context")
    if isinstance(context, dict):
        return context
    return {}


def _options(input_data: dict[str, Any]) -> dict[str, Any]:
    opts = input_data.get("options")
    if isinstance(opts, dict):
        return opts
    return {}


def extract_str(input_data: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = _as_str(input_data.get(alias))
        if value:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_str(context.get(alias))
        if value:
            return value
    opts = _options(input_data)
    for alias in aliases:
        value = _as_str(opts.get(alias))
        if value:
            return value
    return None


def extract_list(input_data: dict[str, Any], aliases: tuple[str, ...]) -> list[Any] | None:
    for alias in aliases:
        value = _as_list(input_data.get(alias))
        if value is not None:
            return value
    context = _ctx(input_data)
    for alias in aliases:
        value = _as_list(context.get(alias))
        if value is not None:
            return value
    opts = _options(input_data)
    for alias in aliases:
        value = _as_list(opts.get(alias))
        if value is not None:
            return value
    return None


# ---------------------------------------------------------------------------
# Canonical alias maps — THE SINGLE SOURCE OF TRUTH for field name variants.
# When a new variant appears (e.g., a provider returns "companyName" instead
# of "company_name"), add it to the appropriate tuple below.
# ---------------------------------------------------------------------------
COMPANY_NAME = (
    "company_name",
    "current_company_name",
    "canonical_name",
    "name",
    "companyName",
    "matched_name",
)
COMPANY_DOMAIN = (
    "domain",
    "company_domain",
    "canonical_domain",
    "customer_domain",
    "current_company_domain",
)
COMPANY_WEBSITE = ("company_website", "website", "website_url", "websiteUrl")
COMPANY_LINKEDIN_URL = (
    "company_linkedin_url",
    "linkedin_url",
    "customer_linkedin_url",
    "current_company_linkedin_url",
)
COMPANY_LINKEDIN_ID = ("company_linkedin_id", "org_id", "orgId", "linkedin_id")
COMPANY_DESCRIPTION = ("description", "description_raw", "company_description", "about")
COMPANY_INDUSTRY = ("industry", "industry_primary", "current_company_industry")
COMPANY_LOCATION = ("hq_locality", "hq_country_code", "current_company_location", "geo_region")

PERSON_LINKEDIN_URL = ("person_linkedin_url", "linkedin_url", "profile_url")
PERSON_FULL_NAME = ("full_name", "person_full_name", "name")
PERSON_EMAIL = ("work_email", "email")
PERSON_FIRST_NAME = ("first_name", "person_first_name")
PERSON_LAST_NAME = ("last_name", "person_last_name")

ICP_CRITERION = ("criterion", "icp_criterion")
ICP_TITLES = ("champion_titles", "titles", "icp_titles")
CUSTOMERS = ("customers",)

SALES_NAV_URL = ("sales_nav_url", "salesnav_url")
PRICING_PAGE_URL = ("pricing_page_url",)


def extract_company_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_NAME)


def extract_domain(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_DOMAIN)


def extract_company_website(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_WEBSITE)


def extract_company_linkedin_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_LINKEDIN_URL)


def extract_company_linkedin_id(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_LINKEDIN_ID)


def extract_description(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, COMPANY_DESCRIPTION)


def extract_criterion(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, ICP_CRITERION)


def extract_person_linkedin_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_LINKEDIN_URL)


def extract_person_full_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_FULL_NAME)


def extract_person_email(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_EMAIL)


def extract_person_first_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_FIRST_NAME)


def extract_person_last_name(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PERSON_LAST_NAME)


def extract_sales_nav_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, SALES_NAV_URL)


def extract_pricing_page_url(input_data: dict[str, Any]) -> str | None:
    return extract_str(input_data, PRICING_PAGE_URL)


def extract_customers(input_data: dict[str, Any]) -> list[Any] | None:
    return extract_list(input_data, CUSTOMERS)


def extract_titles(input_data: dict[str, Any]) -> list[Any] | None:
    return extract_list(input_data, ICP_TITLES)
