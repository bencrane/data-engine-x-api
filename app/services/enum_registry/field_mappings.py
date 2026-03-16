"""
Field mapping registry: maps generic (provider-agnostic) criteria field names
to provider-specific field names, valid enum values, and synonym tables.
"""

from typing import NamedTuple

from app.services.enum_registry.values import (
    PROSPEO_SENIORITIES,
    PROSPEO_DEPARTMENTS,
    PROSPEO_INDUSTRIES,
    PROSPEO_EMPLOYEE_RANGES,
    BLITZAPI_JOB_LEVELS,
    BLITZAPI_JOB_FUNCTIONS,
    BLITZAPI_INDUSTRIES,
    BLITZAPI_EMPLOYEE_RANGES,
    BLITZAPI_COMPANY_TYPES,
    BLITZAPI_CONTINENTS,
    BLITZAPI_SALES_REGIONS,
    BLITZAPI_COUNTRY_CODES,
)
from app.services.enum_registry.synonyms import (
    PROSPEO_SENIORITY_SYNONYMS,
    BLITZAPI_JOB_LEVEL_SYNONYMS,
    PROSPEO_DEPARTMENT_SYNONYMS,
    BLITZAPI_JOB_FUNCTION_SYNONYMS,
    PROSPEO_EMPLOYEE_RANGE_SYNONYMS,
    BLITZAPI_EMPLOYEE_RANGE_SYNONYMS,
    PROSPEO_INDUSTRY_SYNONYMS,
    BLITZAPI_INDUSTRY_SYNONYMS,
)


class FieldMapping(NamedTuple):
    provider_field: str  # the provider's actual API parameter name
    values: tuple[str, ...]  # valid enum values
    synonyms: dict[str, str] | None  # lowercase alias → exact provider value


FIELD_REGISTRY: dict[str, dict[str, FieldMapping]] = {
    "seniority": {
        "prospeo": FieldMapping(
            provider_field="person_seniority",
            values=PROSPEO_SENIORITIES,
            synonyms=PROSPEO_SENIORITY_SYNONYMS,
        ),
        "blitzapi": FieldMapping(
            provider_field="job_level",
            values=BLITZAPI_JOB_LEVELS,
            synonyms=BLITZAPI_JOB_LEVEL_SYNONYMS,
        ),
    },
    "department": {
        "prospeo": FieldMapping(
            provider_field="person_department",
            values=PROSPEO_DEPARTMENTS,
            synonyms=PROSPEO_DEPARTMENT_SYNONYMS,
        ),
        "blitzapi": FieldMapping(
            provider_field="job_function",
            values=BLITZAPI_JOB_FUNCTIONS,
            synonyms=BLITZAPI_JOB_FUNCTION_SYNONYMS,
        ),
    },
    "industry": {
        "prospeo": FieldMapping(
            provider_field="company_industry",
            values=PROSPEO_INDUSTRIES,
            synonyms=PROSPEO_INDUSTRY_SYNONYMS,
        ),
        "blitzapi": FieldMapping(
            provider_field="industry",
            values=BLITZAPI_INDUSTRIES,
            synonyms=BLITZAPI_INDUSTRY_SYNONYMS,
        ),
    },
    "employee_range": {
        "prospeo": FieldMapping(
            provider_field="company_employee_range",
            values=PROSPEO_EMPLOYEE_RANGES,
            synonyms=PROSPEO_EMPLOYEE_RANGE_SYNONYMS,
        ),
        "blitzapi": FieldMapping(
            provider_field="employee_range",
            values=BLITZAPI_EMPLOYEE_RANGES,
            synonyms=BLITZAPI_EMPLOYEE_RANGE_SYNONYMS,
        ),
    },
    "company_type": {
        "blitzapi": FieldMapping(
            provider_field="type",
            values=BLITZAPI_COMPANY_TYPES,
            synonyms=None,
        ),
    },
    "continent": {
        "blitzapi": FieldMapping(
            provider_field="continent",
            values=BLITZAPI_CONTINENTS,
            synonyms=None,
        ),
    },
    "sales_region": {
        "blitzapi": FieldMapping(
            provider_field="sales_region",
            values=BLITZAPI_SALES_REGIONS,
            synonyms=None,
        ),
    },
    "country_code": {
        "blitzapi": FieldMapping(
            provider_field="country_code",
            values=BLITZAPI_COUNTRY_CODES,
            synonyms=None,
        ),
    },
}


def get_field_mapping(generic_field: str, provider: str) -> FieldMapping | None:
    """Return the FieldMapping for a provider+field combination, or None."""
    return FIELD_REGISTRY.get(generic_field, {}).get(provider)
