# Directive: HQ Workflow Operations (6 Operations)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The AlumniGTM pipeline needs 6 new operations that wrap HQ endpoints (api.revenueinfra.com). 5 are Gemini-backed research/derive operations routed through HQ's `/run/` endpoints. 1 is a Claude-backed tool. All follow the existing RevenueInfra provider adapter pattern — no auth header needed for `/run/` routes, just POST with JSON body.

These operations will be assembled into a blueprint in a separate directive. This directive covers building all 6 operations end-to-end.

---

## Existing code to read before starting

- `app/providers/revenueinfra/_common.py` — shared base URL, provider name, `_as_str`, `_configured_base_url`
- `app/providers/revenueinfra/customers.py` — reference pattern for a `/run/` endpoint adapter (no auth, httpx POST, parse response, return `ProviderAdapterResult`)
- `app/providers/revenueinfra/__init__.py` — re-exports. Add your new exports here.
- `app/services/research_operations.py` — reference for research operation service functions
- `app/contracts/company_research.py` — reference for research output contracts
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS` and dispatch chain

---

## The 6 Operations

| # | Operation ID | HQ Endpoint | Auth |
|---|---|---|---|
| 1 | `company.research.infer_linkedin_url` | `POST /run/companies/gemini/linkedin-url/get` | None |
| 2 | `company.research.icp_job_titles_gemini` | `POST /run/companies/gemini/icp-job-titles/research` | None |
| 3 | `company.research.discover_customers_gemini` | `POST /run/companies/gemini/customers-of/discover` | None |
| 4 | `company.derive.icp_criterion` | `POST /run/companies/gemini/icp-criterion/generate` | None |
| 5 | `company.derive.salesnav_url` | `POST /run/tools/claude/salesnav-url/build` | None |
| 6 | `company.derive.evaluate_icp_fit` | `POST /run/companies/gemini/icp-fit/evaluate` | None |

---

## Operation 1: `company.research.infer_linkedin_url`

### Endpoint

```
POST {base_url}/run/companies/gemini/linkedin-url/get
```

**Request:**
```json
{
  "company_name": "Salesforce",
  "domain": "salesforce.com"
}
```

**Response:**
```json
{
  "success": true,
  "company_name": "Salesforce",
  "linkedin_url": "https://www.linkedin.com/company/salesforce",
  "input_tokens": 150,
  "output_tokens": 30,
  "cost_usd": 0.001,
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/infer_linkedin_url.py` (new file)

```python
async def infer_linkedin_url(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
```

- Skip if `company_name` is missing → `skipped`, `missing_required_inputs`
- POST to `{base_url}/run/companies/gemini/linkedin-url/get` with `{"company_name": ..., "domain": ...}`
- Timeout: 30 seconds
- If `success: true` and `linkedin_url` present → `status: "found"`
- Mapped output: `{"company_linkedin_url": body["linkedin_url"], "source_provider": "revenueinfra"}`
- If `success: false` or no `linkedin_url` → `status: "not_found"`

**Important:** Map `linkedin_url` from response to `company_linkedin_url` in output. This is the canonical field name used by downstream steps and entity state.

Update `__init__.py` to re-export.

### Contract

**File:** `app/contracts/hq_workflow.py` (new file — all 6 operations' contracts go here)

```python
class InferLinkedInUrlOutput(BaseModel):
    company_linkedin_url: str | None = None
    source_provider: str = "revenueinfra"
```

### Service function

**File:** `app/services/hq_workflow_operations.py` (new file — all 6 operations' service functions go here)

```python
async def execute_company_research_infer_linkedin_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `company_name` from input_data / cumulative_context (aliases: `company_name`, `canonical_name`, `name`)
- Extract `domain` from input_data / cumulative_context (aliases: `domain`, `company_domain`, `canonical_domain`)
- Required: `company_name`. Missing → failed.
- Call provider. Validate with contract. Return flat output.

---

## Operation 2: `company.research.icp_job_titles_gemini`

### Endpoint

```
POST {base_url}/run/companies/gemini/icp-job-titles/research
```

**Request:**
```json
{
  "company_name": "Salesforce",
  "domain": "salesforce.com",
  "company_description": "CRM and enterprise cloud software"
}
```

**Response:**
```json
{
  "success": true,
  "domain": "salesforce.com",
  "company_name": "Salesforce",
  "inferred_product": "CRM platform",
  "buyer_persona": "Sales and marketing leaders",
  "titles": [{"title": "VP of Sales", "role": "champion"}],
  "champion_titles": ["VP of Sales", "Sales Director"],
  "evaluator_titles": ["Sales Operations Manager"],
  "decision_maker_titles": ["CRO", "CEO"],
  "input_tokens": 500,
  "output_tokens": 200,
  "cost_usd": 0.005,
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/icp_job_titles_gemini.py` (new file)

```python
async def research_icp_job_titles_gemini(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
    company_description: str | None = None,
) -> ProviderAdapterResult:
```

- Skip if `company_name` and `domain` are both missing → `skipped`
- POST to `{base_url}/run/companies/gemini/icp-job-titles/research`
- Timeout: 60 seconds (LLM call, can be slow)
- Mapped output: pass through `inferred_product`, `buyer_persona`, `titles`, `champion_titles`, `evaluator_titles`, `decision_maker_titles` from response body. Add `source_provider: "revenueinfra"`.

Update `__init__.py`.

### Contract

```python
class GeminiIcpJobTitlesOutput(BaseModel):
    inferred_product: str | None = None
    buyer_persona: str | None = None
    titles: list[Any] | None = None
    champion_titles: list[str] | None = None
    evaluator_titles: list[str] | None = None
    decision_maker_titles: list[str] | None = None
    source_provider: str = "revenueinfra"
```

### Service function

```python
async def execute_company_research_icp_job_titles_gemini(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `company_name`, `domain`, `company_description` (aliases: `company_description`, `description_raw`, `description`)
- Required: `company_name` or `domain`. Missing both → failed.
- Call provider. Validate. Return flat output.

---

## Operation 3: `company.research.discover_customers_gemini`

### Endpoint

```
POST {base_url}/run/companies/gemini/customers-of/discover
```

**Request:**
```json
{
  "company_name": "Salesforce",
  "domain": "salesforce.com"
}
```

**Response:**
```json
{
  "success": true,
  "domain": "salesforce.com",
  "company_name": "Salesforce",
  "customers": [
    {"name": "Toyota", "domain": "toyota.com"},
    {"name": "American Express", "domain": "americanexpress.com"}
  ],
  "customer_count": 2,
  "input_tokens": 300,
  "output_tokens": 100,
  "cost_usd": 0.003,
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/discover_customers_gemini.py` (new file)

```python
async def discover_customers_gemini(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
```

- Skip if `company_name` and `domain` are both missing → `skipped`
- POST to `{base_url}/run/companies/gemini/customers-of/discover`
- Timeout: 60 seconds
- Mapped output: `customers` (list), `customer_count` (int), `source_provider: "revenueinfra"`
- If `success: true` but `customers` is empty or null → `status: "not_found"`

Update `__init__.py`.

### Contract

```python
class DiscoverCustomersGeminiOutput(BaseModel):
    customers: list[Any] | None = None
    customer_count: int | None = None
    source_provider: str = "revenueinfra"
```

### Service function

```python
async def execute_company_research_discover_customers_gemini(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `company_name`, `domain`
- Required: `company_name` or `domain`. Missing both → failed.
- Call provider. Validate. Return flat output.

---

## Operation 4: `company.derive.icp_criterion`

### Endpoint

```
POST {base_url}/run/companies/gemini/icp-criterion/generate
```

**Request:**
```json
{
  "company_name": "Salesforce",
  "domain": "salesforce.com",
  "customers": ["Toyota", "American Express", "T-Mobile"],
  "icp_titles": ["VP of Sales", "Sales Director", "CRO"]
}
```

**Response:**
```json
{
  "success": true,
  "domain": "salesforce.com",
  "company_name": "Salesforce",
  "criterion": "Enterprise companies with 500+ employees in financial services, retail, or telecommunications with dedicated sales teams...",
  "input_tokens": 600,
  "output_tokens": 300,
  "cost_usd": 0.007,
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/icp_criterion.py` (new file)

```python
async def generate_icp_criterion(
    *,
    base_url: str | None,
    company_name: str | None,
    domain: str | None,
    customers: list[str] | None = None,
    icp_titles: list[str] | None = None,
) -> ProviderAdapterResult:
```

- Skip if `company_name` and `domain` are both missing → `skipped`
- POST to `{base_url}/run/companies/gemini/icp-criterion/generate` with all 4 fields
- Timeout: 60 seconds
- Mapped output: `icp_criterion` (mapped from response `criterion`), `source_provider: "revenueinfra"`

**Important:** Map `criterion` from response to `icp_criterion` in output. This matches the `company_entities` column name and avoids ambiguity with other fields named `criterion` in cumulative context.

Update `__init__.py`.

### Contract

```python
class IcpCriterionOutput(BaseModel):
    icp_criterion: str | None = None
    source_provider: str = "revenueinfra"
```

### Service function

```python
async def execute_company_derive_icp_criterion(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `company_name`, `domain`
- Extract `customers` from cumulative context. This is a list. Check aliases: `customers` (may be a list of dicts with `name` field, or a list of strings). If list of dicts, extract the `name` field from each. If list of strings, use as-is.
- Extract `icp_titles` from cumulative context. Check aliases: `champion_titles`, `titles` (may be list of dicts with `title` field, or list of strings). Flatten to list of strings.
- Required: `company_name` or `domain`. Missing both → failed. `customers` and `icp_titles` are optional (the Gemini endpoint can work without them, just less accurate).
- Call provider. Validate. Return flat output.

---

## Operation 5: `company.derive.salesnav_url`

### Endpoint

```
POST {base_url}/run/tools/claude/salesnav-url/build
```

**Request:**
```json
{
  "orgId": "12345",
  "companyName": "Salesforce",
  "titles": ["VP of Sales", "Sales Director", "CRO"],
  "excludedSeniority": ["Entry", "Training"],
  "regions": ["United States"],
  "companyHQRegions": ["United States"]
}
```

**Response:**
```json
{
  "success": true,
  "url": "https://www.linkedin.com/sales/search/people?...",
  "orgId": "12345",
  "companyName": "Salesforce",
  "titles": ["VP of Sales", "Sales Director", "CRO"],
  "usage": {"input_tokens": 200, "output_tokens": 100},
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/salesnav_url.py` (new file)

```python
async def build_salesnav_url(
    *,
    base_url: str | None,
    org_id: str | None,
    company_name: str | None,
    titles: list[str] | None = None,
    excluded_seniority: list[str] | None = None,
    regions: list[str] | None = None,
    company_hq_regions: list[str] | None = None,
) -> ProviderAdapterResult:
```

- Skip if `org_id` is missing → `skipped`, `missing_required_inputs`
- Skip if `company_name` is missing → `skipped`, `missing_required_inputs`
- POST to `{base_url}/run/tools/claude/salesnav-url/build`
- **Important:** The HQ endpoint uses camelCase field names in the request body:
  ```json
  {
    "orgId": org_id,
    "companyName": company_name,
    "titles": titles,
    "excludedSeniority": excluded_seniority,
    "regions": regions,
    "companyHQRegions": company_hq_regions
  }
  ```
  Only include non-None fields in the payload.
- Timeout: 60 seconds
- Mapped output: `salesnav_url` (mapped from response `url`), `source_provider: "revenueinfra"`

**Important:** Map `url` from response to `salesnav_url` in output. This matches the `company_entities` column name.

Update `__init__.py`.

### Contract

```python
class SalesNavUrlOutput(BaseModel):
    salesnav_url: str | None = None
    source_provider: str = "revenueinfra"
```

### Service function

```python
async def execute_company_derive_salesnav_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `org_id` from cumulative context. Check aliases: `company_linkedin_id`, `org_id`, `orgId`, `linkedin_id`. This is the numeric LinkedIn org ID (string).
- Extract `company_name`
- Extract `titles` from cumulative context. Check aliases: `champion_titles`, `titles`. Flatten to list of strings same as operation 4.
- Optional: `excluded_seniority`, `regions`, `company_hq_regions` from input_data or cumulative_context. These may not be present — pass None if absent.
- Required: `org_id` and `company_name`. Missing either → failed.
- Call provider. Validate. Return flat output.

---

## Operation 6: `company.derive.evaluate_icp_fit`

### Endpoint

```
POST {base_url}/run/companies/gemini/icp-fit/evaluate
```

**Request:**
```json
{
  "criterion": "Enterprise companies with 500+ employees...",
  "company_name": "JPMorgan Chase",
  "domain": "jpmorganchase.com",
  "description": "Global financial services firm..."
}
```

**Response:**
```json
{
  "success": true,
  "domain": "jpmorganchase.com",
  "company_name": "JPMorgan Chase",
  "criterion": "Enterprise companies with 500+ employees...",
  "verdict": "strong_fit",
  "reasoning": "JPMorgan Chase matches the ICP criterion because...",
  "raw_response": "...",
  "input_tokens": 400,
  "output_tokens": 200,
  "cost_usd": 0.005,
  "error": null
}
```

### Provider adapter

**File:** `app/providers/revenueinfra/evaluate_icp_fit.py` (new file)

```python
async def evaluate_icp_fit(
    *,
    base_url: str | None,
    criterion: str | None,
    company_name: str | None,
    domain: str | None,
    description: str | None = None,
) -> ProviderAdapterResult:
```

- Skip if `criterion` is missing → `skipped`, `missing_required_inputs`
- Skip if `company_name` and `domain` are both missing → `skipped`
- POST to `{base_url}/run/companies/gemini/icp-fit/evaluate`
- Timeout: 60 seconds
- Mapped output: `icp_fit_verdict` (mapped from `verdict`), `icp_fit_reasoning` (mapped from `reasoning`), `source_provider: "revenueinfra"`

**Important:** Map `verdict` → `icp_fit_verdict` and `reasoning` → `icp_fit_reasoning` in output. These match the `company_entities` column names.

Update `__init__.py`.

### Contract

```python
class EvaluateIcpFitOutput(BaseModel):
    icp_fit_verdict: str | None = None
    icp_fit_reasoning: str | None = None
    source_provider: str = "revenueinfra"
```

### Service function

```python
async def execute_company_derive_evaluate_icp_fit(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

- Extract `criterion` from cumulative context. Aliases: `criterion`, `icp_criterion`.
- Extract `company_name`, `domain`, `description` (aliases: `description`, `description_raw`).
- Required: `criterion`. Missing → failed.
- Call provider. Validate. Return flat output.

---

## Deliverable Structure

### Deliverable 1: All 6 Provider Adapters

Create these 6 new files in `app/providers/revenueinfra/`:
- `infer_linkedin_url.py`
- `icp_job_titles_gemini.py`
- `discover_customers_gemini.py`
- `icp_criterion.py`
- `salesnav_url.py`
- `evaluate_icp_fit.py`

Update `app/providers/revenueinfra/__init__.py` to re-export all 6 functions.

All adapters follow the same pattern:
1. Use `_configured_base_url()` and `_as_str()` from `_common.py`
2. No auth header (these are `/run/` endpoints)
3. `httpx.AsyncClient` with adapter-specific timeout
4. `parse_json_or_raw(response.text, response.json)` for response parsing
5. Return `ProviderAdapterResult` with `attempt` + `mapped`

Commit standalone with message: `add 6 HQ workflow provider adapters`

### Deliverable 2: All 6 Contracts

**File:** `app/contracts/hq_workflow.py` (new file)

All 6 output models as specified above.

Commit standalone with message: `add HQ workflow output contracts`

### Deliverable 3: All 6 Service Functions

**File:** `app/services/hq_workflow_operations.py` (new file)

All 6 service functions. Each follows the standard pattern:
1. Generate `run_id`
2. Extract inputs from `input_data` / `cumulative_context`
3. Call provider with `settings.revenueinfra_api_url` as base_url (no api_key needed)
4. Validate through contract
5. Return `{run_id, operation_id, status, output, provider_attempts}`

**Important for input extraction from cumulative_context:**

The cumulative context is a flat dict that accumulates outputs from prior steps. When extracting inputs, always check both direct input_data keys and cumulative_context:

```python
ctx = input_data.get("cumulative_context") or {}
company_name = (
    _as_str(input_data.get("company_name"))
    or _as_str(ctx.get("company_name"))
    or _as_str(ctx.get("canonical_name"))
)
```

Use the same `_as_str` helper pattern from `app/services/resolve_operations.py` (or define a local one). Create a shared input extraction helper if it reduces duplication across the 6 functions.

Commit standalone with message: `add 6 HQ workflow operation services`

### Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add all 6 operation IDs to `SUPPORTED_OPERATION_IDS`.
2. Import all 6 service functions from `app.services.hq_workflow_operations`.
3. Add 6 dispatch branches with `persist_operation_execution` + `DataEnvelope`.

Commit standalone with message: `wire 6 HQ workflow operations into execute router`

### Deliverable 5: Tests

**File:** `tests/test_hq_workflow_operations.py` (new file)

For each of the 6 operations, at minimum:
1. `test_{op}_missing_required_inputs` — verify skip/fail when required inputs missing
2. `test_{op}_success` — mock HQ endpoint returning success, verify output fields and status
3. `test_{op}_not_found` — mock HQ endpoint returning `success: false`, verify not_found
4. `test_{op}_reads_from_cumulative_context` — verify input extraction from cumulative context

That's 24 test cases minimum. Mock all HTTP calls.

For operations 4 and 5 specifically, add a test verifying the input extraction logic for list fields (`customers`, `icp_titles`, `titles`) — test both list-of-strings and list-of-dicts input shapes.

Commit standalone with message: `add tests for 6 HQ workflow operations`

### Deliverable 6: Update Documentation

**File:** `docs/SYSTEM_OVERVIEW.md`

Add all 6 operations to the appropriate sections:
- Operations 1-3 under Company Research
- Operations 4-6 under Company Derive

Update operation count.

**File:** `CLAUDE.md`

Update operation count if referenced.

Commit standalone with message: `update documentation for 6 HQ workflow operations`

---

## What is NOT in scope

- No blueprint creation (separate directive)
- No database migrations
- No changes to `run-pipeline.ts`
- No changes to existing operations or providers
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) All 6 provider adapter function signatures and the HQ endpoint each calls
(b) All 6 contract class names and their fields
(c) All 6 service function signatures and their required vs optional inputs
(d) Confirmation that output field names match `company_entities` column names where applicable (`company_linkedin_url`, `icp_criterion`, `salesnav_url`, `icp_fit_verdict`, `icp_fit_reasoning`)
(e) Router wiring — all 6 operation IDs added
(f) Test count and names
(g) Anything to flag
