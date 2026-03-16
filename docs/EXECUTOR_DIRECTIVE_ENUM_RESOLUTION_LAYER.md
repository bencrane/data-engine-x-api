**Directive: Provider Enum Resolution Layer**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Both Prospeo and BlitzAPI require exact, case-sensitive enum values for search filters. If a caller passes `"vp"` but the provider expects `"VP"` or `"Vice President"`, the query silently returns zero results. We need a resolution layer that translates generic user-facing criteria into valid provider-specific enum values. This layer will be consumed by a future intent-based search endpoint — this directive builds the resolution infrastructure only.

**The problem in concrete terms:**

A chat frontend sends: `{"seniority": "VP", "department": "Sales", "employee_count": "500-1000"}`

- For Prospeo, `"VP"` must become `"Vice President"` (the `person_seniority` filter), `"Sales"` maps to department sub-values, and `"500-1000"` must become `"501-1000"`.
- For BlitzAPI, `"VP"` stays `"VP"` (the `job_level` filter), `"Sales"` must become `"Sales & Business Development"` (the `job_function` filter), and `"500-1000"` must become `"501-1000"`.

The caller should not know any of this. The resolution layer handles it.

**Existing code to read:**

- `docs/api-reference-docs/prospeo/Values List/` — all files. Extract the JSON arrays from each. Key files:
  - `08-seniorities.md` — 10 seniority values
  - `02-departments.md` — hierarchical departments with ~170 sub-departments; has both "Normal Departments" and "Headcount Growth Departments" JSON arrays. Use the Normal Departments array.
  - `05-industries.md` — ~256 industry values
  - `03-employee-ranges.md` — 11 employee range tiers
- `docs/api-reference-docs/blitzapi/Values List/` — all files. Extract the JSON arrays from each. Key files:
  - `03-job-levels.md` — 6 job level values (maps to seniority)
  - `04-job-functions.md` — 22 job function values (maps to department)
  - `09-industry.md` — ~534 industry values (LinkedIn taxonomy)
  - `02-employee-range.md` — 8 employee range tiers
  - `07-company-types.md` — 10 company type values
  - `06-continents.md` — 7 continent values
  - `05-sales-regions.md` — 4 sales region values
  - `08-country-codes.md` — ISO alpha-2 codes + `"WORLD"`
- `docs/api-reference-docs/prospeo/02-search/04-filters-documentation.md` — Prospeo filter field names and structure
- `app/providers/prospeo.py` — `search_companies()` and `search_people()` to see how filters are currently passed
- `app/providers/blitzapi.py` — `search_employees()`, `search_icp_waterfall()`, `search_companies()` to see how filters are currently passed
- `app/services/search_operations.py` — `_build_prospeo_filters()` and the person/company search flows to understand current filter construction

---

### Deliverable 1: Enum Values Constants

Create `app/services/enum_registry/__init__.py` (empty, makes it a package).

Create `app/services/enum_registry/values.py`:

Extract the JSON arrays from the Values List markdown files and define them as Python constants. Use `tuple[str, ...]` (immutable) for each.

**Required constants (copy values exactly from the JSON arrays in the docs):**

```
# Prospeo
PROSPEO_SENIORITIES          # from 08-seniorities.md
PROSPEO_DEPARTMENTS           # from 02-departments.md — Normal Departments JSON only
PROSPEO_INDUSTRIES            # from 05-industries.md
PROSPEO_EMPLOYEE_RANGES       # from 03-employee-ranges.md

# BlitzAPI
BLITZAPI_JOB_LEVELS           # from 03-job-levels.md
BLITZAPI_JOB_FUNCTIONS        # from 04-job-functions.md
BLITZAPI_INDUSTRIES           # from 09-industry.md (all ~534 values)
BLITZAPI_EMPLOYEE_RANGES      # from 02-employee-range.md
BLITZAPI_COMPANY_TYPES        # from 07-company-types.md
BLITZAPI_CONTINENTS           # from 06-continents.md
BLITZAPI_SALES_REGIONS        # from 05-sales-regions.md
BLITZAPI_COUNTRY_CODES        # from 08-country-codes.md
```

Also create a lowercase lookup `frozenset` for each constant (used for case-insensitive exact matching):

```python
_PROSPEO_SENIORITIES_LOWER = frozenset(v.lower() for v in PROSPEO_SENIORITIES)
```

And a reverse lookup dict mapping lowercase → original casing:

```python
_PROSPEO_SENIORITIES_LOOKUP = {v.lower(): v for v in PROSPEO_SENIORITIES}
```

This pattern (tuple + frozenset + reverse dict) applies to every constant.

**Important:** Copy values exactly as they appear in the JSON arrays. Do not normalize, deduplicate, or edit them. If a value has a semicolon, ampersand, or slash, keep it as-is.

Commit standalone.

### Deliverable 2: Synonym Tables

Create `app/services/enum_registry/synonyms.py`:

Define synonym mappings for fields where the cross-provider translation is non-obvious. Each synonym table maps a lowercase alias to the exact provider value.

**Seniority synonyms (most critical — these are the highest-value mappings):**

```python
PROSPEO_SENIORITY_SYNONYMS: dict[str, str] = {
    "vp": "Vice President",
    "vice president": "Vice President",
    "c-suite": "C-Suite",
    "c-team": "C-Suite",
    "csuite": "C-Suite",
    "cxo": "C-Suite",
    "ceo": "C-Suite",
    "cfo": "C-Suite",
    "cto": "C-Suite",
    "coo": "C-Suite",
    "cro": "C-Suite",
    "cmo": "C-Suite",
    "founder": "Founder/Owner",
    "owner": "Founder/Owner",
    "co-founder": "Founder/Owner",
    "cofounder": "Founder/Owner",
    "head": "Head",
    "head of": "Head",
    "director": "Director",
    "manager": "Manager",
    "senior": "Senior",
    "entry": "Entry",
    "entry level": "Entry",
    "junior": "Entry",
    "intern": "Intern",
    "internship": "Intern",
    "partner": "Partner",
    "staff": "Senior",
}

BLITZAPI_JOB_LEVEL_SYNONYMS: dict[str, str] = {
    "c-suite": "C-Team",
    "csuite": "C-Team",
    "cxo": "C-Team",
    "ceo": "C-Team",
    "cfo": "C-Team",
    "cto": "C-Team",
    "coo": "C-Team",
    "cro": "C-Team",
    "cmo": "C-Team",
    "founder": "C-Team",
    "owner": "C-Team",
    "vice president": "VP",
    "vp": "VP",
    "head": "VP",
    "head of": "VP",
    "director": "Director",
    "director level": "Director",
    "manager": "Manager",
    "senior": "Staff",
    "entry": "Staff",
    "entry level": "Staff",
    "junior": "Staff",
    "intern": "Other",
    "individual contributor": "Staff",
    "ic": "Staff",
    "partner": "VP",
    "staff": "Staff",
    "other": "Other",
}
```

**Department / job function synonyms:**

```python
PROSPEO_DEPARTMENT_SYNONYMS: dict[str, str] = {
    "sales": "All Sales",
    "marketing": "Advertising",  # main department entry point
    "engineering": "Engineering & Technical",
    "hr": "All Human Resources",
    "human resources": "All Human Resources",
    "finance": "Accounting",
    "legal": "All Legal",
    "it": "Cloud Engineering",
    "information technology": "Cloud Engineering",
    "product": "All Product",
    "design": "All Design",
    "operations": "Supply Chain",
    "consulting": "Consultant",
    "medical": "Doctors / Physicians",
    "education": "Teacher",
    "customer service": "Customer Service / Support",
    "customer success": "Customer Success",
}

BLITZAPI_JOB_FUNCTION_SYNONYMS: dict[str, str] = {
    "sales": "Sales & Business Development",
    "marketing": "Advertising & Marketing",
    "engineering": "Engineering",
    "hr": "Human Resources",
    "human resources": "Human Resources",
    "finance": "Finance & Accounting",
    "legal": "Legal",
    "it": "Information Technology",
    "information technology": "Information Technology",
    "product": "General Business & Management",
    "operations": "Operations",
    "consulting": "General Business & Management",
    "medical": "Healthcare & Human Services",
    "healthcare": "Healthcare & Human Services",
    "education": "Education",
    "customer service": "Customer/Client Service",
    "construction": "Construction",
    "science": "Science",
    "r&d": "Research & Development",
    "research": "Research & Development",
    "supply chain": "Supply Chain & Logistics",
    "logistics": "Supply Chain & Logistics",
    "purchasing": "Purchasing",
    "writing": "Writing/Editing",
    "creative": "Art, Culture and Creative Professionals",
    "design": "Art, Culture and Creative Professionals",
    "manufacturing": "Manufacturing & Production",
    "government": "Public Administration & Safety",
}
```

**Employee range synonyms (handle the tier mismatch):**

```python
PROSPEO_EMPLOYEE_RANGE_SYNONYMS: dict[str, str] = {
    "1-50": "1-10",       # approximate: pick the lower bucket
    "11-50": "11-20",
    "51-200": "51-100",
    "1001-5000": "1001-2000",
    "10001+": "10000+",
    "small": "1-10",
    "medium": "201-500",
    "large": "5001-10000",
    "enterprise": "10000+",
}

BLITZAPI_EMPLOYEE_RANGE_SYNONYMS: dict[str, str] = {
    "11-20": "11-50",
    "21-50": "11-50",
    "51-100": "51-200",
    "101-200": "51-200",
    "1001-2000": "1001-5000",
    "2001-5000": "1001-5000",
    "10000+": "10001+",
    "small": "1-10",
    "medium": "201-500",
    "large": "5001-10000",
    "enterprise": "10001+",
}
```

**No synonym tables for industries, company types, continents, sales regions, or country codes.** These rely on exact matching + fuzzy matching only. The value sets are either too large (industry) or already intuitive (country codes, continents).

The executor may add additional synonym entries if they notice obvious gaps while reading the values lists. Use judgment — the tables above are the required minimum, not the maximum.

Commit standalone.

### Deliverable 3: Field Mapping Registry

Create `app/services/enum_registry/field_mappings.py`:

Define the mapping between generic (provider-agnostic) criteria field names and provider-specific field names + enum value sets + synonym tables.

```python
from app.services.enum_registry.values import (
    PROSPEO_SENIORITIES, PROSPEO_DEPARTMENTS, PROSPEO_INDUSTRIES,
    PROSPEO_EMPLOYEE_RANGES, BLITZAPI_JOB_LEVELS, BLITZAPI_JOB_FUNCTIONS,
    BLITZAPI_INDUSTRIES, BLITZAPI_EMPLOYEE_RANGES, BLITZAPI_COMPANY_TYPES,
    BLITZAPI_CONTINENTS, BLITZAPI_SALES_REGIONS, BLITZAPI_COUNTRY_CODES,
)
from app.services.enum_registry.synonyms import (
    PROSPEO_SENIORITY_SYNONYMS, BLITZAPI_JOB_LEVEL_SYNONYMS,
    PROSPEO_DEPARTMENT_SYNONYMS, BLITZAPI_JOB_FUNCTION_SYNONYMS,
    PROSPEO_EMPLOYEE_RANGE_SYNONYMS, BLITZAPI_EMPLOYEE_RANGE_SYNONYMS,
)
```

**Structure:**

```python
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
            synonyms=None,
        ),
        "blitzapi": FieldMapping(
            provider_field="industry",
            values=BLITZAPI_INDUSTRIES,
            synonyms=None,
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
```

`FieldMapping` is a simple dataclass or NamedTuple:

```python
class FieldMapping(NamedTuple):
    provider_field: str          # the provider's actual API parameter name
    values: tuple[str, ...]      # valid enum values
    synonyms: dict[str, str] | None  # lowercase alias → exact provider value
```

Also expose a helper:

```python
def get_field_mapping(generic_field: str, provider: str) -> FieldMapping | None:
    return FIELD_REGISTRY.get(generic_field, {}).get(provider)
```

Commit standalone.

### Deliverable 4: Resolution Engine

Create `app/services/enum_registry/resolver.py`:

**Core function signature:**

```python
def resolve_enum(
    provider: str,
    generic_field: str,
    user_input: str,
    *,
    fuzzy_threshold: float = 0.6,
    fuzzy_max_results: int = 1,
) -> ResolveResult:
```

**`ResolveResult`** is a NamedTuple or dataclass:

```python
class ResolveResult(NamedTuple):
    value: str | None           # the resolved provider-specific enum value, or None
    provider_field: str | None  # the provider's API parameter name
    match_type: str             # "exact", "synonym", "fuzzy", "none"
    confidence: float           # 1.0 for exact/synonym, 0.0-1.0 for fuzzy, 0.0 for none
```

**Resolution cascade (try in order, return first match):**

1. **Exact match (case-insensitive):** Lowercase the user input, check against the reverse lookup dict from `values.py`. If found, return `match_type="exact"`, `confidence=1.0`.

2. **Synonym match:** Lowercase the user input, check against the synonym dict for this provider+field. If found, return `match_type="synonym"`, `confidence=1.0`.

3. **Fuzzy match:** Use `difflib.get_close_matches(user_input.lower(), [v.lower() for v in values], n=fuzzy_max_results, cutoff=fuzzy_threshold)`. If a match is found, map back to the original-cased value. Return `match_type="fuzzy"`, `confidence` = the similarity ratio from `difflib.SequenceMatcher`.

4. **No match:** Return `value=None`, `match_type="none"`, `confidence=0.0`.

**Batch resolution helper:**

```python
def resolve_criteria(
    provider: str,
    criteria: dict[str, str],
    *,
    fuzzy_threshold: float = 0.6,
) -> dict[str, ResolveResult]:
```

Takes a dict of `{generic_field: user_input}` and returns `{generic_field: ResolveResult}` for each. This is the function the future intent-based search endpoint will call.

**Also expose:**

```python
def list_supported_fields(provider: str) -> list[str]:
    """Return generic field names supported for this provider."""

def list_valid_values(provider: str, generic_field: str) -> tuple[str, ...] | None:
    """Return the valid enum values for a provider+field combination."""
```

Commit standalone.

### Deliverable 5: Tests

Create `tests/test_enum_resolution.py`.

**Test cases (minimum 12):**

**Exact matching (3):**
1. `test_exact_match_case_insensitive` — `resolve_enum("blitzapi", "seniority", "vp")` → `value="VP"`, `match_type="exact"`.
2. `test_exact_match_preserves_casing` — `resolve_enum("blitzapi", "department", "Engineering")` → `value="Engineering"`, `match_type="exact"`.
3. `test_exact_match_prospeo_seniority` — `resolve_enum("prospeo", "seniority", "director")` → `value="Director"`, `match_type="exact"`.

**Synonym matching (4):**
4. `test_synonym_vp_to_prospeo` — `resolve_enum("prospeo", "seniority", "vp")` → `value="Vice President"`, `match_type="synonym"`.
5. `test_synonym_csuite_to_blitzapi` — `resolve_enum("blitzapi", "seniority", "c-suite")` → `value="C-Team"`, `match_type="synonym"`.
6. `test_synonym_sales_to_blitzapi_function` — `resolve_enum("blitzapi", "department", "sales")` → `value="Sales & Business Development"`, `match_type="synonym"`.
7. `test_synonym_employee_range_cross_provider` — `resolve_enum("blitzapi", "employee_range", "1001-2000")` → `value="1001-5000"`, `match_type="synonym"` (BlitzAPI doesn't have 1001-2000, synonym maps it to 1001-5000).

**Fuzzy matching (2):**
8. `test_fuzzy_match_close_spelling` — `resolve_enum("prospeo", "seniority", "Vice Pres")` → `value="Vice President"`, `match_type="fuzzy"`, `confidence > 0.6`.
9. `test_fuzzy_match_industry` — `resolve_enum("blitzapi", "industry", "Computer Softwar")` → should fuzzy-match to `"Computer Software"` (if it exists in the list) or a close match, `match_type="fuzzy"`.

**No match (2):**
10. `test_no_match_gibberish` — `resolve_enum("blitzapi", "seniority", "xyzzy123")` → `value=None`, `match_type="none"`.
11. `test_no_match_unsupported_field` — `resolve_enum("prospeo", "company_type", "Private")` → `value=None` (Prospeo has no company_type in the registry).

**Batch resolution (1):**
12. `test_resolve_criteria_batch` — `resolve_criteria("blitzapi", {"seniority": "VP", "department": "Sales", "employee_range": "51-200"})` → returns dict with 3 `ResolveResult` entries, all resolved.

**Registry helpers (2):**
13. `test_list_supported_fields` — `list_supported_fields("blitzapi")` returns at least `["seniority", "department", "industry", "employee_range", "company_type", "continent", "sales_region", "country_code"]`.
14. `test_list_valid_values` — `list_valid_values("blitzapi", "seniority")` returns the 6 BlitzAPI job level values.

Commit standalone.

---

**What is NOT in scope:**

- No intent-based search endpoint. This directive builds the resolution layer only. The search endpoint is a follow-up directive.
- No changes to existing search operations, provider adapters, or filter-building functions.
- No database migrations or tables.
- No runtime file parsing from the docs submodule. Values are hardcoded as Python constants.
- No technology, NAICS, SIC, MX provider, or funding stage enum lists. These are v2.
- No deploy commands.
- No Trigger.dev changes.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the constants defined and their value counts per provider, (b) the synonym table coverage — how many entries per provider+field, (c) the field mapping registry — all generic fields and their provider mappings, (d) the resolution function signature and the match cascade, (e) test count and what each covers, (f) anything to flag — especially if any values in the docs JSON arrays looked malformed or if the fuzzy matching needed tuning.
