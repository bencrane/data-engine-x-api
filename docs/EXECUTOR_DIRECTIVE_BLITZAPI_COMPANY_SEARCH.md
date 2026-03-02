# Directive: `company.search.blitzapi` — BlitzAPI Company Search

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** BlitzAPI offers a powerful company search endpoint with rich filtering (keywords, industry, location, employee size, company type, founding year, follower count) and cursor-based pagination. We need this as a standalone operation for building target company lists in pipelines. The response returns full company profiles (same shape as the company enrichment endpoint) so each result includes `linkedin_id`, `domain`, `about`, etc.

---

## BlitzAPI Endpoint Reference

**Endpoint:** `POST https://api.blitz-api.ai/v2/search/companies`

**Auth:** `x-api-key` header. The key is available via `settings.blitzapi_api_key` (already in `app/config.py`).

**Request body:**
```json
{
  "company": {
    "keywords": {
      "include": ["SaaS", "cloud platform"],
      "exclude": []
    },
    "industry": {
      "include": ["Software Development"],
      "exclude": []
    },
    "hq": {
      "continent": ["North America"],
      "country_code": ["US"],
      "sales_region": [],
      "city": { "include": [], "exclude": [] }
    },
    "employee_range": ["51-200", "201-500"],
    "employee_count": { "min": 0, "max": 0 },
    "founded_year": { "min": 2015, "max": 0 },
    "type": {
      "include": ["Privately Held"],
      "exclude": []
    },
    "name": {
      "include": [],
      "exclude": []
    },
    "min_linkedin_followers": 1
  },
  "max_results": 25,
  "cursor": null
}
```

All fields inside `company` are optional. Omit any filter you don't need.

- `keywords`: Search company description/about. `include`/`exclude` arrays of strings.
- `industry`: Filter by LinkedIn industry. `include`/`exclude`.
- `hq`: Location filter. `continent` (Africa, Asia, Europe, North America, Oceania, South America), `country_code` (ISO alpha-2), `sales_region` (NORAM, LATAM, EMEA, APAC), `city` (keyword filter).
- `employee_range`: Array of bucket strings: `1-10`, `11-50`, `51-200`, `201-500`, `501-1000`, `1001-5000`, `5001-10000`, `10001+`.
- `employee_count`: Numeric range `{min, max}`. `max: 0` = unbounded.
- `founded_year`: Numeric range `{min, max}`.
- `type`: Company type filter. Values: `Educational`, `Government Agency`, `Nonprofit`, `Partnership`, `Privately Held`, `Public Company`, `Self-Employed`, `Self-Owned`, `Sole Proprietorship`.
- `name`: Search in company name. `include`/`exclude`.
- `min_linkedin_followers`: Minimum followers (default 1).
- `max_results`: 1-50 per page.
- `cursor`: Pagination cursor from previous response. `null` for first page.

**Response (200):**
```json
{
  "results_count": 2,
  "total_results": 148,
  "cursor": "eyJwYWdlIjoyLCJzZWFyY2hfaWQiOiJhYmMxMjMifQ==",
  "results": [
    {
      "linkedin_url": "https://www.linkedin.com/company/blitz-api",
      "linkedin_id": 108037802,
      "name": "Blitzapi",
      "about": "BlitzAPI provides enriched B2B data access...",
      "industry": "Technology; Information and Internet",
      "type": "Privately Held",
      "size": "1-10",
      "employees_on_linkedin": 3,
      "followers": 6,
      "founded_year": null,
      "specialties": null,
      "hq": {
        "city": "Paris",
        "state": null,
        "postcode": null,
        "country_code": "FR",
        "country_name": "France",
        "continent": "Europe",
        "street": null
      },
      "domain": "blitz-api.ai",
      "website": "https://blitz-api.ai"
    }
  ]
}
```

`cursor` is `null` when no more pages exist.

**Error responses:**
- 401: Invalid API key
- 402: Insufficient credits
- 422: Invalid input
- 429: Rate limit (handled by existing retry logic)
- 500: Internal server error

---

## Existing code to read before starting

- `app/providers/blitzapi.py` — read `search_employees` (~line 443) as the closest pattern reference (structured search with filters, pagination). Read `_blitzapi_request_with_retry` for retry logic. Read `canonical_company_result` (~line 80) for company response mapping. Do NOT modify existing functions.
- `app/contracts/company_enrich.py` — read `BlitzAPICompanyEnrichOutput` for the canonical company fields. Your search results use the same company object shape.
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS` and dispatch chain.
- `app/services/company_operations.py` — reference for company operation service patterns.

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/blitzapi.py` (existing file — add function, do NOT modify existing functions)

```python
async def search_companies(
    *,
    api_key: str | None,
    company_filters: dict[str, Any] | None = None,
    max_results: int = 10,
    cursor: str | None = None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `api_key` missing → `skipped`, `missing_provider_api_key`
2. Build payload:
   ```python
   payload = {"max_results": max(min(max_results, 50), 1)}
   if company_filters and isinstance(company_filters, dict):
       payload["company"] = company_filters
   if cursor:
       payload["cursor"] = cursor
   ```
3. POST to `https://api.blitz-api.ai/v2/search/companies` with `x-api-key` header.
4. Use `_blitzapi_request_with_retry`. Timeout: 30 seconds.
5. If `response.status_code >= 400` → `failed` (or `not_found` for 404).
6. Parse response. Map each result through `canonical_company_result(company=result)` — the results have the same company object shape as the enrichment endpoint.
7. Return:
   ```python
   "mapped": {
       "results": mapped_results,
       "pagination": {
           "cursor": body.get("cursor"),
           "totalItems": body.get("total_results"),
           "pageItems": body.get("results_count"),
       },
   }
   ```
8. Status: `"found"` if results non-empty, `"not_found"` otherwise.
9. Action name: `"search_companies"`

Commit standalone with message: `add BlitzAPI company search provider adapter`

---

## Deliverable 2: Contract

**File:** `app/contracts/blitzapi_company_search.py` (new file)

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CompanySearchResultItem(BaseModel):
    company_name: str | None = None
    company_domain: str | None = None
    company_website: str | None = None
    company_linkedin_url: str | None = None
    company_linkedin_id: str | None = None
    company_type: str | None = None
    industry_primary: str | None = None
    employee_count: int | str | None = None
    employee_range: str | None = None
    founded_year: int | None = None
    hq_locality: str | None = None
    hq_country_code: str | None = None
    description_raw: str | None = None
    specialties: list[Any] | str | None = None
    follower_count: int | str | None = None
    source_provider: str = "blitzapi"


class BlitzAPICompanySearchOutput(BaseModel):
    results: list[CompanySearchResultItem]
    results_count: int
    total_results: int | None = None
    cursor: str | None = None
    source_provider: str = "blitzapi"
```

Commit standalone with message: `add BlitzAPI company search output contract`

---

## Deliverable 3: Service Function

**File:** `app/services/blitzapi_company_search.py` (new file)

```python
async def execute_company_search_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**

The `company_filters` dict is the core input. It can come from:
1. `input_data["company"]` or `input_data["company_filters"]` — direct input
2. `input_data["cumulative_context"]["company"]` or `input_data["cumulative_context"]["company_filters"]` — from context
3. Individual filter fields assembled from input_data or step_config:
   - `keywords` / `keywords_include` / `keywords_exclude`
   - `industry` / `industry_include`
   - `hq_country_code` / `country_code`
   - `hq_continent` / `continent`
   - `hq_sales_region` / `sales_region`
   - `employee_range`
   - `founded_year_min` / `founded_year_max`
   - `company_type` / `type_include`
   - `min_linkedin_followers`

If no pre-built `company_filters` dict is provided, assemble one from individual fields. Only include non-empty filters. This lets blueprints pass search criteria through `step_config`.

Also extract:
- `max_results` — from input_data or step_config. Default: 10. Cap at 50.
- `cursor` — from input_data or cumulative_context. Optional.

**Required:** At least one filter must be present (either a `company_filters` dict or at least one individual filter field). If no filters → return failed with `missing_inputs: ["company_filters"]`.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.search_companies(
    api_key=settings.blitzapi_api_key,
    company_filters=company_filters,
    max_results=max_results,
    cursor=cursor,
)
```

**Output:** Flat output with `results` (list of canonical company dicts), `results_count`, `total_results`, `cursor` at top level. Validate through `BlitzAPICompanySearchOutput`.

**Fan-out compatibility:** `results` must be a top-level field in output for pipeline fan-out.

Commit standalone with message: `add company.search.blitzapi operation service`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.search.blitzapi"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_search_blitzapi` from `app.services.blitzapi_company_search`.
3. Add dispatch branch:

```python
if payload.operation_id == "company.search.blitzapi":
    result = await execute_company_search_blitzapi(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire company.search.blitzapi into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_blitzapi_company_search.py` (new file)

### Required test cases:

1. `test_search_companies_missing_api_key` — provider adapter returns `skipped`
2. `test_search_companies_no_filters` — service returns failed with `missing_inputs`
3. `test_search_companies_success` — mock BlitzAPI returning 2 company results. Verify:
   - `status == "found"`
   - `results` is a list of 2 items
   - `results_count == 2`
   - `total_results == 148`
   - `cursor` is populated
   - First result has `company_linkedin_id`, `company_name`, `company_domain`, `description_raw`
4. `test_search_companies_empty_results` — mock BlitzAPI returning `{"results": [], "results_count": 0, "total_results": 0, "cursor": null}`. Verify `status == "not_found"`.
5. `test_search_companies_http_error` — mock HTTP 500. Verify `status == "failed"`.
6. `test_search_companies_with_keyword_filters` — verify `company_filters` with keywords are passed correctly to the provider.
7. `test_search_companies_assembles_filters_from_individual_fields` — pass `keywords_include`, `hq_country_code`, `employee_range` as individual fields. Verify service assembles them into the correct `company_filters` dict.
8. `test_search_companies_pagination` — pass `cursor` value. Verify it's forwarded to provider.
9. `test_search_companies_from_step_config` — verify filters extracted from cumulative_context step_config.

Mock all HTTP calls. Use the example response data from the endpoint reference.

Commit standalone with message: `add tests for company.search.blitzapi operation`

---

## Deliverable 6: Update Documentation

**File:** `docs/SYSTEM_OVERVIEW.md`

Add to Company Search / Discovery section:
```
| `company.search.blitzapi` | BlitzAPI (company search with keyword, industry, location, size, type, founded year filters + pagination) |
```

Update operation count.

**File:** `CLAUDE.md` — update operation count if referenced.

Commit standalone with message: `update documentation for company.search.blitzapi operation`

---

## What is NOT in scope

- No changes to the existing `company.search` operation
- No changes to existing functions in `blitzapi.py`
- No database migrations
- No changes to `run-pipeline.ts`
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and BlitzAPI endpoint URL
(b) Contract class names and field lists
(c) Service function signature, how `company_filters` is assembled (pre-built dict vs individual fields), required inputs
(d) Confirmation that `results` is top-level in output (fan-out compatibility)
(e) Confirmation that each result includes `company_linkedin_id` (from `canonical_company_result`)
(f) Router wiring confirmation
(g) Test count and names
(h) Anything to flag
