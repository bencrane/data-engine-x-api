**Directive: Enum Resolution — Numeric Range Resolver + Industry Synonyms + Country Code Handling**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The intent search endpoint (`POST /api/v1/search`) uses an enum resolution layer to translate user-facing criteria into provider-specific enum values. Three categories of resolution failure were discovered during frontend chat agent testing:

1. **Employee range resolution is fundamentally broken.** The resolver treats ranges like `"50-200"` as opaque strings and fuzzy-matches them character-by-character against provider buckets like `"51-200"`. This means `"50-200"` might match `"101-200"` (higher string similarity) instead of `"51-200"` (the correct numeric bucket). Adding more synonyms is a band-aid — users can type any range ("50-200", "75-150", "100+"), and string fuzzy matching will never handle these correctly. The fix is a dedicated numeric range resolver that parses `(min, max)` and finds the best-fit provider bucket.

2. **Common industry short-forms have no synonym entries.** A user searching for `"staffing"` companies gets zero matches because both providers require the exact value `"Staffing and Recruiting"`. The industry field has `synonyms=None` in the field registry — no synonym table at all. Common single-word industry terms need synonym mappings.

3. **Country code is BlitzAPI-only but the resolver doesn't surface this.** Prospeo has no `country_code` field mapping, so `"US"` silently resolves to `match_type="none"` and is dropped. The search proceeds without geographic filtering, returning irrelevant global results. The resolver should handle provider-unsupported fields more explicitly so the search service can make smarter provider-selection decisions.

**Existing code to read:**

- `app/services/enum_registry/resolver.py` — current resolution cascade (exact → synonym → fuzzy → none)
- `app/services/enum_registry/synonyms.py` — current synonym tables (seniority, department, employee range)
- `app/services/enum_registry/field_mappings.py` — `FIELD_REGISTRY`, `FieldMapping` NamedTuple
- `app/services/enum_registry/values.py` — all provider enum constants and lookup structures, including `VALUES_REGISTRY`
- `app/services/intent_search.py` — the search service that calls `resolve_criteria()` and builds provider filters
- `app/contracts/intent_search.py` — `IntentSearchRequest`, `IntentSearchOutput`, `EnumResolutionDetail`
- `tests/test_enum_resolution.py` — existing tests (do not break them)
- `tests/test_intent_search.py` — existing search tests (do not break them)

---

### Deliverable 1: Numeric Range Resolver for `employee_range`

The current resolution cascade (exact → synonym → fuzzy) is wrong for numeric ranges. Replace it with a dedicated path for `employee_range` that understands numbers.

**In `app/services/enum_registry/resolver.py`:**

Add a function that resolves employee range inputs numerically:

1. Parse the user input into `(min_val, max_val)` integers. Handle these formats:
   - `"50-200"` → `(50, 200)`
   - `"51-200"` → `(51, 200)`
   - `"200+"` or `"200plus"` → `(200, infinity)`
   - `"10000+"` → `(10000, infinity)`
   - `"500"` (single number) → `(500, 500)`
   - Strip whitespace, commas, "employees", "people" from the input before parsing

2. Parse each provider bucket the same way: `"51-200"` → `(51, 200)`, `"10001+"` → `(10001, infinity)`.

3. Find the best-fit bucket using this logic:
   - **Containment:** If the user range falls entirely within a provider bucket, that bucket wins. Example: user `(50, 200)` fits inside BlitzAPI `(51, 200)` — close enough, take it.
   - **Best overlap:** If no single bucket contains the user range, pick the bucket with the most overlap with the user range. Example: user `(50, 200)` overlaps BlitzAPI `(51, 200)` by 150 units and `(11, 50)` by 1 unit — pick `(51, 200)`.
   - **Nearest boundary:** If there's no overlap at all (e.g., user says `"15"` and buckets are `"1-10"`, `"11-50"`), pick the bucket whose boundaries are closest to the user input.

4. Return `match_type="exact"` with `confidence=1.0` if the user input exactly matches a bucket. Return `match_type="numeric"` with a confidence score based on how well the user range fits the bucket (1.0 for perfect containment, scaled down for partial overlap).

**In `resolve_enum()`:** Before the fuzzy match step (step 3), check if `generic_field == "employee_range"`. If so, call the numeric range resolver instead of `difflib.get_close_matches`. Keep the exact match (step 1) and synonym match (step 2) checks as-is — they still handle word inputs like `"small"`, `"medium"`, `"enterprise"`.

**Do NOT remove the existing synonym entries** in `PROSPEO_EMPLOYEE_RANGE_SYNONYMS` and `BLITZAPI_EMPLOYEE_RANGE_SYNONYMS`. They still serve as a fast path for known cross-provider mappings. The numeric resolver is a replacement for the fuzzy fallback only.

Commit standalone.

### Deliverable 2: Industry Synonym Tables

The `industry` field currently has `synonyms=None` for both providers. Add synonym tables for common short-form industry terms.

**In `app/services/enum_registry/synonyms.py`:**

Create `PROSPEO_INDUSTRY_SYNONYMS` and `BLITZAPI_INDUSTRY_SYNONYMS`. Both providers have `"Staffing and Recruiting"` as an exact value (Prospeo line 258, BlitzAPI line 982 in `values.py`).

**Required entries (minimum — add more if you spot obvious gaps while reading the values lists):**

```
"staffing" → "Staffing and Recruiting"
"staffing and recruiting" → "Staffing and Recruiting"
"recruiting" → "Staffing and Recruiting"
"recruitment" → "Staffing and Recruiting"
"saas" → "Computer Software" (or closest match in the provider's list)
"software" → "Computer Software"
"tech" → "Information Technology and Services"
"healthcare" → "Hospital & Health Care"
"fintech" → "Financial Services"
"real estate" → "Real Estate"
"insurance" → "Insurance"
"banking" → "Banking"
"manufacturing" → "Machinery"  (or closest)
"logistics" → "Logistics and Supply Chain"
"construction" → "Construction"
"retail" → "Retail"
"ecommerce" → "Internet"
"e-commerce" → "Internet"
"legal" → "Legal Services"
"accounting" → "Accounting"
"consulting" → "Management Consulting"
"advertising" → "Marketing and Advertising"
"media" → "Online Media"
"education" → "Education Management"
"telecom" → "Telecommunications"
"automotive" → "Automotive"
"pharma" → "Pharmaceuticals"
"biotech" → "Biotechnology"
```

The exact target values will differ between Prospeo and BlitzAPI — look up the actual values in `values.py` (Prospeo industries start around line 214, BlitzAPI industries start around line 525). Map each synonym to the closest exact value that exists in that provider's list.

**In `app/services/enum_registry/field_mappings.py`:**

Update the `"industry"` entry in `FIELD_REGISTRY` to wire in the new synonym tables:

- `"prospeo"` → `synonyms=PROSPEO_INDUSTRY_SYNONYMS` (currently `None`)
- `"blitzapi"` → `synonyms=BLITZAPI_INDUSTRY_SYNONYMS` (currently `None`)

Import the new synonym constants.

Commit standalone.

### Deliverable 3: Country Code Provider Awareness

Currently, when a user includes `country_code: "US"` in their criteria and the resolver tries Prospeo first, Prospeo has no `country_code` mapping so it resolves to `match_type="none"`. The search proceeds without any geographic filter, often returning irrelevant results.

**In `app/services/intent_search.py`:**

When determining provider order in auto mode (`provider=None`), add provider-selection awareness for `country_code`:

- If the user's criteria include `country_code` (or `location` that looks like a country/country code), prefer providers that support the `country_code` field.
- Concretely: if `criteria` contains `country_code` and the provider order is `["prospeo", "blitzapi"]`, move BlitzAPI ahead of Prospeo (or at minimum, do not discard the `country_code` criterion when building Prospeo filters — flag it as unsupported so the caller knows).

The implementation approach is up to you. The simplest correct approach: before trying a provider, check how many of the user's enum criteria fields are supported by that provider (via `get_field_mapping`). If one provider supports significantly more of the user's criteria, try it first. This is a lightweight heuristic — do not over-engineer it.

**Also in `app/contracts/intent_search.py`:**

Add a `provider_field_gaps` field (or similar) to `IntentSearchOutput` that lists criteria fields the user requested but the chosen provider does not support. This gives the frontend agent visibility into why some filters were dropped. Example:

```python
provider_field_gaps: list[str] = []  # e.g., ["country_code"] when Prospeo was used
```

Commit standalone.

### Deliverable 4: Tests

**In `tests/test_enum_resolution.py`** — add tests for the numeric range resolver:

1. `test_numeric_range_exact_bucket_match` — `resolve_enum("blitzapi", "employee_range", "51-200")` → exact match, `confidence=1.0`
2. `test_numeric_range_close_fit` — `resolve_enum("blitzapi", "employee_range", "50-200")` → resolves to `"51-200"`, `match_type="numeric"`
3. `test_numeric_range_partial_overlap` — `resolve_enum("blitzapi", "employee_range", "100-300")` → resolves to `"51-200"` or `"201-500"` (whichever has more overlap)
4. `test_numeric_range_plus_format` — `resolve_enum("blitzapi", "employee_range", "500+")` → resolves to `"501-1000"` or best fit
5. `test_numeric_range_single_number` — `resolve_enum("blitzapi", "employee_range", "150")` → resolves to `"51-200"`
6. `test_numeric_range_with_word_suffix` — `resolve_enum("blitzapi", "employee_range", "50-200 employees")` → resolves to `"51-200"`
7. `test_numeric_range_prospeo_different_buckets` — `resolve_enum("prospeo", "employee_range", "50-200")` → resolves to `"51-100"` or `"101-200"` (Prospeo has finer buckets)
8. `test_word_range_still_uses_synonym` — `resolve_enum("blitzapi", "employee_range", "enterprise")` → still uses synonym table, returns `"10001+"`, `match_type="synonym"`

**In `tests/test_enum_resolution.py`** — add tests for industry synonyms:

9. `test_industry_synonym_staffing` — `resolve_enum("blitzapi", "industry", "staffing")` → `"Staffing and Recruiting"`, `match_type="synonym"`
10. `test_industry_synonym_saas` — `resolve_enum("prospeo", "industry", "saas")` → resolves to the closest Prospeo industry value, `match_type="synonym"`
11. `test_industry_exact_still_works` — `resolve_enum("blitzapi", "industry", "Staffing and Recruiting")` → exact match, `confidence=1.0`

**In `tests/test_intent_search.py`** — add tests for provider selection and field gaps:

12. `test_country_code_prefers_blitzapi` — Send criteria with `country_code: "US"` and no explicit provider. Assert BlitzAPI is tried first (or at least that `country_code` is not silently dropped).
13. `test_provider_field_gaps_reported` — Send criteria with `country_code: "US"` and `provider: "prospeo"` explicitly. Assert `provider_field_gaps` includes `"country_code"`.

Commit standalone.

---

**What is NOT in scope:**

- No changes to provider adapters (`app/providers/prospeo.py`, `app/providers/blitzapi.py`). The resolution layer translates values; it does not change how providers are called.
- No new API endpoints. The changes are to the resolution engine and the existing intent search service.
- No database migrations.
- No Trigger.dev changes.
- No deploy commands.
- Do not break existing tests. Run `pytest` before committing and fix any regressions.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the numeric range resolver — what formats it parses and how it picks the best bucket, (b) the industry synonym tables — entry counts per provider and any values you couldn't find exact matches for, (c) the provider selection changes — how country_code (and other provider-specific fields) influence provider order, (d) the `provider_field_gaps` field — what it contains and when, (e) test count and what each covers, (f) anything to flag — especially if the numeric parsing needed edge-case handling beyond what this directive specified, or if Prospeo/BlitzAPI industry value lists had gaps that made synonym mapping ambiguous.
