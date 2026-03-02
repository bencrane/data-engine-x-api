# Directive: `company.enrich.profile_blitzapi` — BlitzAPI Company Enrichment (Dedicated)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need a dedicated BlitzAPI-only company enrichment operation. The existing `company.enrich.profile` uses a 4-provider waterfall (Prospeo → BlitzAPI → CompanyEnrich → LeadMagic), which means we can't guarantee BlitzAPI runs or that `company_linkedin_id` is in the output. This new operation calls BlitzAPI directly — single provider, deterministic output. It's a step in the AlumniGTM pipeline where downstream steps depend on `company_linkedin_id` (the numeric LinkedIn org ID) being present.

---

## BlitzAPI Endpoint Reference

**Endpoint:** `POST https://api.blitz-api.ai/v2/enrichment/company`

**Auth:** `x-api-key` header. The key is available via `settings.blitzapi_api_key` (already in `app/config.py`).

**Request body:**
```json
{
  "company_linkedin_url": "https://www.linkedin.com/company/blitz-api"
}
```

**Response (success — `found: true`):**
```json
{
  "found": true,
  "company": {
    "linkedin_url": "https://www.linkedin.com/company/blitz-api",
    "linkedin_id": 108037802,
    "name": "Blitzapi",
    "about": "BlitzAPI provides enriched B2B data access through a suite of flexible and high-performance APIs...",
    "specialties": null,
    "industry": "Technology; Information and Internet",
    "type": "Privately Held",
    "size": "1-10",
    "employees_on_linkedin": 3,
    "followers": 6,
    "founded_year": null,
    "hq": {
      "city": "Paris",
      "state": null,
      "postcode": null,
      "country_code": "FR",
      "country_name": "France",
      "region": null,
      "continent": null,
      "street": null
    },
    "domain": "blitz-api.ai",
    "website": "https://blitz-api.ai"
  }
}
```

**Response (not found):**
```json
{
  "found": false
}
```

**Error responses:**
- 401: `{"success": false, "message": "Invalid API key..."}`
- 404: `{"success": false, "message": "Not Found"}`
- 429: `{"success": false, "message": "Rate limit exceeded..."}` — handled by existing retry logic
- 500: `{"success": false, "message": "..."}`

---

## Existing code to read before starting

- `app/providers/blitzapi.py` — existing BlitzAPI provider. Read `_blitzapi_request_with_retry` (reuse it), `resolve_linkedin_from_domain` (pattern reference for a single-endpoint adapter). Do NOT modify existing functions.
- `app/services/company_operations.py` — read `_canonical_company_from_blitz` (line ~119) for the field mapping from BlitzAPI raw → canonical. Read `execute_company_enrich_profile` for how the waterfall operation flattens output (line ~374). Your new operation follows the same flat output pattern but is single-provider.
- `app/contracts/company_enrich.py` — read `CompanyProfileOutput` (line ~8). You will NOT reuse this model. You will create a new, dedicated contract (see Deliverable 2).
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — `blitzapi_api_key` already exists

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/blitzapi.py` (existing file — add function, do NOT modify existing functions)

Add a new function:

```python
async def enrich_company_profile(
    *,
    api_key: str | None,
    company_linkedin_url: str | None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `api_key` is missing → `status: "skipped"`, `skip_reason: "missing_provider_api_key"`
2. Skip if `company_linkedin_url` is missing/empty → `status: "skipped"`, `skip_reason: "missing_required_inputs"`
3. Call `POST https://api.blitz-api.ai/v2/enrichment/company` with `x-api-key` header and JSON body `{"company_linkedin_url": company_linkedin_url}`.
4. Use `_blitzapi_request_with_retry` for the HTTP call (handles 429 retry).
5. Timeout: 30 seconds (use `httpx.AsyncClient(timeout=30.0)`).
6. If `response.status_code >= 400` → `status: "failed"` (or `"not_found"` for 404).
7. Parse response. If `found: true` and `company` object present, map to canonical fields:

```python
hq = company.get("hq") or {}
"mapped": {
    "company_name": company.get("name"),
    "company_domain": company.get("domain"),
    "company_website": company.get("website"),
    "company_linkedin_url": company.get("linkedin_url"),
    "company_linkedin_id": str(company.get("linkedin_id")) if company.get("linkedin_id") is not None else None,
    "company_type": company.get("type"),
    "industry_primary": company.get("industry"),
    "employee_count": company.get("employees_on_linkedin"),
    "employee_range": company.get("size"),
    "founded_year": company.get("founded_year"),
    "hq_locality": hq.get("city"),
    "hq_country_code": hq.get("country_code"),
    "description_raw": company.get("about"),
    "specialties": company.get("specialties"),
    "follower_count": company.get("followers"),
    "source_provider": "blitzapi",
}
```

8. If `found: false` or no `company` → `status: "not_found"`, `mapped: None`

**Important:** The `action` field in the attempt dict must be `"enrich_company_profile"` (distinct from the existing `"company_enrich"` action on the old `enrich_company` function).

Follow the exact error handling + attempt metadata pattern of `resolve_linkedin_from_domain` in the same file.

Commit standalone with message: `add BlitzAPI dedicated company enrichment provider adapter`

---

## Deliverable 2: Canonical Contract

**File:** `app/contracts/company_enrich.py` (existing file — add model, do NOT modify existing models)

Add:

```python
class BlitzAPICompanyEnrichOutput(BaseModel):
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
```

This is intentionally a dedicated contract — not `CompanyProfileOutput` — because this operation is single-provider and the output shape is guaranteed.

Commit standalone with message: `add BlitzAPI company enrichment output contract`

---

## Deliverable 3: Service Operation

**File:** `app/services/company_operations.py` (existing file — add function, do NOT modify existing functions)

Add:

```python
async def execute_company_enrich_profile_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:** Extract `company_linkedin_url` from `input_data`, falling back to `cumulative_context` if present. Check these keys in order: `company_linkedin_url`, `linkedin_url`.

If no `company_linkedin_url` found but `company_domain` or `domain` is available, use it to resolve via `blitzapi.resolve_linkedin_from_domain` first (same bridge pattern as `_blitzapi_company_enrich` at line ~240). Track the bridge attempt.

**Required inputs:** At least one of `company_linkedin_url` or `company_domain`/`domain`. If neither → return `status: "failed"` with `missing_inputs: ["company_linkedin_url|company_domain"]`.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.enrich_company_profile(
    api_key=settings.blitzapi_api_key,
    company_linkedin_url=company_linkedin_url,
)
```

**Output validation:** Validate `mapped` through `BlitzAPICompanyEnrichOutput.model_validate(mapped).model_dump()`.

**Output flattening:** The `output` field in the return dict must have all canonical fields at top level (flat). This is critical — downstream pipeline steps read from cumulative context, and fields like `company_linkedin_id`, `company_name`, `description_raw` must be directly accessible. Follow the same flat output pattern as `execute_company_enrich_profile` (line ~374-376).

**Operation ID:** `"company.enrich.profile_blitzapi"`

**Return shape:**
```python
{
    "run_id": run_id,
    "operation_id": "company.enrich.profile_blitzapi",
    "status": "found" | "not_found" | "failed",
    "output": { ... flat canonical fields ... },
    "provider_attempts": attempts,
}
```

Commit standalone with message: `add company.enrich.profile_blitzapi operation service`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.enrich.profile_blitzapi"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_enrich_profile_blitzapi` from `app.services.company_operations`.
3. Add dispatch branch:

```python
if payload.operation_id == "company.enrich.profile_blitzapi":
    result = await execute_company_enrich_profile_blitzapi(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Place near the existing `company.enrich.profile` dispatch.

Commit standalone with message: `wire company.enrich.profile_blitzapi into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_blitzapi_company_enrichment.py` (new file)

### Required test cases:

1. `test_enrich_company_missing_api_key` — provider adapter returns `skipped` with `missing_provider_api_key`
2. `test_enrich_company_missing_linkedin_url` — provider adapter returns `skipped` with `missing_required_inputs`
3. `test_enrich_company_success` — mock BlitzAPI returning the full success response from the endpoint reference above. Verify:
   - `status == "found"`
   - `output["company_linkedin_id"] == "108037802"` (string, not int)
   - `output["company_name"] == "Blitzapi"`
   - `output["description_raw"]` is populated
   - `output["company_domain"] == "blitz-api.ai"`
   - `output["hq_locality"] == "Paris"`
   - `output["hq_country_code"] == "FR"`
4. `test_enrich_company_not_found` — mock BlitzAPI returning `{"found": false}`. Verify `status == "not_found"`.
5. `test_enrich_company_http_error` — mock HTTP 500. Verify `status == "failed"`.
6. `test_enrich_company_domain_bridge` — service function receives `company_domain` but no `company_linkedin_url`. Verify it calls `resolve_linkedin_from_domain` first, then calls `enrich_company_profile` with the resolved URL. Mock both calls.
7. `test_enrich_company_reads_from_cumulative_context` — verify `company_linkedin_url` is extracted from `cumulative_context` when not in direct input.

Mock all HTTP calls. Use realistic data from the endpoint reference above.

Commit standalone with message: `add tests for company.enrich.profile_blitzapi operation`

---

## Deliverable 6: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Company Enrichment section:
```
| `company.enrich.profile_blitzapi` | BlitzAPI (dedicated single-provider company enrichment with linkedin_id) |
```

Update operation count.

### File: `CLAUDE.md`

Update operation count references if present.

Commit standalone with message: `update documentation for company.enrich.profile_blitzapi operation`

---

## What is NOT in scope

- No changes to the existing `company.enrich.profile` (waterfall) operation
- No changes to the existing `enrich_company` or `company_search` functions in `blitzapi.py`
- No database migrations (the `company_linkedin_id` column on `company_entities` is a separate directive)
- No deploy commands
- No changes to `run-pipeline.ts`

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and the exact BlitzAPI endpoint URL it calls
(b) Confirmation that `company_linkedin_id` is a top-level field in the flat output (critical for downstream pipeline steps)
(c) Contract field list
(d) Input extraction — what context fields it checks for `company_linkedin_url` and the domain-bridge fallback behavior
(e) Router wiring confirmation
(f) Test count and names
(g) Anything to flag
