# Directive: 3 Standalone BlitzAPI Person Operations

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need dedicated standalone operations for 3 BlitzAPI person endpoints. Currently these endpoints are only accessible through multi-provider waterfalls (`person.search` and `person.contact.resolve_email`). Standalone operations give us deterministic single-provider behavior so we can use them in blueprints where we specifically want BlitzAPI.

---

## Existing code to read before starting

- `app/providers/blitzapi.py` — **critical**. Read `search_icp_waterfall` (~line 523) and `search_employees` (~line 443). These adapters already exist and can be reused directly. Also read `phone_enrich` (~line 596) as pattern reference for the new email adapter. Read `canonical_person_result` (~line 100) for the person mapping function.
- `app/services/person_operations.py` — existing person operation services. Reference for service function patterns.
- `app/contracts/person.py` — existing person contracts. Reference for output models.
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS` and dispatch chain.

---

## The 3 Operations

| # | Operation ID | BlitzAPI Endpoint | Provider Adapter |
|---|---|---|---|
| 1 | `person.search.waterfall_icp_blitzapi` | `POST /v2/search/waterfall-icp-keyword` | **Exists:** `search_icp_waterfall` |
| 2 | `person.search.employee_finder_blitzapi` | `POST /v2/search/employee-finder` | **Exists:** `search_employees` |
| 3 | `person.contact.resolve_email_blitzapi` | `POST /v2/enrichment/email` | **New — build it** |

---

## Operation 1: `person.search.waterfall_icp_blitzapi`

### Provider Adapter

**Already exists:** `blitzapi.search_icp_waterfall` in `app/providers/blitzapi.py`. Do NOT modify it.

Signature:
```python
async def search_icp_waterfall(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
    cascade: list[dict[str, Any]] | None,
    max_results: int,
) -> ProviderAdapterResult:
```

Returns `{"results": [canonical_person_result, ...], "pagination": {...}}` in `mapped`.

### Contract

**File:** `app/contracts/blitzapi_person.py` (new file — all 3 operations' contracts go here)

```python
class WaterfallIcpSearchOutput(BaseModel):
    results: list[Any]
    results_count: int
    source_provider: str = "blitzapi"
```

### Service Function

**File:** `app/services/blitzapi_person_operations.py` (new file — all 3 operations' service functions go here)

```python
async def execute_person_search_waterfall_icp_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `company_linkedin_url` — from input_data or cumulative_context. Aliases: `company_linkedin_url`, `linkedin_url`.
- `cascade` — from input_data or cumulative_context. This is a list of cascade tier objects. If not provided, check `step_config` for it (blueprints may pass cascade config there). If still absent, use a sensible default:
  ```python
  [
      {"include_title": ["VP", "Director", "Head of"], "exclude_title": ["intern", "assistant", "junior"], "location": ["WORLD"], "include_headline_search": False},
      {"include_title": ["CEO", "founder", "cofounder", "CTO", "COO", "CRO"], "exclude_title": [], "location": ["WORLD"], "include_headline_search": False},
  ]
  ```
- `max_results` — from input_data, cumulative_context, or step_config. Default: 10.

**Required:** `company_linkedin_url`. Missing → failed.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.search_icp_waterfall(
    api_key=settings.blitzapi_api_key,
    company_linkedin_url=company_linkedin_url,
    cascade=cascade,
    max_results=max_results,
)
```

**Output:** Extract `results` list and `results_count` from mapped. The `results` list contains canonical person results. Return flat with `results` at top level.

**Fan-out compatibility:** This operation returns a `results` array. When used in a blueprint step with `fan_out: true`, the pipeline runner will create child runs from each result. Ensure `results` is a top-level field in `output`.

---

## Operation 2: `person.search.employee_finder_blitzapi`

### Provider Adapter

**Already exists:** `blitzapi.search_employees` in `app/providers/blitzapi.py`. Do NOT modify it.

Signature:
```python
async def search_employees(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
    job_level: str | list[str] | None,
    job_function: str | list[str] | None,
    country_code: str | list[str] | None,
    max_results: int,
    page: int,
) -> ProviderAdapterResult:
```

### Contract

```python
class EmployeeFinderOutput(BaseModel):
    results: list[Any]
    results_count: int
    pagination: dict[str, Any] | None = None
    source_provider: str = "blitzapi"
```

### Service Function

```python
async def execute_person_search_employee_finder_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `company_linkedin_url` — from input_data or cumulative_context. Aliases: `company_linkedin_url`, `linkedin_url`.
- `job_level` — from input_data, cumulative_context, or step_config. Optional. Allowed values: `C-Team`, `Director`, `Manager`, `VP`, `Staff`, `Other`.
- `job_function` — from input_data, cumulative_context, or step_config. Optional. Allowed values: `Sales & Business Development`, `Engineering`, `Information Technology`, `Human Resources`, `Finance & Accounting`, `Operations`, `Advertising & Marketing`, etc.
- `country_code` — from input_data, cumulative_context, or step_config. Optional. e.g., `["US"]`.
- `max_results` — from input_data or step_config. Default: 10.
- `page` — from input_data or step_config. Default: 1.

**Required:** `company_linkedin_url`. Missing → failed.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.search_employees(
    api_key=settings.blitzapi_api_key,
    company_linkedin_url=company_linkedin_url,
    job_level=job_level,
    job_function=job_function,
    country_code=country_code,
    max_results=max_results,
    page=page,
)
```

**Output:** Same as operation 1 — `results` list + `results_count` + `pagination` at top level.

**Fan-out compatible.**

---

## Operation 3: `person.contact.resolve_email_blitzapi`

### Provider Adapter — NEW

**File:** `app/providers/blitzapi.py` (existing file — add function, do NOT modify existing functions)

```python
async def find_work_email(
    *,
    api_key: str | None,
    person_linkedin_url: str | None,
) -> ProviderAdapterResult:
```

**Endpoint:** `POST https://api.blitz-api.ai/v2/enrichment/email`

**Request body:**
```json
{
  "person_linkedin_url": "https://www.linkedin.com/in/antoine-blitz-5581b7373"
}
```

**Response (success):**
```json
{
  "found": true,
  "email": "antoine@blitz-agency.com",
  "all_emails": [
    {
      "email": "antoine@blitz-agency.com",
      "job_order_in_profile": 1,
      "company_linkedin_url": "https://www.linkedin.com/company/blitz-api",
      "email_domain": "blitz-agency.com"
    }
  ]
}
```

**Logic:**
1. Skip if `api_key` missing → `skipped`, `missing_provider_api_key`
2. Skip if `person_linkedin_url` missing → `skipped`, `missing_required_inputs`
3. Call endpoint with `x-api-key` header and `{"person_linkedin_url": person_linkedin_url}`
4. Use `_blitzapi_request_with_retry`. Timeout: 30 seconds.
5. If `found: true`:
   ```python
   "mapped": {
       "work_email": body.get("email"),
       "all_emails": body.get("all_emails"),
       "source_provider": "blitzapi",
   }
   ```
6. If `found: false` → `status: "not_found"`, `mapped: None`
7. Action name: `"find_work_email"`

Follow the exact error handling pattern of `phone_enrich` in the same file.

### Contract

```python
class FindWorkEmailOutput(BaseModel):
    work_email: str | None = None
    all_emails: list[Any] | None = None
    source_provider: str = "blitzapi"
```

### Service Function

```python
async def execute_person_contact_resolve_email_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `person_linkedin_url` — from input_data or cumulative_context. Aliases: `person_linkedin_url`, `linkedin_url`.

**Required:** `person_linkedin_url`. Missing → failed.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.find_work_email(
    api_key=settings.blitzapi_api_key,
    person_linkedin_url=person_linkedin_url,
)
```

**Output:** Flat with `work_email` and `all_emails` at top level. `work_email` is the primary field — it persists to `person_entities.work_email` via entity state upsert.

---

## Deliverable Structure

### Deliverable 1: Provider Adapter (email only)

**File:** `app/providers/blitzapi.py`

Add `find_work_email` function. Do NOT modify existing functions.

Commit standalone with message: `add BlitzAPI find_work_email provider adapter`

### Deliverable 2: Contracts

**File:** `app/contracts/blitzapi_person.py` (new file)

All 3 output models: `WaterfallIcpSearchOutput`, `EmployeeFinderOutput`, `FindWorkEmailOutput`.

Commit standalone with message: `add BlitzAPI person operation output contracts`

### Deliverable 3: Service Functions

**File:** `app/services/blitzapi_person_operations.py` (new file)

All 3 service functions. Each follows the standard pattern: generate run_id, extract inputs, call provider, validate through contract, return `{run_id, operation_id, status, output, provider_attempts}`.

Commit standalone with message: `add 3 BlitzAPI person operation services`

### Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add all 3 operation IDs to `SUPPORTED_OPERATION_IDS`:
   - `person.search.waterfall_icp_blitzapi`
   - `person.search.employee_finder_blitzapi`
   - `person.contact.resolve_email_blitzapi`
2. Import all 3 service functions from `app.services.blitzapi_person_operations`.
3. Add 3 dispatch branches with `persist_operation_execution` + `DataEnvelope`.

Commit standalone with message: `wire 3 BlitzAPI person operations into execute router`

### Deliverable 5: Tests

**File:** `tests/test_blitzapi_person_operations.py` (new file)

For each of the 3 operations, at minimum:

**Waterfall ICP Search:**
1. `test_waterfall_icp_missing_api_key`
2. `test_waterfall_icp_missing_linkedin_url`
3. `test_waterfall_icp_success` — mock BlitzAPI returning results with person objects. Verify `results` list, `results_count`, canonical person fields.
4. `test_waterfall_icp_not_found` — mock empty results.
5. `test_waterfall_icp_reads_from_cumulative_context`

**Employee Finder:**
6. `test_employee_finder_missing_linkedin_url`
7. `test_employee_finder_success` — verify results + pagination.
8. `test_employee_finder_with_filters` — verify `job_level`, `job_function`, `country_code` are passed through.
9. `test_employee_finder_reads_from_cumulative_context`

**Find Work Email:**
10. `test_find_email_missing_api_key`
11. `test_find_email_missing_linkedin_url`
12. `test_find_email_success` — mock BlitzAPI returning `{"found": true, "email": "...", "all_emails": [...]}`. Verify `work_email` and `all_emails` in output.
13. `test_find_email_not_found`
14. `test_find_email_reads_from_cumulative_context`

Mock all HTTP calls.

Commit standalone with message: `add tests for 3 BlitzAPI person operations`

### Deliverable 6: Update Documentation

**File:** `docs/SYSTEM_OVERVIEW.md`

Add under Person section:
```
| `person.search.waterfall_icp_blitzapi` | BlitzAPI (dedicated cascade ICP search with tier matching) |
| `person.search.employee_finder_blitzapi` | BlitzAPI (dedicated employee search with level/function/location filters) |
| `person.contact.resolve_email_blitzapi` | BlitzAPI (dedicated work email finder from LinkedIn URL) |
```

Update operation count.

**File:** `CLAUDE.md` — update operation count if referenced.

Commit standalone with message: `update documentation for 3 BlitzAPI person operations`

---

## What is NOT in scope

- No changes to existing `person.search` waterfall operation
- No changes to existing `person.contact.resolve_email` waterfall operation
- No changes to existing provider adapter functions (`search_icp_waterfall`, `search_employees`)
- No database migrations
- No changes to `run-pipeline.ts`
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) New provider adapter function signature (`find_work_email`) and endpoint it calls
(b) All 3 contract class names and fields
(c) All 3 service function signatures and required vs optional inputs
(d) Confirmation that `work_email` is top-level in email operation output (for entity state persistence)
(e) Confirmation that `results` is top-level in search operation outputs (for fan-out compatibility)
(f) Router wiring — all 3 operation IDs added
(g) Test count and names
(h) Anything to flag
