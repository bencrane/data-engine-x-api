# Directive: `company.research.lookup_customers_resolved` — HQ Resolved Customer Lookup

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** HQ has a new endpoint that returns a company's known customers with their domains and LinkedIn URLs already resolved. This is faster and cheaper than the Gemini discover-customers call and should be tried first as a DB lookup before falling back to Gemini.

---

## HQ Endpoint Reference

**Endpoint:** `POST https://api.revenueinfra.com/run/companies/db/company-customers/lookup-resolved`

**Auth:** None (this is a `/run/` endpoint).

**Request body:**
```json
{
  "domain": "vanta.com"
}
```

**Response (success):**
```json
{
  "success": true,
  "domain": "vanta.com",
  "customer_count": 5,
  "customers": [
    {
      "origin_company_name": "Vanta",
      "origin_company_domain": "vanta.com",
      "customer_name": "Notion",
      "customer_domain": "notion.so",
      "customer_linkedin_url": "https://www.linkedin.com/company/notion-hq"
    }
  ]
}
```

**Response (failure):**
```json
{
  "success": false,
  "domain": "vanta.com",
  "error": "...",
  "traceback": "..."
}
```

---

## Existing code to read before starting

- `app/providers/revenueinfra/customers.py` — existing `lookup_customers` adapter for the non-resolved endpoint. Follow the same pattern.
- `app/providers/revenueinfra/_common.py` — shared base URL, helpers.
- `app/providers/revenueinfra/__init__.py` — re-exports.
- `app/services/hq_workflow_operations.py` — add the new service function here alongside the other HQ workflow operations.
- `app/contracts/hq_workflow.py` — add the new contract here.
- `app/routers/execute_v1.py` — wire in.

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/revenueinfra/customers.py` (existing file — add function, do NOT modify existing functions)

```python
async def lookup_customers_resolved(
    *,
    base_url: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `domain` is missing → `skipped`, `missing_required_inputs`
2. POST to `{base_url}/run/companies/db/company-customers/lookup-resolved` with `{"domain": domain}`
3. No auth header.
4. Timeout: 30 seconds.
5. If `success: true` and `customers` is a non-empty list:
   ```python
   "mapped": {
       "customers": body["customers"],
       "customer_count": body.get("customer_count", len(body["customers"])),
       "source_provider": "revenueinfra",
   }
   ```
   Status: `"found"`
6. If `success: true` but `customers` is empty or null → `status: "not_found"`, mapped with empty customers list.
7. If `success: false` → `status: "failed"`

Update `app/providers/revenueinfra/__init__.py` to re-export.

Commit standalone with message: `add HQ lookup-customers-resolved provider adapter`

---

## Deliverable 2: Contract

**File:** `app/contracts/hq_workflow.py` (existing file — add model)

```python
class LookupCustomersResolvedOutput(BaseModel):
    customers: list[Any] | None = None
    customer_count: int | None = None
    source_provider: str = "revenueinfra"
```

Commit standalone with message: `add LookupCustomersResolvedOutput contract`

---

## Deliverable 3: Service Function

**File:** `app/services/hq_workflow_operations.py` (existing file — add function)

```python
async def execute_company_research_lookup_customers_resolved(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `domain` — from input_data or cumulative_context. Aliases: `domain`, `company_domain`, `canonical_domain`.

**Required:** `domain`. Missing → failed.

**Provider call:**
```python
settings = get_settings()
result = await revenueinfra.lookup_customers_resolved(
    base_url=settings.revenueinfra_api_url,
    domain=domain,
)
```

Validate through `LookupCustomersResolvedOutput`. Return flat output.

Commit standalone with message: `add company.research.lookup_customers_resolved operation service`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.research.lookup_customers_resolved"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_research_lookup_customers_resolved` from `app.services.hq_workflow_operations`.
3. Add dispatch branch with `persist_operation_execution` + `DataEnvelope`.

Commit standalone with message: `wire company.research.lookup_customers_resolved into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_hq_lookup_customers_resolved.py` (new file)

1. `test_lookup_missing_domain` — service returns failed
2. `test_lookup_success` — mock HQ returning the Vanta example. Verify `customers` list, `customer_count`, customer fields (`customer_name`, `customer_domain`, `customer_linkedin_url`).
3. `test_lookup_empty_customers` — mock HQ returning `success: true` with `customers: []`. Verify `status == "not_found"`.
4. `test_lookup_failure` — mock HQ returning `success: false`. Verify `status == "failed"`.
5. `test_lookup_reads_from_cumulative_context` — verify domain extracted from cumulative context.

Mock all HTTP calls.

Commit standalone with message: `add tests for company.research.lookup_customers_resolved operation`

---

## Deliverable 6: Update Documentation

Update `docs/SYSTEM_OVERVIEW.md` — add to Company Research section. Update operation count.

Commit standalone with message: `update documentation for company.research.lookup_customers_resolved operation`

---

## What is NOT in scope

- No changes to the existing `company.research.lookup_customers` operation
- No blueprint changes (the chief agent handles blueprint updates)
- No database migrations
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and HQ endpoint URL
(b) Contract fields
(c) Service function — confirm `domain` alias list
(d) Confirmation that `customers` list is top-level in output (for downstream steps to read customer names)
(e) Router wiring confirmation
(f) Test count and names
(g) Anything to flag
