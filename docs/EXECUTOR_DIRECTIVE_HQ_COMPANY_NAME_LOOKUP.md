# Directive: `company.resolve.domain_from_name_hq` — HQ Company Name Lookup

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need a dedicated operation that resolves a company name to its domain and LinkedIn URL via HQ's `/run/lookup-company-by-name` endpoint. This is used in the AlumniGTM prospect resolution pipeline — after scraping Sales Navigator, each prospect has a `current_company_name` but no domain. This operation attempts a fast DB lookup on HQ before falling back to slower resolution methods.

---

## HQ Endpoint Reference

**Endpoint:** `POST https://api.revenueinfra.com/run/lookup-company-by-name`

**Auth:** None (this is a `/run/` endpoint).

**Request body:**
```json
{
  "company_name": "Datadog"
}
```

**Response (found):**
```json
{
  "success": true,
  "found": true,
  "match_type": "exact_cleaned_name",
  "company_name": "Datadog",
  "matched_name": "Datadog",
  "domain": "datadoghq.com",
  "linkedin_url": "https://www.linkedin.com/company/datadog"
}
```

**Response (not found):**
```json
{
  "success": true,
  "found": false,
  "company_name": "Salesforce",
  "reason": "no_unique_match",
  "matches_found": 0
}
```

The endpoint is intentionally strict — it only returns a match when there's a single unambiguous result.

---

## Existing code to read before starting

- `app/providers/revenueinfra/infer_linkedin_url.py` — closest pattern reference (HQ `/run/` endpoint, no auth, returns company identifiers)
- `app/providers/revenueinfra/_common.py` — shared base URL, helpers
- `app/providers/revenueinfra/__init__.py` — re-exports
- `app/services/hq_workflow_operations.py` — existing HQ workflow service functions. Add the new one here.
- `app/contracts/hq_workflow.py` — existing HQ workflow contracts. Add the new one here.
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS` and dispatch chain.

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/revenueinfra/lookup_company_by_name.py` (new file)

```python
async def lookup_company_by_name(
    *,
    base_url: str | None,
    company_name: str | None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `company_name` is missing → `skipped`, `missing_required_inputs`
2. POST to `{base_url}/run/lookup-company-by-name` with `{"company_name": company_name}`
3. No auth header needed.
4. Timeout: 30 seconds.
5. If `found: true`:
   ```python
   "mapped": {
       "company_domain": body.get("domain"),
       "company_linkedin_url": body.get("linkedin_url"),
       "match_type": body.get("match_type"),
       "matched_name": body.get("matched_name"),
       "source_provider": "revenueinfra",
   }
   ```
6. If `found: false` → `status: "not_found"`, `mapped: None`

**Important:** Map `domain` → `company_domain` and `linkedin_url` → `company_linkedin_url` in output. These are the canonical field names that chain into cumulative context and entity state.

Update `app/providers/revenueinfra/__init__.py` to re-export.

Commit standalone with message: `add HQ lookup-company-by-name provider adapter`

---

## Deliverable 2: Contract

**File:** `app/contracts/hq_workflow.py` (existing file — add model, do NOT modify existing models)

```python
class LookupCompanyByNameOutput(BaseModel):
    company_domain: str | None = None
    company_linkedin_url: str | None = None
    match_type: str | None = None
    matched_name: str | None = None
    source_provider: str = "revenueinfra"
```

Commit standalone with message: `add LookupCompanyByNameOutput contract`

---

## Deliverable 3: Service Function

**File:** `app/services/hq_workflow_operations.py` (existing file — add function, do NOT modify existing functions)

```python
async def execute_company_resolve_domain_from_name_hq(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `company_name` — from input_data or cumulative_context. Check aliases: `company_name`, `current_company_name`, `canonical_name`, `name`.

The alias `current_company_name` is critical — this is the field name from Sales Nav prospect data in cumulative context after fan-out.

**Required:** `company_name`. Missing → failed.

**Provider call:**
```python
settings = get_settings()
result = await revenueinfra.lookup_company_by_name(
    base_url=settings.revenueinfra_api_url,
    company_name=company_name,
)
```

Validate through `LookupCompanyByNameOutput`. Return flat output.

Commit standalone with message: `add company.resolve.domain_from_name_hq operation service`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.resolve.domain_from_name_hq"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_resolve_domain_from_name_hq` from `app.services.hq_workflow_operations`.
3. Add dispatch branch with `persist_operation_execution` + `DataEnvelope`.

Commit standalone with message: `wire company.resolve.domain_from_name_hq into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_hq_company_name_lookup.py` (new file)

1. `test_lookup_missing_company_name` — service returns failed
2. `test_lookup_success` — mock HQ returning the Datadog success response. Verify `company_domain == "datadoghq.com"`, `company_linkedin_url` populated, `match_type` populated.
3. `test_lookup_not_found` — mock HQ returning `found: false`. Verify `status == "not_found"`.
4. `test_lookup_http_error` — mock HTTP 500. Verify `status == "failed"`.
5. `test_lookup_reads_current_company_name` — pass `current_company_name` in cumulative_context (not `company_name`). Verify it's extracted correctly. This tests the Sales Nav fan-out context path.

Mock all HTTP calls.

Commit standalone with message: `add tests for company.resolve.domain_from_name_hq operation`

---

## Deliverable 6: Update Documentation

Update `docs/SYSTEM_OVERVIEW.md` — add to Resolution / CRM Cleanup section. Update operation count.

Commit standalone with message: `update documentation for company.resolve.domain_from_name_hq operation`

---

## What is NOT in scope

- No changes to HQ
- No database migrations
- No changes to `run-pipeline.ts`
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and HQ endpoint URL
(b) Contract fields
(c) Service function — confirm `current_company_name` is in the alias list
(d) Confirmation `company_domain` and `company_linkedin_url` are top-level output fields
(e) Router wiring confirmation
(f) Test count and names
(g) Anything to flag
