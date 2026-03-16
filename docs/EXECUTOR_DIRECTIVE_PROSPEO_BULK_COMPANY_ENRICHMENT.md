**Directive: `company.enrich.bulk_prospeo` Operation**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We currently enrich companies one at a time via Prospeo's single-record `POST /enrich-company`. Prospeo also offers a bulk endpoint `POST /bulk-enrich-company` that enriches up to 50 companies in a single request at 1 credit per match. We need this wired up as a standalone operation so we can batch-enrich companies against Prospeo directly. This is net-new capability — no bulk enrichment exists today. A future directive will build a multi-provider batch orchestration layer on top of this.

**The Prospeo endpoint:**

```
POST https://api.prospeo.io/bulk-enrich-company
Headers:
  X-KEY: <PROSPEO_API_KEY>
  Content-Type: application/json

Request:
{
    "data": [
        {
            "identifier": "1",
            "company_website": "intercom.com"
        },
        {
            "identifier": "2",
            "company_linkedin_url": "https://www.linkedin.com/company/deloitte"
        },
        {
            "identifier": "3",
            "company_name": "Milka"
        },
        ... up to 50 objects
    ]
}

Each object requires:
- "identifier" (required) — caller-generated string to reconcile results
- At least one of: "company_website", "company_linkedin_url", "company_name", "company_id"

Response (200):
{
    "error": false,
    "total_cost": 2,
    "matched": [
        {
            "identifier": "1",
            "company": { ... full company object ... }
        },
        {
            "identifier": "2",
            "company": { ... full company object ... }
        }
    ],
    "not_matched": ["3"],
    "invalid_datapoints": ["4"]
}

Error codes:
- 400 INSUFFICIENT_CREDITS
- 401 INVALID_API_KEY
- 429 RATE_LIMITED
- 400 INVALID_REQUEST / INTERNAL_ERROR
```

The `company` object in each matched result is the same shape as the single-record `POST /enrich-company` response — the `_canonical_company_from_prospeo()` mapper in `company_operations.py` already handles it.

**Existing code to read:**

- `app/providers/prospeo.py` — existing adapter (`enrich_company`, `search_companies`, `search_people`). Follow the same httpx + error handling + `ProviderAdapterResult` pattern.
- `app/providers/common.py` — `ProviderAdapterResult`, `now_ms`, `parse_json_or_raw`
- `app/config.py` — `prospeo_api_key` (line 37)
- `app/services/company_operations.py` — `_canonical_company_from_prospeo()` (lines 103-123) for the per-company canonical mapping, and `execute_company_enrich_profile()` (lines 298-390) as a reference for how single-record enrichment operations are structured
- `app/contracts/company_enrich.py` — `CompanyProfileOutput` for the per-company canonical shape
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS`, dispatch pattern (lines 133-216 for the ID set, lines 310+ for dispatch branches), `persist_operation_execution` call
- `app/services/operation_history.py` — `persist_operation_execution`

---

### Deliverable 1: Bulk Provider Adapter

Add `bulk_enrich_companies()` to `app/providers/prospeo.py`.

**Signature:** `async def bulk_enrich_companies(*, api_key: str | None, records: list[dict[str, Any]]) -> ProviderAdapterResult`

Where `records` is a list of dicts, each containing `identifier` plus at least one of `company_website`, `company_linkedin_url`, `company_name`, `company_id`.

Behavior:
- If `api_key` is `None`, return skipped with `missing_provider_api_key`.
- If `records` is empty, return skipped with `missing_required_inputs`.
- If `len(records) > 50`, return failed — do not silently truncate. The caller must chunk.
- Call `POST https://api.prospeo.io/bulk-enrich-company` with `{"data": records}`. Timeout: 60 seconds (bulk calls are slower).
- On error (`error: true` or HTTP >= 400), return failed attempt with error code.
- On success, return `ProviderAdapterResult` where:
  - `attempt` has `status: "found"` if any matched, `"not_found"` if zero matched, plus `raw_response`, `duration_ms`
  - `mapped` is `{"matched": [...], "not_matched": [...], "invalid_datapoints": [...], "total_cost": int}` — keep the Prospeo structure here. Each item in `matched` retains its `identifier` and raw `company` object.

Commit standalone.

### Deliverable 2: Output Contract

Add to `app/contracts/company_enrich.py`:

```
class BulkCompanyEnrichItem(BaseModel):
    identifier: str
    company_profile: CompanyProfileOutput | None

class BulkCompanyEnrichOutput(BaseModel):
    matched: list[BulkCompanyEnrichItem]
    not_matched: list[str]
    invalid_datapoints: list[str]
    total_submitted: int
    total_matched: int
    total_cost: int | None = None
    source_provider: str = "prospeo"
```

Commit standalone.

### Deliverable 3: Service Function

Create the service function in `app/services/company_operations.py`:

**Signature:** `async def execute_company_enrich_bulk_prospeo(*, input_data: dict[str, Any]) -> dict[str, Any]`

Behavior:
1. Extract `companies` from `input_data` — a list of dicts, each with at least one of: `company_website`/`company_domain`, `company_linkedin_url`, `company_name`, `company_id`. If absent or empty, return `failed` with `missing_inputs: ["companies"]`.
2. Build the `records` list for the adapter. For each company in the input list:
   - Generate an `identifier` (use the list index as a string, or a UUID — keep it simple).
   - Map `company_domain` → `company_website` if `company_website` is not provided (Prospeo uses `company_website` as the domain field).
   - Pass through `company_linkedin_url`, `company_name`, `company_id` as-is.
3. Call `bulk_enrich_companies()`.
4. For each matched result, run `_canonical_company_from_prospeo()` on the raw `company` object.
5. Validate through `BulkCompanyEnrichOutput`.
6. Return the standard operation result shape:

```python
{
    "run_id": ...,
    "operation_id": "company.enrich.bulk_prospeo",
    "status": "found" | "not_found" | "failed",
    "output": {
        "matched": [...],       # canonical profiles with identifiers
        "not_matched": [...],   # identifiers
        "invalid_datapoints": [...],  # identifiers
        "total_submitted": N,
        "total_matched": M,
        "total_cost": C,
        "source_provider": "prospeo",
    },
    "provider_attempts": [...],
}
```

Commit standalone.

### Deliverable 4: Wire Into Execute Router

In `app/routers/execute_v1.py`:

1. Add `"company.enrich.bulk_prospeo"` to `SUPPORTED_OPERATION_IDS`.
2. Add the import for `execute_company_enrich_bulk_prospeo` from `app.services.company_operations`.
3. Add a dispatch branch following the same pattern as other operations — call the service, `persist_operation_execution`, return `DataEnvelope(data=result)`.

Commit standalone.

### Deliverable 5: Tests

Create `tests/test_bulk_company_enrich_prospeo.py`.

Test cases (mock all HTTP calls):

1. **Adapter success** — mock Prospeo returning 2 matched, 1 not_matched. Verify `ProviderAdapterResult` shape, matched count, identifiers preserved.
2. **Adapter missing API key** — verify skipped.
3. **Adapter empty records** — verify skipped.
4. **Adapter over 50 records** — verify failed, not truncated.
5. **Adapter upstream error** — mock 401 INVALID_API_KEY, verify failed attempt.
6. **Service end-to-end** — mock the adapter, verify canonical mapping applied to each matched company, verify `BulkCompanyEnrichOutput` validates.
7. **Service missing input** — no `companies` key, verify `missing_inputs`.
8. **Service domain-to-website mapping** — pass `company_domain` without `company_website`, verify it maps to `company_website` in the adapter call.

Commit standalone.

---

**What is NOT in scope:**

- No changes to the existing single-record `enrich_company()` adapter or `execute_company_enrich_profile()` service.
- No multi-provider waterfall. This is Prospeo-only.
- No Trigger.dev workflow changes.
- No deploy commands.
- No new environment variables.
- No bulk person enrichment (separate future work).

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the adapter function signature and the max-records guard, (b) the contract models, (c) the service function signature and how identifiers are generated, (d) the operation_id added to the router, (e) test count and what each covers, (f) anything to flag.
