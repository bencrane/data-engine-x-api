**Directive: Intent-Based Search Endpoint**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The chat frontend at admin.outboundsolutions.com needs to send high-level search requests like "find VPs of Sales at staffing companies in Texas" and get normalized results back. Today, the search operations (`company.search`, `person.search`, `company.search.blitzapi`) require callers to know provider-specific filter structures and exact enum values. We just built an enum resolution layer (`app/services/enum_registry/`) that translates generic criteria to provider-specific values. This directive builds the endpoint that ties it all together.

**The user experience this enables:**

Chat agent sends:
```json
{
  "search_type": "people",
  "criteria": {
    "seniority": "VP",
    "department": "Sales",
    "industry": "Staffing",
    "location": "Texas",
    "employee_range": "200-1000"
  },
  "limit": 25
}
```

data-engine-x resolves "VP" → Prospeo `"Vice President"` / BlitzAPI `"VP"`, resolves "Sales" → Prospeo `"All Sales"` / BlitzAPI `"Sales & Business Development"`, builds the provider-specific filter objects, executes the search, and returns normalized person results with resolution metadata.

**Existing code to read before starting:**

- `app/services/enum_registry/resolver.py` — `resolve_criteria()`, `resolve_enum()`, `ResolveResult`
- `app/services/enum_registry/field_mappings.py` — `FIELD_REGISTRY`, `get_field_mapping()`, `FieldMapping`
- `app/services/search_operations.py` — `execute_company_search()`, `execute_person_search()`, `_build_prospeo_filters()`, `_search_people_blitzapi()`, `_search_companies_prospeo()`, `_search_companies_blitzapi()`
- `app/services/blitzapi_company_search.py` — `execute_company_search_blitzapi()`, `_build_company_filters()`
- `app/contracts/search.py` — existing search output models (`CompanySearchOutput`, `PersonSearchOutput`)
- `app/providers/prospeo.py` — `search_companies()`, `search_people()` — how filters are passed
- `app/providers/blitzapi.py` — `search_employees()`, `search_companies()` — how filters are passed
- `app/routers/entities_v1.py` lines 40-50 — `_resolve_flexible_auth` pattern (copy this for the new router)
- `app/main.py` — how routers are registered

---

### Deliverable 1: Input/Output Contracts

Create `app/contracts/intent_search.py`:

**Input model:**

```python
class IntentSearchRequest(BaseModel):
    search_type: Literal["companies", "people"]
    criteria: dict[str, str | list[str]]  # generic field names → user-facing values
    provider: str | None = None           # "prospeo", "blitzapi", or None for auto
    limit: int = 25
    page: int = 1
```

Criteria keys are a mix of **enum-resolved fields** and **pass-through fields**.

Enum-resolved fields (go through `resolve_criteria()`):
- `seniority`, `department`, `industry`, `employee_range`, `company_type`, `continent`, `sales_region`, `country_code`

Pass-through fields (used as-is, not enum-resolved):
- `query` — free text search term
- `company_domain` — domain filter
- `company_name` — company name filter
- `company_linkedin_url` — LinkedIn URL (required by some BlitzAPI paths)
- `job_title` — free text job title (separate from seniority/department enums)
- `location` — free text location (for Prospeo's `person_location_search`)

The service must separate these two groups. Do not pass pass-through fields into `resolve_criteria()`.

**Resolution metadata model:**

```python
class EnumResolutionDetail(BaseModel):
    input_value: str
    resolved_value: str | None
    provider_field: str | None
    match_type: str       # "exact", "synonym", "fuzzy", "none"
    confidence: float
```

**Output model:**

```python
class IntentSearchOutput(BaseModel):
    search_type: str
    provider_used: str
    results: list[dict[str, Any]]
    result_count: int
    enum_resolution: dict[str, EnumResolutionDetail]
    unresolved_fields: list[str]   # criteria fields that resolved to None
    pagination: dict[str, Any] | None = None
```

Commit standalone.

### Deliverable 2: Intent Search Service

Create `app/services/intent_search.py`:

**Core function:**

```python
async def execute_intent_search(
    *,
    search_type: str,
    criteria: dict[str, str | list[str]],
    provider: str | None,
    limit: int,
    page: int,
) -> dict[str, Any]:
```

**Flow:**

1. **Separate criteria** into enum fields and pass-through fields. Use a constant set to classify:

```python
ENUM_FIELDS = {"seniority", "department", "industry", "employee_range", "company_type", "continent", "sales_region", "country_code"}
PASS_THROUGH_FIELDS = {"query", "company_domain", "company_name", "company_linkedin_url", "job_title", "location"}
```

Any criteria key not in either set should be ignored (do not error).

2. **Determine provider order.** If `provider` is explicitly set (`"prospeo"` or `"blitzapi"`), use only that provider. If `provider` is `None` (auto), try providers in this order:
   - For `search_type == "people"`: `["prospeo", "blitzapi"]`
   - For `search_type == "companies"`: `["prospeo", "blitzapi"]`

   Prospeo first is the default because it has broader text-based search. The executor can make this configurable via `get_settings()` if a config key already exists, but do not add new config keys.

3. **For each provider to try:**

   a. **Resolve enums:** Extract only the enum fields from criteria (as `dict[str, str]` — if a value is a list, resolve each item and collect valid results). Call `resolve_criteria(provider_name, enum_criteria)` from the enum registry.

   b. **Track resolution metadata:** Build an `enum_resolution` dict mapping each enum field to its `ResolveResult`. Track which fields resolved to `None` in `unresolved_fields`.

   c. **Build provider-specific filters:** This is the core translation step. Combine the resolved enum values with the pass-through values to build the filter object that the provider adapter expects.

   **For Prospeo person search** — build a filter dict compatible with `prospeo.search_people()`:
   ```python
   filters = {}
   # From resolved enums:
   if resolved_seniority:
       filters["person_seniority"] = {"include": [resolved_seniority]}
   if resolved_department:
       filters["person_department"] = {"include": [resolved_department]}
   if resolved_industry:
       filters["company"] = filters.get("company", {})
       filters["company"]["industry"] = {"include": [resolved_industry]}
   if resolved_employee_range:
       filters["company"] = filters.get("company", {})
       filters["company"]["employee_range"] = {"include": [resolved_employee_range]}
   # From pass-through:
   if job_title:
       filters["person_job_title"] = {"include": [job_title]}
   if location:
       filters["person_location_search"] = {"include": location if isinstance(location, list) else [location]}
   if company_domain:
       filters.setdefault("company", {}).setdefault("websites", {})["include"] = [company_domain]
   elif company_name:
       filters.setdefault("company", {}).setdefault("names", {})["include"] = [company_name]
   ```
   Then call `prospeo.search_people(api_key=..., query=job_title or query, page=page, provider_filters={"prospeo": filters})`.

   **For Prospeo company search** — similar structure:
   ```python
   filters = {}
   if resolved_industry:
       filters["company"] = filters.get("company", {})
       filters["company"]["industry"] = {"include": [resolved_industry]}
   if resolved_employee_range:
       filters["company"] = filters.get("company", {})
       filters["company"]["employee_range"] = {"include": [resolved_employee_range]}
   if company_domain:
       filters.setdefault("company", {}).setdefault("websites", {})["include"] = [company_domain]
   elif company_name:
       filters.setdefault("company", {}).setdefault("names", {})["include"] = [company_name]
   ```
   Then call `prospeo.search_companies(api_key=..., query=query or company_name, page=page, provider_filters={"prospeo": filters})`.

   **For BlitzAPI person search** — call `blitzapi.search_employees()` directly:
   ```python
   blitzapi.search_employees(
       api_key=...,
       company_linkedin_url=company_linkedin_url,
       job_level=resolved_seniority,        # from enum resolution
       job_function=resolved_department,     # from enum resolution
       country_code=resolved_country_code,   # from enum resolution
       max_results=limit,
       page=page,
   )
   ```

   **For BlitzAPI company search** — build a filter dict compatible with `blitzapi.search_companies()`:
   ```python
   company_filters = {}
   if resolved_industry:
       company_filters["industry"] = {"include": [resolved_industry]}
   if resolved_employee_range:
       company_filters["employee_range"] = [resolved_employee_range]
   if resolved_company_type:
       company_filters["type"] = {"include": [resolved_company_type]}
   if resolved_continent:
       company_filters.setdefault("hq", {})["continent"] = [resolved_continent]
   if resolved_country_code:
       company_filters.setdefault("hq", {})["country_code"] = [resolved_country_code]
   if resolved_sales_region:
       company_filters.setdefault("hq", {})["sales_region"] = [resolved_sales_region]
   if query or company_name:
       company_filters["keywords"] = {"include": [query or company_name]}
   if company_domain:
       company_filters["website"] = {"include": [company_domain]}
   ```
   Then call `blitzapi.search_companies(api_key=..., company_filters=company_filters, max_results=limit)`.

   d. **Extract results:** Parse the adapter response using the same pattern as existing search services — `result.get("mapped", {}).get("results", [])`.

   e. **If results found, return immediately.** Do not try the next provider. If no results, try next provider in the order.

4. **Build response:**

```python
{
    "search_type": search_type,
    "provider_used": provider_that_returned_results,
    "results": results_list,
    "result_count": len(results_list),
    "enum_resolution": {field: detail for each resolved field},
    "unresolved_fields": [fields that resolved to None],
    "pagination": pagination_from_provider,
    "provider_attempts": all_attempts,
}
```

**Important implementation notes:**

- Call provider adapters directly (`prospeo.search_people()`, `blitzapi.search_employees()`, etc.), NOT the existing service functions like `execute_person_search()`. The existing service functions have their own filter-building logic that would conflict with the resolved filters. The intent search service owns its own filter construction.
- Get API keys from `get_settings()` — same pattern as all existing services.
- Handle list values in criteria: if a criteria value is a list (e.g., `"industry": ["SaaS", "Staffing"]`), resolve each item individually and collect all valid resolved values into a list.
- If zero enum fields resolve for a provider, still attempt the search if pass-through fields provide enough context (e.g., company_domain alone is enough for a company search). Only skip a provider if there are genuinely no usable filters.

Commit standalone.

### Deliverable 3: Router

Create `app/routers/search_v1.py`:

Single endpoint: `POST /search`

```python
router = APIRouter()

@router.post("/search")
async def intent_search(request: Request):
```

**Auth:** Use `_resolve_flexible_auth` — same pattern as `app/routers/entities_v1.py` lines 40-50. Try super-admin first, fall back to tenant auth.

**Request parsing:** Parse the body as `IntentSearchRequest`. Clamp `limit` to `[1, 100]` and `page` to `[1, ∞)`.

**Dispatch:** Call `execute_intent_search()` with the parsed fields.

**Response:** Validate through `IntentSearchOutput` and wrap in `DataEnvelope(data=result)`.

Commit standalone.

### Deliverable 4: Register Router

In `app/main.py`:

1. Add `search_v1` to the import block.
2. Register: `app.include_router(search_v1.router, prefix="/api/v1", tags=["search-v1"])`

This puts the endpoint at `POST /api/v1/search`.

Commit standalone (can be combined with D3 if trivial).

### Deliverable 5: Tests

Create `tests/test_intent_search.py`.

**Minimum 10 tests:**

**Person search (4):**
1. `test_person_search_prospeo_with_enum_resolution` — Mock `prospeo.search_people` to return results. Send criteria `{"seniority": "VP", "department": "Sales", "location": "Texas"}`. Assert:
   - `provider_used == "prospeo"`
   - Prospeo adapter was called with filters containing `person_seniority: {"include": ["Vice President"]}` (resolved from "VP")
   - `enum_resolution["seniority"]["resolved_value"] == "Vice President"`
   - `enum_resolution["seniority"]["match_type"] == "synonym"`

2. `test_person_search_blitzapi_with_enum_resolution` — Mock BlitzAPI adapter. Send criteria with `provider: "blitzapi"`, `{"seniority": "Director", "department": "Engineering"}`. Assert:
   - `provider_used == "blitzapi"`
   - `search_employees` was called with `job_level="Director"`, `job_function="Engineering"`

3. `test_person_search_fallback_to_blitzapi` — Mock Prospeo returning empty results, BlitzAPI returning results. Send criteria without explicit provider. Assert Prospeo was tried first, then BlitzAPI returned results.

4. `test_person_search_with_pass_through_fields` — Send criteria with `{"job_title": "Account Executive", "company_domain": "salestalent.inc"}`. Assert these are passed through without enum resolution.

**Company search (3):**
5. `test_company_search_prospeo_with_industry` — Mock Prospeo adapter. Send `search_type: "companies"`, criteria `{"industry": "Staffing", "employee_range": "201-500"}`. Assert Prospeo was called with correct filter structure.

6. `test_company_search_blitzapi_with_filters` — Mock BlitzAPI adapter. Send `search_type: "companies"`, `provider: "blitzapi"`, criteria `{"industry": "Computer Software", "company_type": "Privately Held", "continent": "North America"}`. Assert company_filters dict was built correctly.

7. `test_company_search_with_query_only` — Send criteria `{"query": "staffing companies texas"}` with no enum fields. Assert search proceeds with query as the primary filter.

**Enum resolution metadata (2):**
8. `test_unresolved_fields_in_response` — Send criteria with a field that won't resolve (e.g., `"seniority": "xyzzy123"`). Assert `unresolved_fields` includes `"seniority"` and `enum_resolution["seniority"]["match_type"] == "none"`.

9. `test_list_criteria_values` — Send criteria with `{"industry": ["SaaS", "Staffing"]}` (list of values). Assert both values are individually resolved and the provider receives a list of resolved values.

**Edge cases (1):**
10. `test_missing_search_type_or_criteria` — Send request with empty criteria. Assert the response has `status: "failed"` with a clear missing_inputs message.

**Mocking strategy:** Mock provider adapter functions (`prospeo.search_people`, `prospeo.search_companies`, `blitzapi.search_employees`, `blitzapi.search_companies`) using `unittest.mock.patch` or `pytest-mock`. Do NOT mock the enum resolution layer — let it run against the real constants so the tests validate the full resolution path.

Commit standalone.

---

**What is NOT in scope:**

- No changes to existing search operations (`execute_company_search`, `execute_person_search`, etc.). The intent search is additive.
- No changes to existing provider adapters. The intent search calls them directly with resolved filters.
- No changes to the enum registry. It's consumed as-is.
- No new operation IDs in `SUPPORTED_OPERATION_IDS`. This is a separate endpoint, not an operation.
- No Trigger.dev changes.
- No database changes.
- No deploy.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the input contract — what fields are accepted and how list values are handled, (b) the filter building — show the Prospeo and BlitzAPI filter shapes for both person and company search, (c) the provider fallback behavior — what happens when the first provider returns no results, (d) the enum resolution metadata — what the response looks like for resolved vs unresolved fields, (e) test count and what each covers, (f) anything to flag — especially if the Prospeo or BlitzAPI filter structures needed adjustments from what the directive specified.
