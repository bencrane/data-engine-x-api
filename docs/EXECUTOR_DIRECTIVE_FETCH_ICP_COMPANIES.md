# Directive: `company.fetch.icp_candidates` Operation — Fetch Companies for ICP Research from HQ

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a temporary table in HQ (`api.revenueinfra.com`) that holds companies queued for ICP job title research via Parallel.ai Deep Research. This operation fetches those companies so they can be used as input to a blueprint. The endpoint returns `company_name`, `domain`, and `description` per company. This operation is a simple single-provider adapter that calls the HQ endpoint and returns the results as a fan-out-capable list.

---

## HQ Endpoint Reference

**Endpoint:** `POST https://api.revenueinfra.com/api/admin/temp/companies-for-parallel-icp`

**Auth:** None required (admin temp endpoint).

**Request body:**
```json
{
  "limit": 10
}
```

`limit` is optional. If omitted, returns all records.

**Response:**
```json
{
  "count": 3,
  "data": [
    {
      "id": 2,
      "company_name": "Abacus.AI",
      "domain": "abacus.ai",
      "description": "Abacus AI is the world's best AI super assistant...",
      "created_at": "2026-02-24T17:53:22.919167+00:00"
    },
    {
      "id": 3,
      "company_name": "Tailscale",
      "domain": "tailscale.com",
      "description": "Tailscale develops a software-defined networking platform...",
      "created_at": "2026-02-24T17:53:22.919167+00:00"
    }
  ]
}
```

Each record has: `id` (int), `company_name` (string), `domain` (string), `description` (string), `created_at` (string).

---

## Existing code to read before starting

- `app/providers/revenueinfra/alumni.py` — reference pattern for calling an HQ endpoint (provider adapter)
- `app/providers/revenueinfra/_common.py` — shared config (`_configured_base_url`, `_PROVIDER`, helpers)
- `app/providers/revenueinfra/__init__.py` — re-exports (add new function here)
- `app/services/research_operations.py` — reference pattern for operation service function (e.g., `execute_company_research_lookup_alumni`)
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — settings class (`revenueinfra_api_url` already exists)

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/revenueinfra/fetch_icp_companies.py` (new file)

Create `fetch_icp_companies` function following the exact pattern of `alumni.py`:

```python
async def fetch_icp_companies(
    *,
    base_url: str,
    limit: int | None = None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Call `POST {base_url}/api/admin/temp/companies-for-parallel-icp` with JSON body `{"limit": limit}` if limit is provided, otherwise `{}`.
2. No auth header needed (this is a temp admin endpoint).
3. Timeout: 30 seconds.
4. If HTTP error → `failed`.
5. Parse response. If `data` is an empty array → `not_found`.
6. Map response to canonical output:

```python
"mapped": {
    "company_count": body.get("count", 0),
    "results": [
        {
            "company_name": item.get("company_name"),
            "domain": item.get("domain"),
            "company_description": item.get("description"),
        }
        for item in body.get("data", [])
    ],
}
```

**Important:** The output key must be `results` (a list of dicts) because this is how the pipeline runner's `extractFanOutResults` function reads fan-out entities. Each item in `results` becomes a child pipeline run with that item as its cumulative context.

Also note: the HQ response field is `description` but we map it to `company_description` — this matches what the downstream `company.derive.icp_job_titles` step expects in cumulative context.

**Update `__init__.py`** to re-export `fetch_icp_companies`.

Commit standalone with message: `add revenueinfra provider adapter for fetching ICP candidate companies`

---

## Deliverable 2: Contract

**File:** `app/contracts/icp_companies.py` (new file)

```python
from pydantic import BaseModel


class IcpCompanyItem(BaseModel):
    company_name: str | None = None
    domain: str | None = None
    company_description: str | None = None


class FetchIcpCompaniesOutput(BaseModel):
    company_count: int | None = None
    results: list[IcpCompanyItem] | None = None
    source_provider: str = "revenueinfra"
```

Commit standalone with message: `add contract for company.fetch.icp_candidates operation`

---

## Deliverable 3: Service Operation

**File:** `app/services/research_operations.py`

Add:

```python
async def execute_company_fetch_icp_candidates(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `limit` from `input_data.get("limit")` or `input_data.get("cumulative_context", {}).get("limit")` or from `input_data.get("options", {}).get("limit")`. Default: `None` (fetch all).

**Provider call:**
```python
settings = get_settings()
result = await revenueinfra.fetch_icp_companies(
    base_url=settings.revenueinfra_api_url,
    limit=limit,
)
```

**Validate output** with `FetchIcpCompaniesOutput` contract. Follow the exact attempt tracking + status derivation pattern from `execute_company_research_lookup_alumni`.

**Operation ID:** `"company.fetch.icp_candidates"`

If the adapter returns `not_found` (empty data), return `status: "not_found"`.
If the adapter returns `found` with results, return `status: "found"` with the mapped output.

Commit standalone with message: `add company.fetch.icp_candidates operation service`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.fetch.icp_candidates"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_fetch_icp_candidates` from `app.services.research_operations`.
3. Add dispatch branch:

```python
if payload.operation_id == "company.fetch.icp_candidates":
    result = await execute_company_fetch_icp_candidates(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire company.fetch.icp_candidates into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_fetch_icp_companies.py` (new file)

Follow the pattern from `tests/test_alumni.py`.

### Required test cases:

1. `test_fetch_icp_companies_success` — mock HQ response with 3 companies. Verify `status: "found"`, `output.company_count == 3`, `output.results` has 3 items, each with `company_name`, `domain`, `company_description`.
2. `test_fetch_icp_companies_empty` — mock HQ response with `{"count": 0, "data": []}`. Verify `status: "not_found"`.
3. `test_fetch_icp_companies_with_limit` — mock HQ, verify the request body contains `{"limit": 5}` when limit=5 is passed.
4. `test_fetch_icp_companies_http_error` — mock HTTP 500. Verify `status: "failed"`.
5. `test_fetch_icp_companies_maps_description_to_company_description` — verify the HQ field `description` is mapped to `company_description` in the output items.

Mock all HTTP calls. Use realistic data (Abacus.AI, Tailscale, Fivetran from the real endpoint).

Commit standalone with message: `add tests for company.fetch.icp_candidates operation`

---

## What is NOT in scope

- No changes to the HQ endpoint (already built)
- No changes to `run-pipeline.ts` or the Parallel Deep Research function
- No blueprint creation
- No deploy commands
- No database migrations

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and HQ endpoint it calls
(b) Contract field counts (IcpCompanyItem, FetchIcpCompaniesOutput)
(c) Output `results` key confirmation (must be `results` for fan-out compatibility)
(d) Field mapping confirmation (`description` → `company_description`)
(e) Router wiring confirmation
(f) Test count and names
(g) Anything to flag
