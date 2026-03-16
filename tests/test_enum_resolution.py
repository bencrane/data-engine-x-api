"""Tests for the provider enum resolution layer."""

from app.services.enum_registry.resolver import (
    resolve_enum,
    resolve_criteria,
    list_supported_fields,
    list_valid_values,
)


# ---------------------------------------------------------------------------
# Exact matching
# ---------------------------------------------------------------------------


def test_exact_match_case_insensitive():
    result = resolve_enum("blitzapi", "seniority", "vp")
    assert result.value == "VP"
    assert result.match_type == "exact"
    assert result.confidence == 1.0


def test_exact_match_preserves_casing():
    result = resolve_enum("blitzapi", "department", "Engineering")
    assert result.value == "Engineering"
    assert result.match_type == "exact"
    assert result.confidence == 1.0


def test_exact_match_prospeo_seniority():
    result = resolve_enum("prospeo", "seniority", "director")
    assert result.value == "Director"
    assert result.match_type == "exact"
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Synonym matching
# ---------------------------------------------------------------------------


def test_synonym_vp_to_prospeo():
    result = resolve_enum("prospeo", "seniority", "vp")
    assert result.value == "Vice President"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


def test_synonym_csuite_to_blitzapi():
    result = resolve_enum("blitzapi", "seniority", "c-suite")
    assert result.value == "C-Team"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


def test_synonym_sales_to_blitzapi_function():
    result = resolve_enum("blitzapi", "department", "sales")
    assert result.value == "Sales & Business Development"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


def test_synonym_employee_range_cross_provider():
    result = resolve_enum("blitzapi", "employee_range", "1001-2000")
    assert result.value == "1001-5000"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def test_fuzzy_match_close_spelling():
    result = resolve_enum("prospeo", "seniority", "Vice Pres")
    assert result.value == "Vice President"
    assert result.match_type == "fuzzy"
    assert result.confidence > 0.6


def test_fuzzy_match_industry():
    result = resolve_enum("blitzapi", "industry", "Computer Softwar")
    assert result.value == "Computer Software"
    assert result.match_type == "fuzzy"
    assert result.confidence > 0.6


# ---------------------------------------------------------------------------
# No match
# ---------------------------------------------------------------------------


def test_no_match_gibberish():
    result = resolve_enum("blitzapi", "seniority", "xyzzy123")
    assert result.value is None
    assert result.match_type == "none"
    assert result.confidence == 0.0


def test_no_match_unsupported_field():
    result = resolve_enum("prospeo", "company_type", "Private")
    assert result.value is None
    assert result.provider_field is None
    assert result.match_type == "none"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Batch resolution
# ---------------------------------------------------------------------------


def test_resolve_criteria_batch():
    results = resolve_criteria("blitzapi", {
        "seniority": "VP",
        "department": "Sales",
        "employee_range": "51-200",
    })
    assert len(results) == 3
    assert results["seniority"].value == "VP"
    assert results["department"].value == "Sales & Business Development"
    assert results["employee_range"].value == "51-200"
    assert all(r.value is not None for r in results.values())


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------


def test_list_supported_fields():
    fields = list_supported_fields("blitzapi")
    expected = [
        "seniority", "department", "industry", "employee_range",
        "company_type", "continent", "sales_region", "country_code",
    ]
    for f in expected:
        assert f in fields


def test_list_valid_values():
    values = list_valid_values("blitzapi", "seniority")
    assert values is not None
    assert len(values) == 6
    assert "VP" in values
    assert "C-Team" in values
    assert "Staff" in values


# ---------------------------------------------------------------------------
# Numeric range resolver
# ---------------------------------------------------------------------------


def test_numeric_range_exact_bucket_match():
    result = resolve_enum("blitzapi", "employee_range", "51-200")
    assert result.value == "51-200"
    assert result.match_type == "exact"
    assert result.confidence == 1.0


def test_numeric_range_close_fit():
    result = resolve_enum("blitzapi", "employee_range", "50-200")
    # BlitzAPI "51-200" covers nearly all of 50-200; "11-50" overlap is trivial (1 unit)
    assert result.value == "51-200"
    assert result.match_type == "numeric"


def test_numeric_range_partial_overlap():
    result = resolve_enum("blitzapi", "employee_range", "100-300")
    # Spans two BlitzAPI buckets: "51-200" (overlap 101) and "201-500" (overlap 100)
    assert result.value == ["51-200", "201-500"]
    assert result.match_type == "numeric"


def test_numeric_range_plus_format():
    result = resolve_enum("blitzapi", "employee_range", "500+")
    assert result.value is not None
    assert result.match_type == "numeric"


def test_numeric_range_single_number():
    result = resolve_enum("blitzapi", "employee_range", "150")
    assert result.value == "51-200"
    assert result.match_type == "numeric"


def test_numeric_range_with_word_suffix():
    result = resolve_enum("blitzapi", "employee_range", "50-200 employees")
    assert result.value == "51-200"
    assert result.match_type == "numeric"


def test_numeric_range_prospeo_multi_bucket():
    # Prospeo has finer buckets: 51-100, 101-200
    result = resolve_enum("prospeo", "employee_range", "50-200")
    # User range 50-200 spans both Prospeo buckets
    assert result.value == ["51-100", "101-200"]
    assert result.match_type == "numeric"


def test_word_range_still_uses_synonym():
    result = resolve_enum("blitzapi", "employee_range", "enterprise")
    assert result.value == "10001+"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


# ---------------------------------------------------------------------------
# Industry synonym resolution
# ---------------------------------------------------------------------------


def test_industry_synonym_staffing():
    result = resolve_enum("blitzapi", "industry", "staffing")
    assert result.value == "Staffing and Recruiting"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


def test_industry_synonym_saas():
    result = resolve_enum("prospeo", "industry", "saas")
    assert result.value == "Software Development"
    assert result.match_type == "synonym"
    assert result.confidence == 1.0


def test_industry_exact_still_works():
    result = resolve_enum("blitzapi", "industry", "Staffing and Recruiting")
    assert result.value == "Staffing and Recruiting"
    assert result.match_type == "exact"
    assert result.confidence == 1.0
