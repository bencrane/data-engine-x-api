# Directive: CRM Resolution Operations (6 Resolve Operations)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have 6 single-record resolution endpoints at `api.revenueinfra.com` that resolve missing fields by looking up against the HQ warehouse database (1M+ companies). This directive creates 6 data-engine-x operations that call those endpoints, enabling them to be used as steps in blueprints. All 6 follow the same pattern: call HQ endpoint with one input field, get back a resolved value, merge into cumulative context.

---

## HQ Endpoint Reference

All endpoints are `POST` to `https://api.revenueinfra.com/api/workflows/{path}`. Auth: `x-api-key` header with value from `REVENUEINFRA_INGEST_API_KEY` env var. All return `{"resolved": true/false, ...}`.

| # | Path | Input | Output (when resolved) |
|---|---|---|---|
| 1 | `/resolve-domain-from-email/single` | `{"work_email": "jane@stripe.com"}` | `{"resolved": true, "domain": "stripe.com", "source": "..."}` |
| 2 | `/resolve-domain-from-linkedin/single` | `{"company_linkedin_url": "linkedin.com/company/stripe"}` | `{"resolved": true, "domain": "stripe.com", "source": "..."}` |
| 3 | `/resolve-company-name/single` | `{"company_name": "Stripe Inc"}` | `{"resolved": true, "domain": "stripe.com", "cleaned_company_name": "Stripe", "source": "..."}` |
| 4 | `/resolve-linkedin-from-domain/single` | `{"domain": "stripe.com"}` | `{"resolved": true, "company_linkedin_url": "...", "source": "..."}` |
| 5 | `/resolve-person-linkedin-from-email/single` | `{"work_email": "jane@stripe.com"}` | `{"resolved": true, "person_linkedin_url": "...", "source": "..."}` |
| 6 | `/resolve-company-location-from-domain/single` | `{"domain": "stripe.com"}` | `{"resolved": true, "company_city": "...", "company_state": "...", "company_country": "...", "source": "..."}` |

When not resolved: `{"resolved": false, "reason": "..."}`.

---

## Existing code to read before starting:

- `app/providers/revenueinfra/validate_job.py` — reference pattern for calling an HQ endpoint with `x-api-key` auth. **Follow this exact pattern for all 6 adapters.**
- `app/providers/revenueinfra/_common.py` — `_configured_base_url()`, `_PROVIDER`, helpers
- `app/providers/revenueinfra/__init__.py` — re-exports
- `app/services/research_operations.py` — `execute_job_validate_is_active` as reference for a simple single-provider operation
- `app/contracts/job_validation.py` — reference for a simple contract
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS` + dispatch
- `app/config.py` — `revenueinfra_ingest_api_key` already exists

---

## Deliverable 1: Provider Adapters (all 6)

**File:** `app/providers/revenueinfra/resolve.py` (new file)

Create 6 adapter functions in one file. They all follow the same pattern — only the endpoint path, input field name, and output mapping differ.

### Shared pattern:

```python
async def resolve_XXXX(
    *,
    base_url: str,
    api_key: str | None,
    INPUT_FIELD: str,
) -> ProviderAdapterResult:
```

1. Skip if `api_key` missing → `skipped`, `missing_provider_api_key`
2. Skip if input field missing/empty → `skipped`, `missing_required_inputs`
3. Call `POST {base_url}/api/workflows/{path}` with `x-api-key` header and JSON body
4. Timeout: 15 seconds (these are DB lookups, should be fast)
5. If HTTP error → `failed`
6. Parse response: if `resolved: true` → `status: "found"`, map output fields. If `resolved: false` → `status: "not_found"`.

### The 6 functions:

**`resolve_domain_from_email`**
- Path: `/api/workflows/resolve-domain-from-email/single`
- Input: `work_email: str`
- Mapped output: `{"domain": ..., "resolve_source": ...}`

**`resolve_domain_from_linkedin`**
- Path: `/api/workflows/resolve-domain-from-linkedin/single`
- Input: `company_linkedin_url: str`
- Mapped output: `{"domain": ..., "resolve_source": ...}`

**`resolve_domain_from_company_name`**
- Path: `/api/workflows/resolve-company-name/single`
- Input: `company_name: str`
- Mapped output: `{"domain": ..., "cleaned_company_name": ..., "resolve_source": ...}`

**`resolve_linkedin_from_domain`**
- Path: `/api/workflows/resolve-linkedin-from-domain/single`
- Input: `domain: str`
- Mapped output: `{"company_linkedin_url": ..., "resolve_source": ...}`

**`resolve_person_linkedin_from_email`**
- Path: `/api/workflows/resolve-person-linkedin-from-email/single`
- Input: `work_email: str`
- Mapped output: `{"person_linkedin_url": ..., "resolve_source": ...}`

**`resolve_company_location_from_domain`**
- Path: `/api/workflows/resolve-company-location-from-domain/single`
- Input: `domain: str`
- Mapped output: `{"company_city": ..., "company_state": ..., "company_country": ..., "resolve_source": ...}`

All 6 include `resolve_source` from the HQ response's `source` field — this tracks where the resolution came from (e.g., `"core.companies"`, `"email_extract"`, `"extracted.cleaned_company_names"`).

**Update `__init__.py`** to re-export all 6 functions.

Commit standalone with message: `add 6 HQ resolution provider adapters for CRM cleanup operations`

---

## Deliverable 2: Contracts

**File:** `app/contracts/resolve.py` (new file)

```python
from pydantic import BaseModel


class ResolveDomainOutput(BaseModel):
    domain: str | None = None
    cleaned_company_name: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolveLinkedInOutput(BaseModel):
    company_linkedin_url: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolvePersonLinkedInOutput(BaseModel):
    person_linkedin_url: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolveLocationOutput(BaseModel):
    company_city: str | None = None
    company_state: str | None = None
    company_country: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"
```

Note: `ResolveDomainOutput` is shared by all 3 domain-resolving operations (from email, from LinkedIn, from company name). The `cleaned_company_name` field is only populated by `resolve-company-name`.

Commit standalone with message: `add resolution contracts for CRM cleanup operations`

---

## Deliverable 3: Service Operations (all 6)

**File:** `app/services/resolve_operations.py` (new file)

Create 6 operation functions. All follow the same minimal pattern.

### Operation IDs:

| Operation ID | Calls | Primary input from context |
|---|---|---|
| `company.resolve.domain_from_email` | `resolve_domain_from_email` | `work_email` |
| `company.resolve.domain_from_linkedin` | `resolve_domain_from_linkedin` | `company_linkedin_url` or `linkedin_url` |
| `company.resolve.domain_from_name` | `resolve_domain_from_company_name` | `company_name` |
| `company.resolve.linkedin_from_domain` | `resolve_linkedin_from_domain` | `domain` or `company_domain` |
| `person.resolve.linkedin_from_email` | `resolve_person_linkedin_from_email` | `work_email` or `email` |
| `company.resolve.location_from_domain` | `resolve_company_location_from_domain` | `domain` or `company_domain` |

### Input extraction pattern (same for all):

Read the input field from:
1. `input_data.get(FIELD)` (direct input)
2. `input_data.get("cumulative_context", {}).get(FIELD)` (from prior step output)

For domain fields, also check aliases: `domain`, `company_domain`, `canonical_domain`.
For email fields, also check: `work_email`, `email`.
For LinkedIn fields, also check: `company_linkedin_url`, `linkedin_url`.

If the required input is missing → return `status: "failed"`, `missing_inputs: [FIELD]`.

### Execution pattern (same for all):

```python
async def execute_company_resolve_domain_from_email(*, input_data: dict[str, Any]) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    operation_id = "company.resolve.domain_from_email"
    attempts = []

    work_email = _extract_email(input_data)
    if not work_email:
        return {"run_id": run_id, "operation_id": operation_id, "status": "failed", "missing_inputs": ["work_email"], "provider_attempts": attempts}

    settings = get_settings()
    result = await revenueinfra.resolve_domain_from_email(
        base_url=settings.revenueinfra_api_url,
        api_key=settings.revenueinfra_ingest_api_key,
        work_email=work_email,
    )
    attempt = result.get("attempt", {})
    attempts.append(attempt if isinstance(attempt, dict) else {})
    mapped = result.get("mapped")

    if not isinstance(mapped, dict):
        return {"run_id": run_id, "operation_id": operation_id, "status": attempt.get("status", "failed"), "provider_attempts": attempts}

    output = ResolveDomainOutput.model_validate({**mapped, "source_provider": "revenueinfra"}).model_dump()
    return {"run_id": run_id, "operation_id": operation_id, "status": "found", "output": output, "provider_attempts": attempts}
```

Repeat for all 6 with appropriate input extraction, provider call, and contract validation.

**Helper functions to share across all 6:**

```python
def _extract_email(input_data: dict) -> str | None:
    # check input_data, then cumulative_context, for work_email or email

def _extract_domain(input_data: dict) -> str | None:
    # check input_data, then cumulative_context, for domain, company_domain, canonical_domain

def _extract_company_linkedin_url(input_data: dict) -> str | None:
    # check input_data, then cumulative_context, for company_linkedin_url, linkedin_url

def _extract_company_name(input_data: dict) -> str | None:
    # check input_data, then cumulative_context, for company_name
```

Commit standalone with message: `add 6 CRM resolve operation services`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add all 6 operation IDs to `SUPPORTED_OPERATION_IDS`:
   - `"company.resolve.domain_from_email"`
   - `"company.resolve.domain_from_linkedin"`
   - `"company.resolve.domain_from_name"`
   - `"company.resolve.linkedin_from_domain"`
   - `"person.resolve.linkedin_from_email"`
   - `"company.resolve.location_from_domain"`

2. Import all 6 execute functions from `app.services.resolve_operations`.

3. Add 6 dispatch branches. Group them together in the router. Follow existing pattern:

```python
if payload.operation_id == "company.resolve.domain_from_email":
    result = await execute_company_resolve_domain_from_email(input_data=payload.input)
    persist_operation_execution(auth=auth, entity_type=payload.entity_type, operation_id=payload.operation_id, input_payload=payload.input, result=result)
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire 6 CRM resolve operations into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_resolve_operations.py` (new file)

### Required test cases (18 total — 3 per operation):

For each of the 6 operations, test:

1. **Missing input** → `status: "failed"`, `missing_inputs` present
2. **Success (resolved)** → mock HQ returning `resolved: true`, verify output has expected fields
3. **Not found** → mock HQ returning `resolved: false`, verify `status: "not_found"`

**Test naming pattern:**
- `test_resolve_domain_from_email_missing_input`
- `test_resolve_domain_from_email_success`
- `test_resolve_domain_from_email_not_found`
- `test_resolve_domain_from_linkedin_missing_input`
- `test_resolve_domain_from_linkedin_success`
- `test_resolve_domain_from_linkedin_not_found`
- ... (same for all 6)

Mock all HTTP calls. Use realistic data (stripe.com, jane@stripe.com, etc.).

**Also add 2 context-chaining tests:**
- `test_resolve_domain_from_email_reads_cumulative_context` — verify `work_email` is extracted from `cumulative_context` when not in direct input
- `test_resolve_linkedin_from_domain_reads_cumulative_context` — verify `domain` is extracted from `cumulative_context.company_domain`

**Total: 20 tests.**

Commit standalone with message: `add tests for 6 CRM resolve operations`

---

## Deliverable 6: Update System Overview

**File:** `docs/SYSTEM_OVERVIEW.md`

- Update operation count from 51 to 57.
- Add a new section after Person operations:

```
### Resolution / CRM Cleanup (6)
| Operation ID | Provider(s) |
|---|---|
| `company.resolve.domain_from_email` | RevenueInfra HQ (reference.email_to_person + email domain extraction) |
| `company.resolve.domain_from_linkedin` | RevenueInfra HQ (core.companies) |
| `company.resolve.domain_from_name` | RevenueInfra HQ (extracted.cleaned_company_names) |
| `company.resolve.linkedin_from_domain` | RevenueInfra HQ (core.companies) |
| `person.resolve.linkedin_from_email` | RevenueInfra HQ (reference.email_to_person) |
| `company.resolve.location_from_domain` | RevenueInfra HQ (core.company_locations) |
```

Commit standalone with message: `update system overview with 6 CRM resolve operations (57 total)`

---

## What is NOT in scope

- No HQ endpoint changes (those are already built)
- No blueprint creation (separate task)
- No fallback provider logic (if HQ lookup returns `resolved: false`, the operation returns `not_found` — the blueprint's conditional execution handles what happens next)
- No changes to existing operations
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) All 6 operation IDs
(b) Provider adapter function signatures (all 6)
(c) HQ endpoint paths called by each
(d) Contract model names and field counts
(e) Input extraction aliases for each operation (what context fields it checks)
(f) Router wiring confirmation
(g) Test count and names
(h) Anything to flag
