# Directive: Add `companyHeadcount` and `function` Parameters to Sales Nav URL Builder

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The `company.derive.salesnav_url` operation builds LinkedIn Sales Navigator search URLs via the HQ endpoint `/run/tools/claude/salesnav-url/build`. It currently passes `orgId`, `companyName`, `titles`, `excludedSeniority`, `regions`, `companyHQRegions`. Two additional parameters are needed: `companyHeadcount` (to filter by company size — exclude self-employed and 1-10) and `function` (to filter by job function — e.g., Engineering, Finance, Legal). These are already supported by the HQ endpoint but not passed through by our provider adapter and service function.

---

## Existing code to read before starting

- `app/providers/revenueinfra/salesnav_url.py` — the provider adapter. Add the two new parameters to the function signature and the request payload.
- `app/services/hq_workflow_operations.py` — the service function `execute_company_derive_salesnav_url` (~line 356). Add input extraction for the two new parameters.

---

## Fix 1: Provider Adapter

**File:** `app/providers/revenueinfra/salesnav_url.py`

Add two new parameters to `build_salesnav_url`:

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
    company_headcount: list[str] | None = None,      # NEW
    function: list[str] | None = None,                 # NEW
) -> ProviderAdapterResult:
```

Add them to the request payload using camelCase keys (matching the HQ endpoint):

```python
if company_headcount is not None:
    payload["companyHeadcount"] = company_headcount
if function is not None:
    payload["function"] = function
```

Place these alongside the existing optional field additions in the payload construction.

---

## Fix 2: Service Function

**File:** `app/services/hq_workflow_operations.py`

In `execute_company_derive_salesnav_url`, add input extraction for the two new parameters:

```python
company_headcount = _coerce_list_of_strings(_extract_list(input_data, ("company_headcount", "companyHeadcount")))
function = _coerce_list_of_strings(_extract_list(input_data, ("function", "job_function")))
```

Pass them to the provider call:

```python
result = await revenueinfra.build_salesnav_url(
    base_url=settings.revenueinfra_api_url,
    org_id=org_id,
    company_name=company_name,
    titles=titles,
    excluded_seniority=excluded_seniority,
    regions=regions,
    company_hq_regions=company_hq_regions,
    company_headcount=company_headcount,
    function=function,
)
```

These values can come from cumulative_context or step_config. The step_config path is important — blueprints will pass headcount and function filters as step configuration.

---

## Scope

Two files only. Do not change any other files.

**One commit. Do not push.**

Commit message: `add companyHeadcount and function params to salesnav_url operation`

## When done

Report back with:
(a) Updated provider adapter signature
(b) Updated service function input extraction aliases
(c) Confirmation both params are passed as camelCase in the HQ request payload
(d) Anything to flag
