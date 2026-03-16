"""
Enum resolution engine.

Resolves user-facing criteria values into exact, case-sensitive provider
enum values using a cascade: exact match → synonym → numeric (for ranges) → fuzzy → no match.
"""

import difflib
import math
import re
from typing import NamedTuple

from app.services.enum_registry.field_mappings import FIELD_REGISTRY, get_field_mapping
from app.services.enum_registry.values import VALUES_REGISTRY


class ResolveResult(NamedTuple):
    value: str | None  # the resolved provider-specific enum value, or None
    provider_field: str | None  # the provider's API parameter name
    match_type: str  # "exact", "synonym", "numeric", "fuzzy", "none"
    confidence: float  # 1.0 for exact/synonym, 0.0-1.0 for fuzzy/numeric, 0.0 for none


# ---------------------------------------------------------------------------
# Numeric range resolver (for employee_range)
# ---------------------------------------------------------------------------

_RANGE_STRIP_WORDS = re.compile(r'\b(employees?|people|persons?)\b', re.IGNORECASE)


def _parse_range(s: str) -> tuple[int, float] | None:
    """Parse a range string into (min, max). Returns None if unparseable."""
    cleaned = _RANGE_STRIP_WORDS.sub("", s).replace(",", "").strip()

    # "N+" or "Nplus"
    m = re.match(r'^(\d+)\s*\+$', cleaned) or re.match(r'^(\d+)\s*plus$', cleaned, re.IGNORECASE)
    if m:
        return (int(m.group(1)), math.inf)

    # "N-M"
    m = re.match(r'^(\d+)\s*-\s*(\d+)$', cleaned)
    if m:
        return (int(m.group(1)), int(m.group(2)))

    # Single number
    m = re.match(r'^(\d+)$', cleaned)
    if m:
        n = int(m.group(1))
        return (n, n)

    return None


def _range_overlap(a_min: int, a_max: float, b_min: int, b_max: float) -> float:
    """Calculate overlap size between two ranges."""
    lo = max(a_min, b_min)
    hi = min(a_max, b_max)
    if lo > hi:
        return 0.0
    if math.isinf(hi):
        return 10_000.0  # large finite stand-in for unbounded overlap
    return float(hi - lo + 1)


def _range_distance(a_min: int, a_max: float, b_min: int, b_max: float) -> float:
    """Distance between two non-overlapping ranges (0 if they overlap)."""
    if a_max < b_min:
        return float(b_min - a_max)
    if b_max < a_min:
        return float(a_min - b_max)
    return 0.0


def _range_span(lo: int, hi: float) -> float:
    if math.isinf(hi):
        return 10_000.0
    return float(hi - lo + 1)


def _resolve_numeric_range(
    values: tuple[str, ...],
    user_input: str,
    provider_field: str,
) -> ResolveResult | None:
    """Resolve a numeric range input against provider buckets.

    Returns None if the user input cannot be parsed as a numeric range,
    letting the caller fall through to fuzzy matching.
    """
    user_range = _parse_range(user_input)
    if user_range is None:
        return None

    u_min, u_max = user_range

    # Parse all provider buckets
    parsed_buckets: list[tuple[str, int, float]] = []
    for bucket_str in values:
        parsed = _parse_range(bucket_str)
        if parsed:
            parsed_buckets.append((bucket_str, parsed[0], parsed[1]))

    if not parsed_buckets:
        return None

    # 1. Check containment: user range fits entirely within a bucket
    best_contained: tuple[str, float] | None = None
    for bucket_str, b_min, b_max in parsed_buckets:
        if b_min <= u_min and u_max <= b_max:
            span = _range_span(b_min, b_max)
            if best_contained is None or span < best_contained[1]:
                best_contained = (bucket_str, span)

    if best_contained is not None:
        return ResolveResult(
            value=best_contained[0],
            provider_field=provider_field,
            match_type="numeric",
            confidence=1.0,
        )

    # 2. Best overlap
    best_overlap_val = 0.0
    best_overlap_bucket: str | None = None
    for bucket_str, b_min, b_max in parsed_buckets:
        overlap = _range_overlap(u_min, u_max, b_min, b_max)
        if overlap > best_overlap_val:
            best_overlap_val = overlap
            best_overlap_bucket = bucket_str

    if best_overlap_bucket is not None and best_overlap_val > 0:
        user_span = _range_span(u_min, u_max)
        confidence = round(min(best_overlap_val / user_span, 1.0), 4) if user_span > 0 else 0.5
        return ResolveResult(
            value=best_overlap_bucket,
            provider_field=provider_field,
            match_type="numeric",
            confidence=confidence,
        )

    # 3. Nearest boundary
    best_dist = math.inf
    best_near_bucket: str = parsed_buckets[0][0]
    for bucket_str, b_min, b_max in parsed_buckets:
        dist = _range_distance(u_min, u_max, b_min, b_max)
        if dist < best_dist:
            best_dist = dist
            best_near_bucket = bucket_str

    return ResolveResult(
        value=best_near_bucket,
        provider_field=provider_field,
        match_type="numeric",
        confidence=round(max(0.3, 1.0 - best_dist / 100.0), 4),
    )


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

    # 3. Numeric range resolver (employee_range only)
    if generic_field == "employee_range":
        numeric_result = _resolve_numeric_range(values, user_input, provider_field)
        if numeric_result is not None:
            return numeric_result

    # 4. Fuzzy match
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

    # 5. No match
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
