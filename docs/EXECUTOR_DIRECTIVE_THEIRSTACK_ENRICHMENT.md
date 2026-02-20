# Directive: TheirStack Adapter Enrichment + `job.search` Operation

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We are building a staffing agency revenue activation product. The core data pipeline starts with TheirStack job posting search. Our current adapter maps only 8 of 30+ fields returned by the API, and the operation exposes only 5 of 40+ available filters. This directive enriches the TheirStack integration to capture the full job posting payload — especially `hiring_team`, `description`, salary fields, `remote`/`hybrid`, `employment_statuses`, and the embedded `company_object` — and adds a new `job.search` operation with full filter passthrough.

---

## TheirStack Job Search API Reference

**Endpoint:** `POST https://api.theirstack.com/v1/jobs/search`

**Auth:** `Authorization: Bearer <token>`

**Required:** At least one of: `posted_at_max_age_days`, `posted_at_gte`, `posted_at_lte`, `company_domain_or`, `company_linkedin_url_or`, `company_name_or`

### Response shape (per job item in `data[]`):

```json
{
  "id": 1234,
  "job_title": "Senior Data Engineer",
  "normalized_title": "data engineer",
  "url": "https://example.com/job/1234",
  "final_url": "https://company.com/careers/job-details/1234",
  "source_url": "https://www.linkedin.com/jobs/view/1234567890",
  "date_posted": "2024-01-01",
  "discovered_at": "2024-01-01T00:00:00",
  "reposted": true,
  "date_reposted": "2024-01-01",
  "company": "Google",
  "company_domain": "google.com",
  "location": "New York",
  "short_location": "Tulsa, OK",
  "long_location": "Methuen, MA 01844",
  "state_code": "OK",
  "postal_code": "01844",
  "latitude": 37.774929,
  "longitude": -96.726486,
  "country": "United States",
  "country_code": "US",
  "cities": ["New York", "San Francisco"],
  "remote": true,
  "hybrid": true,
  "seniority": "c_level",
  "employment_statuses": ["full_time"],
  "easy_apply": true,
  "salary_string": "$100,000 - $120,000",
  "min_annual_salary_usd": 100000,
  "max_annual_salary_usd": 120000,
  "avg_annual_salary_usd": 110000,
  "salary_currency": "USD",
  "description": "We are looking for a Senior Data Engineer...",
  "technology_slugs": ["postgresql", "kafka", "python"],
  "hiring_team": [
    {
      "first_name": "John",
      "full_name": "John Doe",
      "image_url": "https://media.licdn.com/...",
      "linkedin_url": "https://www.linkedin.com/in/john-doe-123",
      "role": "VP Engineering",
      "thumbnail_url": "https://media.licdn.com/..."
    }
  ],
  "company_object": {
    "id": "google",
    "name": "Google",
    "domain": "google.com",
    "industry": "internet",
    "country": "United States",
    "employee_count": 7543,
    "logo": "https://example.com/logo.png",
    "num_jobs": 746,
    "linkedin_url": "http://www.linkedin.com/company/google",
    "num_jobs_last_30_days": 34,
    "yc_batch": "W21",
    "founded_year": 2019,
    "annual_revenue_usd": 189000000,
    "total_funding_usd": 500000,
    "last_funding_round_date": "2020-01-01",
    "employee_count_range": "1001-5000",
    "long_description": "Google is a California-based multinational...",
    "city": "Mountain View",
    "publicly_traded_symbol": "GOOG",
    "publicly_traded_exchange": "NASDAQ",
    "funding_stage": "angel",
    "technology_slugs": ["kafka", "elasticsearch"],
    "technology_names": ["Kafka", "Elasticsearch"]
  },
  "locations": [
    {
      "name": "Live Oak",
      "state": "California",
      "state_code": "CA",
      "country_code": "US",
      "country_name": "United States",
      "display_name": "Live Oak, California, United States",
      "latitude": 37,
      "longitude": -122,
      "type": "city"
    }
  ],
  "manager_roles": ["VP Engineering"]
}
```

### Response metadata:

```json
{
  "metadata": {
    "total_results": 2034,
    "total_companies": 1045
  },
  "data": [...]
}
```

### Full filter surface (all available request body parameters):

**Job Title:** `job_title_or`, `job_title_not`, `job_title_pattern_and`, `job_title_pattern_or`, `job_title_pattern_not`

**Job Location:** `job_country_code_or`, `job_country_code_not`, `job_location_pattern_or`, `job_location_pattern_not`

**Date:** `posted_at_max_age_days`, `posted_at_gte`, `posted_at_lte`, `discovered_at_max_age_days`, `discovered_at_gte`, `discovered_at_lte`

**Job Attributes:** `remote`, `job_seniority_or`, `min_salary_usd`, `max_salary_usd`, `easy_apply`, `employment_statuses_or`

**Job Description:** `job_description_pattern_or`, `job_description_pattern_not`, `job_description_contains_or`, `job_description_contains_not`

**Technology:** `job_technology_slug_or`, `job_technology_slug_not`, `job_technology_slug_and`

**URL/Source:** `url_domain_or`, `url_domain_not`

**Company Identity:** `company_domain_or`, `company_domain_not`, `company_name_or`, `company_name_not`, `company_name_case_insensitive_or`, `company_name_partial_match_or`, `company_linkedin_url_or`, `company_list_id_or`, `company_list_id_not`

**Company Description:** `company_description_pattern_or`, `company_description_pattern_not`

**Company Size/Financials:** `min_revenue_usd`, `max_revenue_usd`, `min_employee_count`, `max_employee_count`, `min_funding_usd`, `max_funding_usd`, `funding_stage_or`, `last_funding_round_date_lte`, `last_funding_round_date_gte`

**Company Industry/Location:** `industry_id_or`, `industry_id_not`, `company_country_code_or`, `company_country_code_not`

**Company Tech/Investors:** `company_technology_slug_or`, `company_technology_slug_and`, `company_technology_slug_not`, `company_investors_or`, `company_investors_partial_match_or`, `company_tags_or`, `only_yc_companies`

**Company Type:** `company_type` — values: `recruiting_agency`, `direct_employer`, `all`

**Pagination:** `limit`, `offset`, `page`, `cursor`

**Other:** `include_total_results`, `blur_company_data`

---

## Existing code to read before starting:

- `app/providers/theirstack.py` — current adapter (4 functions: `search_companies`, `search_jobs`, `get_technographics`, `enrich_hiring_signals`)
- `app/contracts/theirstack.py` — current Pydantic contracts (`TheirStackJobItem` has 8 fields)
- `app/services/theirstack_operations.py` — current operation executors (4 operations)
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/providers/common.py` — `ProviderAdapterResult` type, `now_ms()`, `parse_json_or_raw()`
- `tests/test_theirstack_operations.py` — existing tests (reference pattern)

---

## Deliverable 1: Enrich Provider Adapter

**File:** `app/providers/theirstack.py`

### 1a. Replace `_map_job_item` with an enriched version that maps all staffing-relevant fields:

| Canonical field | Source field | Type |
|---|---|---|
| `theirstack_job_id` | `id` | `int \| None` |
| `job_title` | `job_title` | `str \| None` |
| `normalized_title` | `normalized_title` | `str \| None` |
| `company_name` | `company` | `str \| None` |
| `company_domain` | `company_domain` | `str \| None` |
| `url` | `url` | `str \| None` |
| `final_url` | `final_url` | `str \| None` |
| `source_url` | `source_url` | `str \| None` |
| `date_posted` | `date_posted` | `str \| None` |
| `discovered_at` | `discovered_at` | `str \| None` |
| `reposted` | `reposted` | `bool \| None` |
| `date_reposted` | `date_reposted` | `str \| None` |
| `location` | `location` | `str \| None` |
| `short_location` | `short_location` | `str \| None` |
| `long_location` | `long_location` | `str \| None` |
| `state_code` | `state_code` | `str \| None` |
| `postal_code` | `postal_code` | `str \| None` |
| `latitude` | `latitude` | `float \| None` |
| `longitude` | `longitude` | `float \| None` |
| `country` | `country` | `str \| None` |
| `country_code` | `country_code` | `str \| None` |
| `cities` | `cities` | `list[str] \| None` |
| `remote` | `remote` | `bool \| None` |
| `hybrid` | `hybrid` | `bool \| None` |
| `seniority` | `seniority` | `str \| None` |
| `employment_statuses` | `employment_statuses` | `list[str] \| None` |
| `easy_apply` | `easy_apply` | `bool \| None` |
| `salary_string` | `salary_string` | `str \| None` |
| `min_annual_salary_usd` | `min_annual_salary_usd` | `float \| None` |
| `max_annual_salary_usd` | `max_annual_salary_usd` | `float \| None` |
| `avg_annual_salary_usd` | `avg_annual_salary_usd` | `float \| None` |
| `salary_currency` | `salary_currency` | `str \| None` |
| `description` | `description` | `str \| None` |
| `technology_slugs` | `technology_slugs` | `list[str] \| None` |
| `hiring_team` | `hiring_team` (mapped via `_map_hiring_team_item`) | `list[dict] \| None` |
| `company_object` | `company_object` (mapped via `_map_company_object`) | `dict \| None` |
| `manager_roles` | `manager_roles` | `list[str] \| None` |

### 1b. Add `_map_hiring_team_item(raw: dict) -> dict | None`:

```
{
  "full_name": str | None,
  "first_name": str | None,
  "linkedin_url": str | None,
  "role": str | None,
  "image_url": str | None,
}
```

Skip items where both `full_name` and `linkedin_url` are null.

### 1c. Add `_map_company_object(raw: dict) -> dict | None`:

```
{
  "theirstack_company_id": str | None,  # from "id"
  "name": str | None,
  "domain": str | None,
  "industry": str | None,
  "country": str | None,
  "employee_count": int | None,
  "employee_count_range": str | None,
  "logo": str | None,
  "linkedin_url": str | None,
  "num_jobs": int | None,
  "num_jobs_last_30_days": int | None,
  "founded_year": int | None,
  "annual_revenue_usd": float | None,
  "total_funding_usd": int | None,
  "last_funding_round_date": str | None,
  "funding_stage": str | None,
  "city": str | None,
  "long_description": str | None,
  "publicly_traded_symbol": str | None,
  "publicly_traded_exchange": str | None,
  "technology_slugs": list[str] | None,
  "technology_names": list[str] | None,
}
```

Return `None` if no `name` and no `domain`.

### 1d. Update `search_jobs` function signature to accept optional pagination params:

```python
async def search_jobs(
    *,
    api_key: str | None,
    filters: dict[str, Any],
    limit: int,
    offset: int = 0,
    page: int | None = None,
    cursor: str | None = None,
    include_total_results: bool = False,
) -> ProviderAdapterResult:
```

Pass `offset`, `page`, `cursor`, and `include_total_results` through to the API request payload alongside filters and limit. Only include non-None/non-default values.

Add `total_results` and `total_companies` from `metadata` to the mapped output:

```python
"mapped": {
    "results": mapped_results,
    "result_count": result_count,
    "total_results": _as_int(metadata.get("total_results")),
    "total_companies": _as_int(metadata.get("total_companies")),
}
```

**Important:** The existing `_map_job_item` signature and return shape is changing. The old 8-field shape is a strict subset of the new shape, so this is backward-compatible — existing callers get more data, not different data. The old field names (`job_id`, `company_name`, `company_domain`, `url`, `date_posted`, `location`, `seniority`) must remain present with the same keys. `job_id` is renamed to `theirstack_job_id` — **also keep the old `job_id` key mapped to the same value for backward compatibility.**

Commit standalone with message: `enrich TheirStack provider adapter with full job posting field mapping`

---

## Deliverable 2: Enrich Contracts

**File:** `app/contracts/theirstack.py`

### 2a. Add `TheirStackHiringTeamMember` model:

```python
class TheirStackHiringTeamMember(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    linkedin_url: str | None = None
    role: str | None = None
    image_url: str | None = None
```

### 2b. Add `TheirStackEmbeddedCompany` model:

```python
class TheirStackEmbeddedCompany(BaseModel):
    theirstack_company_id: str | None = None
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    country: str | None = None
    employee_count: int | None = None
    employee_count_range: str | None = None
    logo: str | None = None
    linkedin_url: str | None = None
    num_jobs: int | None = None
    num_jobs_last_30_days: int | None = None
    founded_year: int | None = None
    annual_revenue_usd: float | None = None
    total_funding_usd: int | None = None
    last_funding_round_date: str | None = None
    funding_stage: str | None = None
    city: str | None = None
    long_description: str | None = None
    publicly_traded_symbol: str | None = None
    publicly_traded_exchange: str | None = None
    technology_slugs: list[str] | None = None
    technology_names: list[str] | None = None
```

### 2c. Expand `TheirStackJobItem` with all new fields:

Keep all existing fields. Add:

```python
class TheirStackJobItem(BaseModel):
    # existing (keep all)
    job_id: int | None = None
    job_title: str | None = None
    company_name: str | None = None
    company_domain: str | None = None
    url: str | None = None
    date_posted: str | None = None
    location: str | None = None
    seniority: str | None = None
    source_provider: str = "theirstack"

    # new identity
    theirstack_job_id: int | None = None
    normalized_title: str | None = None

    # new URLs
    final_url: str | None = None
    source_url: str | None = None

    # new dates
    discovered_at: str | None = None
    reposted: bool | None = None
    date_reposted: str | None = None

    # new location (structured)
    short_location: str | None = None
    long_location: str | None = None
    state_code: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    country: str | None = None
    country_code: str | None = None
    cities: list[str] | None = None

    # new job attributes
    remote: bool | None = None
    hybrid: bool | None = None
    employment_statuses: list[str] | None = None
    easy_apply: bool | None = None

    # new salary
    salary_string: str | None = None
    min_annual_salary_usd: float | None = None
    max_annual_salary_usd: float | None = None
    avg_annual_salary_usd: float | None = None
    salary_currency: str | None = None

    # new content
    description: str | None = None
    technology_slugs: list[str] | None = None
    manager_roles: list[str] | None = None

    # new nested objects
    hiring_team: list[TheirStackHiringTeamMember] | None = None
    company_object: TheirStackEmbeddedCompany | None = None
```

### 2d. Add `TheirStackJobSearchExtendedOutput` model:

```python
class TheirStackJobSearchExtendedOutput(BaseModel):
    results: list[TheirStackJobItem]
    result_count: int
    total_results: int | None = None
    total_companies: int | None = None
    source_provider: str = "theirstack"
```

The existing `TheirStackJobSearchOutput` must remain unchanged for backward compatibility with `company.search.by_job_postings`. The new `job.search` operation uses `TheirStackJobSearchExtendedOutput`.

Commit standalone with message: `add enriched TheirStack job posting contracts with hiring team and embedded company`

---

## Deliverable 3: Expand `company.search.by_job_postings` Filter Surface

**File:** `app/services/theirstack_operations.py`

Update `execute_company_search_by_job_postings` to expose additional filters from `step_config`:

**Add these to the filters dict (in addition to the existing 5):**

```python
# Company identity
"company_domain_or": step_config.get("company_domain_or"),
"company_domain_not": step_config.get("company_domain_not"),
"company_name_or": step_config.get("company_name_or"),
"company_name_not": step_config.get("company_name_not"),
"company_linkedin_url_or": step_config.get("company_linkedin_url_or"),

# Date (precise)
"posted_at_gte": step_config.get("posted_at_gte"),
"posted_at_lte": step_config.get("posted_at_lte"),

# Job attributes
"remote": step_config.get("remote"),
"min_salary_usd": step_config.get("min_salary_usd"),
"max_salary_usd": step_config.get("max_salary_usd"),
"employment_statuses_or": step_config.get("employment_statuses_or"),

# Company type
"company_type": step_config.get("company_type"),

# Company size
"min_employee_count": step_config.get("min_employee_count"),
"max_employee_count": step_config.get("max_employee_count"),
"min_revenue_usd": step_config.get("min_revenue_usd"),
"max_revenue_usd": step_config.get("max_revenue_usd"),
```

Also update the `_has_filter_value` check so that boolean `False` is treated as a valid filter value (for `remote: false`). Currently `_has_filter_value` returns `True` for booleans which is correct, but verify this edge case is handled properly for `None` vs `False`.

Update the validation output to use `TheirStackJobSearchExtendedOutput` instead of `TheirStackJobSearchOutput`. Pass through `total_results` and `total_companies` from the mapped result.

Update the `missing_inputs` message to reflect the expanded filter set.

Commit standalone with message: `expand company.search.by_job_postings filter surface for staffing use case`

---

## Deliverable 4: Add `job.search` Operation

**File:** `app/services/theirstack_operations.py`

Add new function `execute_job_search`:

```python
async def execute_job_search(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

This operation exposes the **full** TheirStack job search filter surface. It reads all filter parameters from `step_config` (via `_extract_step_config`).

**Full filter passthrough — every filter listed in the API reference section of this directive:**

All job title filters, all location filters, all date filters, all description filters, all job attribute filters, all technology filters, all URL/source filters, all company identity filters, all company size/financials, all company industry/location, all company tech/investors, and `company_type`.

Also read from step_config:
- `limit` (default 25, min 1, max 500)
- `offset` (default 0)
- `include_total_results` (default false)

**Filter cleaning rules:**
- Remove `None` values
- Remove empty strings
- Remove empty lists
- Keep `False` booleans (they are valid filters, e.g. `remote: false`)
- Keep `0` integers (e.g. `posted_at_max_age_days: 0` means today only)

**Validation:** At least one of `posted_at_max_age_days`, `posted_at_gte`, `posted_at_lte`, `company_domain_or`, `company_linkedin_url_or`, `company_name_or` must be present. If none: return `status: "failed"` with `missing_inputs`.

**Output:** Use `TheirStackJobSearchExtendedOutput` contract.

**Operation ID:** `"job.search"`

Follow the exact same pattern as `execute_company_search_by_job_postings` for run_id generation, attempt tracking, status derivation, and error handling.

Commit standalone with message: `add job.search operation with full TheirStack filter passthrough`

---

## Deliverable 5: Wire Into Execute Router

**File:** `app/routers/execute_v1.py`

1. Add `"job.search"` to `SUPPORTED_OPERATION_IDS`.

2. Add import: `execute_job_search` from `app.services.theirstack_operations`.

3. Add dispatch branch (follow existing pattern):

```python
if payload.operation_id == "job.search":
    result = await execute_job_search(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Place the new branch near the existing TheirStack operations for readability.

Commit standalone with message: `wire job.search operation into execute router`

---

## Deliverable 6: Tests

**File:** `tests/test_theirstack_job_search.py` (new file)

Write tests using the existing test patterns from `tests/test_theirstack_operations.py`. Mock all HTTP calls via `unittest.mock.patch` on `httpx.AsyncClient`.

### Required test cases:

**Provider adapter tests:**
1. `test_map_job_item_full_fields` — verify all 35+ fields are mapped correctly from a complete API response
2. `test_map_job_item_minimal_fields` — verify graceful handling when most fields are null/missing
3. `test_map_hiring_team_item_valid` — verify hiring team member mapping
4. `test_map_hiring_team_item_skip_empty` — verify items with no name and no LinkedIn are skipped
5. `test_map_company_object_valid` — verify embedded company mapping
6. `test_map_company_object_skip_empty` — verify None returned when no name and no domain
7. `test_search_jobs_pagination_params` — verify offset/cursor/include_total_results are passed through to the API request
8. `test_search_jobs_metadata_in_output` — verify total_results/total_companies are captured from response metadata

**Operation tests:**
9. `test_job_search_full_filters` — verify all filter types pass through to the provider
10. `test_job_search_missing_required_filter` — verify fails when no required filter is provided
11. `test_job_search_boolean_false_preserved` — verify `remote: false` is not stripped as a falsy value
12. `test_job_search_integer_zero_preserved` — verify `posted_at_max_age_days: 0` is not stripped
13. `test_job_search_success_response_shape` — verify full response structure with enriched job items
14. `test_job_search_empty_results` — verify `not_found` status when no results
15. `test_job_search_api_error` — verify `failed` status on HTTP error

**Backward compatibility:**
16. `test_company_search_by_job_postings_still_works` — verify existing operation returns enriched data without breaking
17. `test_company_search_by_job_postings_expanded_filters` — verify new filters (company_domain_or, remote, etc.) pass through

Use realistic mock data based on the API response shape documented above. Do not use placeholder strings — use realistic job titles, company names, domains, etc.

Commit standalone with message: `add tests for enriched TheirStack job search adapter and job.search operation`

---

## What is NOT in scope

- No database migrations. No new tables. The `job_posting_entities` table is a separate workstream.
- No changes to `company.search.by_tech_stack`, `company.enrich.tech_stack`, or `company.enrich.hiring_signals` operations.
- No changes to the Trigger.dev pipeline runner.
- No deploy commands (`git push`, `trigger deploy`, etc.).
- No changes to `app/registry/operations.yaml` (will be updated separately).
- No Bright Data integration.
- No entity state or timeline changes.

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Full list of fields now mapped in `_map_job_item` (count)
(b) `TheirStackJobItem` field count (old vs new)
(c) Full list of filters exposed in `job.search` operation
(d) Router wiring confirmation
(e) Test count and all test names
(f) Any edge cases or concerns discovered during implementation
