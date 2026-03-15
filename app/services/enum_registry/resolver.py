"""
Enum resolution engine.

Resolves user-facing criteria values into exact, case-sensitive provider
enum values using a cascade: exact match → synonym → fuzzy → no match.
"""

import difflib
from typing import NamedTuple

from app.services.enum_registry.field_mappings import FIELD_REGISTRY, get_field_mapping
from app.services.enum_registry.values import VALUES_REGISTRY


class ResolveResult(NamedTuple):
    value: str | None  # the resolved provider-specific enum value, or None
    provider_field: str | None  # the provider's API parameter name
    match_type: str  # "exact", "synonym", "fuzzy", "none"
    confidence: float  # 1.0 for exact/synonym, 0.0-1.0 for fuzzy, 0.0 for none


def resolve_enum(
    provider: str,
    generic_field: str,
    user_input: str,
    *,
    fuzzy_threshold: float = 0.6,
    fuzzy_max_results: int = 1,
) -> ResolveResult:
    """
    Resolve a user-facing value into the exact provider enum value.

    Resolution cascade (returns first match):
    1. Exact match (case-insensitive against valid values)
    2. Synonym match (lowercase lookup in synonym table)
    3. Fuzzy match (difflib.get_close_matches)
    4. No match
    """
    mapping = get_field_mapping(generic_field, provider)
    if mapping is None:
        return ResolveResult(
            value=None,
            provider_field=None,
            match_type="none",
            confidence=0.0,
        )

    provider_field = mapping.provider_field
    synonyms = mapping.synonyms
    input_lower = user_input.lower()

    # Use pre-built lookup structures from values.py
    registry_key = (provider, generic_field)
    values, lookup = VALUES_REGISTRY[registry_key]

    # 1. Exact match (case-insensitive)
    if input_lower in lookup:
        return ResolveResult(
            value=lookup[input_lower],
            provider_field=provider_field,
            match_type="exact",
            confidence=1.0,
        )

    # 2. Synonym match
    if synonyms and input_lower in synonyms:
        return ResolveResult(
            value=synonyms[input_lower],
            provider_field=provider_field,
            match_type="synonym",
            confidence=1.0,
        )

    # 3. Fuzzy match
    matches = difflib.get_close_matches(
        input_lower, list(lookup), n=fuzzy_max_results, cutoff=fuzzy_threshold
    )
    if matches:
        best_lower = matches[0]
        best_original = lookup[best_lower]
        ratio = difflib.SequenceMatcher(None, input_lower, best_lower).ratio()
        return ResolveResult(
            value=best_original,
            provider_field=provider_field,
            match_type="fuzzy",
            confidence=round(ratio, 4),
        )

    # 4. No match
    return ResolveResult(
        value=None,
        provider_field=provider_field,
        match_type="none",
        confidence=0.0,
    )


def resolve_criteria(
    provider: str,
    criteria: dict[str, str],
    *,
    fuzzy_threshold: float = 0.6,
) -> dict[str, ResolveResult]:
    """
    Resolve a batch of generic criteria into provider-specific enum values.

    Takes {generic_field: user_input} and returns {generic_field: ResolveResult}.
    """
    return {
        field: resolve_enum(provider, field, value, fuzzy_threshold=fuzzy_threshold)
        for field, value in criteria.items()
    }


def list_supported_fields(provider: str) -> list[str]:
    """Return generic field names supported for this provider."""
    return [
        field
        for field, providers in FIELD_REGISTRY.items()
        if provider in providers
    ]


def list_valid_values(provider: str, generic_field: str) -> tuple[str, ...] | None:
    """Return the valid enum values for a provider+field combination."""
    mapping = get_field_mapping(generic_field, provider)
    if mapping is None:
        return None
    return mapping.values
