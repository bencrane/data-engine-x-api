# Directive: `company.resolve.linkedin_from_domain_blitzapi` — BlitzAPI Domain to LinkedIn URL

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need to resolve company domains to LinkedIn Company Page URLs using BlitzAPI's domain-to-linkedin endpoint. This is a standalone operation that takes a domain and returns the LinkedIn URL. The result must persist to the company entity record (via entity state upsert) so the LinkedIn URL is queryable by domain going forward — not just stored in step_results.

---

## BlitzAPI Endpoint Reference

**Endpoint:** `POST https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin`

**Auth:** `x-api-key` header. The key is available via `settings.blitzapi_api_key` (already in `app/config.py`).

**Request body:**
```json
{
  "domain": "https://www.vanta.com"
}
```

`domain` field accepts URLs or bare domains.

**Response (success):**
```json
{
  "found": true,
  "company_linkedin_url": "https://www.linkedin.com/company/vanta-security"
}
```

**Response (not found):**
```json
{
  "found": false
}
```

**Response (error):**
- 402: `{"message": "Insufficient credits balance"}`
- 422: `{"success": false, "error": {"code": "INVALID_INPUT", "message": "Missing required fields"}}`
- 500: `{"success": false, "message": "..."}`

---

## Existing code to read before starting

- `app/providers/blitzapi.py` — existing BlitzAPI provider adapter. Add the new function here. Follow the existing patterns for auth, error handling, and `ProviderAdapterResult` shape.
- `app/services/resolve_operations.py` — existing CRM resolve operations. Add the new operation here. Follow the pattern of `execute_company_resolve_linkedin_from_domain`.
- `app/contracts/resolve.py` — existing resolve contracts. The `ResolveLinkedInOutput` contract already exists and fits this operation.
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — `blitzapi_api_key` already exists

---

## Deliverable 1: Provider Adapter

**File:** `app/providers/blitzapi.py` (existing file — add function, do NOT modify existing functions)

Add:

```python
async def resolve_linkedin_from_domain(
    *,
    api_key: str | None,
    domain: str | None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `api_key` is missing → `skipped`, `missing_provider_api_key`
2. Skip if `domain` is missing/empty → `skipped`, `missing_required_inputs`
3. Call `POST https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin` with `x-api-key` header and JSON body `{"domain": domain}`.
4. Timeout: 15 seconds.
5. If HTTP error → `failed`
6. Parse response. If `found: true` → map output:

```python
"mapped": {
    "company_linkedin_url": body.get("company_linkedin_url"),
    "resolve_source": "blitzapi",
}
```

7. If `found: false` → `not_found`

Follow the exact error handling pattern of existing functions in `blitzapi.py`.

Commit standalone with message: `add BlitzAPI domain-to-linkedin provider adapter`

---

## Deliverable 2: Service Operation

**File:** `app/services/resolve_operations.py` (existing file — add function, do NOT modify existing functions)

Add:

```python
async def execute_company_resolve_linkedin_from_domain_blitzapi(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:** Same pattern as `execute_company_resolve_linkedin_from_domain` — extract `domain` from `input_data` or `cumulative_context`, checking aliases: `domain`, `company_domain`, `canonical_domain`.

**Required inputs:** `domain`. Missing → return `status: "failed"` with `missing_inputs: ["domain"]`.

**Provider call:**
```python
settings = get_settings()
result = await blitzapi.resolve_linkedin_from_domain(
    api_key=settings.blitzapi_api_key,
    domain=domain,
)
```

**Validate output** with the existing `ResolveLinkedInOutput` contract from `app/contracts/resolve.py`. Follow the exact attempt tracking + status derivation pattern from the existing resolve operations.

**Operation ID:** `"company.resolve.linkedin_from_domain_blitzapi"`

**Important:** The output must include `company_linkedin_url` as a top-level field in the result output. This ensures the entity state mapper picks it up and writes it to `company_entities.linkedin_url` when the pipeline run succeeds. The data must land on the company entity record, not just in step_results.

Commit standalone with message: `add company.resolve.linkedin_from_domain_blitzapi operation service`

---

## Deliverable 3: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.resolve.linkedin_from_domain_blitzapi"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_resolve_linkedin_from_domain_blitzapi` from `app.services.resolve_operations`.
3. Add dispatch branch:

```python
if payload.operation_id == "company.resolve.linkedin_from_domain_blitzapi":
    result = await execute_company_resolve_linkedin_from_domain_blitzapi(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Place near the other resolve operations.

Commit standalone with message: `wire company.resolve.linkedin_from_domain_blitzapi into execute router`

---

## Deliverable 4: Tests

**File:** `tests/test_blitzapi_domain_to_linkedin.py` (new file)

### Required test cases:

1. `test_resolve_linkedin_missing_api_key` — skipped with `missing_provider_api_key`
2. `test_resolve_linkedin_missing_domain` — skipped with `missing_required_inputs`
3. `test_resolve_linkedin_success` — mock BlitzAPI returning `{"found": true, "company_linkedin_url": "https://www.linkedin.com/company/vanta-security"}`. Verify status `"found"`, output has `company_linkedin_url`.
4. `test_resolve_linkedin_not_found` — mock BlitzAPI returning `{"found": false}`. Verify status `"not_found"`.
5. `test_resolve_linkedin_http_error` — mock HTTP 500. Verify status `"failed"`.
6. `test_resolve_linkedin_reads_from_cumulative_context` — verify `domain` is extracted from `cumulative_context.company_domain` when not in direct input.

Mock all HTTP calls. Use realistic data (vanta.com → linkedin.com/company/vanta-security).

Commit standalone with message: `add tests for BlitzAPI domain-to-linkedin resolve operation`

---

## Deliverable 5: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Resolution / CRM Cleanup section:
```
| `company.resolve.linkedin_from_domain_blitzapi` | BlitzAPI (domain to LinkedIn URL lookup) |
```

Update operation count (63 total).

### File: `CLAUDE.md`

Update operation count references if present.

Commit standalone with message: `update documentation for company.resolve.linkedin_from_domain_blitzapi operation`

---

## What is NOT in scope

- No changes to the existing `company.resolve.linkedin_from_domain` (HQ-based) operation
- No changes to BlitzAPI's existing `enrich_company` or `company_search` functions
- No dedicated storage table (the LinkedIn URL persists to `company_entities.linkedin_url` via standard entity state upsert)
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Provider adapter function signature and BlitzAPI endpoint it calls
(b) Operation service input extraction (what context fields it checks for domain)
(c) Contract used for output validation
(d) Confirmation that `company_linkedin_url` is a top-level output field (for entity state persistence)
(e) Router wiring confirmation
(f) Test count and names
(g) Anything to flag
