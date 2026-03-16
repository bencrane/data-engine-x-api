**Directive: `company.enrich.bulk_profile` Operation**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a single-company enrichment operation `company.enrich.profile` that runs a multi-provider waterfall (prospeo → blitzapi → companyenrich → leadmagic) and merges results. We also just shipped `company.enrich.bulk_prospeo`, which calls Prospeo's bulk endpoint for up to 50 companies in one request. This directive builds a batch enrichment operation that runs N companies through the full multi-provider waterfall, using the Prospeo bulk adapter for the Prospeo leg instead of N individual calls.

**How the existing single-company waterfall works** (read `app/services/company_operations.py` lines 300-363):

1. Extract identifiers from input (domain, website, linkedin_url, name, company_id).
2. For each provider in order (configurable, default: prospeo → blitzapi → companyenrich → leadmagic):
   - Call the provider with current identifiers.
   - If the provider returns data, map to canonical shape and merge into profile (base → overlay, first non-null wins).
   - Update `current_input` with any newly discovered identifiers (e.g., Prospeo returns a LinkedIn URL that blitzapi can use).
3. Return merged profile with `source_providers` list.

The identifier chaining matters: Prospeo might return a LinkedIn URL that the caller didn't have, and blitzapi needs that LinkedIn URL. So the waterfall is inherently sequential per company.

**What the bulk operation does:**

1. Accept up to 50 companies.
2. **Prospeo leg (batched):** Call `bulk_enrich_companies()` once for all companies. Map each matched result back to its company by identifier.
3. **Remaining providers (per-company):** For each company, take whatever Prospeo returned (or nothing if unmatched), update identifiers, then continue the waterfall with the remaining providers (blitzapi, companyenrich, leadmagic) one company at a time. Reuse the existing per-provider helpers (`_blitzapi_company_enrich`, `_companyenrich_company_enrich`, `_leadmagic_company_enrich`).
4. Return a list of enriched profiles, each with its own `source_providers` and status.

**Existing code to read:**

- `app/services/company_operations.py` — the entire file. Key sections:
  - `_canonical_company_from_prospeo()` (lines 103-123) — already used by bulk_prospeo
  - `_canonical_company_from_blitz()`, `_canonical_company_from_companyenrich()`, `_canonical_company_from_leadmagic()` — the other mappers
  - `_merge_company_profile()` (lines 203-210) — base/overlay merge
  - `_provider_order()` (lines 213-222) — reads configurable provider order
  - `_blitzapi_company_enrich()`, `_companyenrich_company_enrich()`, `_leadmagic_company_enrich()` (lines 249-297) — per-company provider helpers to reuse
  - `execute_company_enrich_profile()` (lines 300-390) — the single-company waterfall (reference pattern)
  - `execute_company_enrich_bulk_prospeo()` (lines 877-968) — the Prospeo-only bulk operation just shipped
- `app/providers/prospeo.py` — `bulk_enrich_companies()` adapter
- `app/contracts/company_enrich.py` — `CompanyProfileOutput`, `CompanyEnrichProfileOutput`, `BulkCompanyEnrichItem`, `BulkCompanyEnrichOutput`
- `app/routers/execute_v1.py` — `SUPPORTED_OPERATION_IDS`, dispatch pattern, `persist_operation_execution`
- `app/services/_input_extraction.py` — `extract_domain`, `extract_company_website`, `extract_company_linkedin_url`, `extract_company_name`
- `app/services/operation_history.py` — `persist_operation_execution`

---

### Deliverable 1: Output Contract

Add to `app/contracts/company_enrich.py`:

```python
class BulkProfileEnrichItem(BaseModel):
    identifier: str
    status: str  # "found", "not_found", "failed"
    company_profile: CompanyProfileOutput | None = None
    source_providers: list[str] = []

class BulkProfileEnrichOutput(BaseModel):
    results: list[BulkProfileEnrichItem]
    total_submitted: int
    total_found: int
    total_not_found: int
    total_failed: int
```

Commit standalone.

### Deliverable 2: Service Function

Add `execute_company_enrich_bulk_profile()` to `app/services/company_operations.py`.

**Signature:** `async def execute_company_enrich_bulk_profile(*, input_data: dict[str, Any]) -> dict[str, Any]`

**Input shape:**

```python
{
    "companies": [
        {
            "company_domain": "intercom.com",          # at least one identifier required
            "company_website": "https://intercom.com",  # optional
            "company_linkedin_url": "...",               # optional
            "company_name": "Intercom",                  # optional
            "source_company_id": "...",                  # optional
        },
        ...
    ]
}
```

**Behavior:**

1. Extract `companies` from `input_data`. If absent, empty, or not a list, return `failed` with `missing_inputs: ["companies"]`.
2. Cap at 50 companies. If `len(companies) > 50`, return `failed` with error `max_50_companies_exceeded`. Do not silently truncate.
3. **Prospeo bulk leg:**
   - Build records for `bulk_enrich_companies()` using stringified indices as identifiers (same pattern as `execute_company_enrich_bulk_prospeo`).
   - Call the adapter once.
   - Build a lookup dict: `{identifier: raw_company_dict}` from the matched results.
4. **Per-company waterfall continuation:**
   - For each company (by index), determine the remaining providers after "prospeo" in `_provider_order()`.
   - Start with the original input identifiers for that company.
   - If Prospeo matched this company (found in the lookup dict), map the raw company through `_canonical_company_from_prospeo()`, merge into profile, add "prospeo" to sources, and update `current_input` with newly discovered identifiers (same logic as lines 356-363 of `execute_company_enrich_profile`).
   - Then iterate through the remaining providers (`_blitzapi_company_enrich`, `_companyenrich_company_enrich`, `_leadmagic_company_enrich`), calling each with the updated `current_input`. Merge results and update identifiers exactly as the single-company waterfall does.
   - Each company gets its own `attempts` list (do not cross-contaminate).
5. **Build output:** For each company, create a `BulkProfileEnrichItem` with status (`"found"` if profile has data, `"not_found"` if all providers returned nothing, `"failed"` only on hard error), canonical profile, and `source_providers`.
6. Validate through `BulkProfileEnrichOutput`.
7. Return standard operation result:

```python
{
    "run_id": ...,
    "operation_id": "company.enrich.bulk_profile",
    "status": "found" if any found else "not_found",
    "output": {
        "results": [...],
        "total_submitted": N,
        "total_found": M,
        "total_not_found": K,
        "total_failed": F,
    },
    "provider_attempts": [prospeo_bulk_attempt],  # only the bulk attempt goes here; per-company attempts go in each result item
}
```

**Important:** The per-company waterfall continuation must run sequentially within each company (identifier chaining), but different companies are independent of each other. If you want to run multiple companies concurrently with `asyncio.gather` or `asyncio.Semaphore`, that is acceptable as a performance optimization — but not required. Do not over-engineer; sequential is fine for v1.

Commit standalone.

### Deliverable 3: Wire Into Execute Router

In `app/routers/execute_v1.py`:

1. Add `"company.enrich.bulk_profile"` to `SUPPORTED_OPERATION_IDS`.
2. Add the import for `execute_company_enrich_bulk_profile`.
3. Add the dispatch branch — call the service, `persist_operation_execution`, return `DataEnvelope(data=result)`.

Commit standalone.

### Deliverable 4: Tests

Create `tests/test_bulk_company_enrich_profile.py`.

Test cases (mock all HTTP calls and provider adapters):

1. **Full waterfall — Prospeo matched, blitzapi fills gaps:** Mock Prospeo bulk returning a match for company 0 (with domain but no LinkedIn URL). Mock blitzapi returning a LinkedIn URL for that company. Verify the merged profile has data from both providers, `source_providers` is `["prospeo", "blitzapi"]`.
2. **Prospeo unmatched, fallback providers find it:** Company 0 not in Prospeo matched list. Mock companyenrich returning data. Verify `source_providers` is `["companyenrich"]`, profile populated.
3. **All providers miss:** No provider returns data for a company. Verify `status: "not_found"`, empty profile.
4. **Mixed batch:** 3 companies — one found by Prospeo+blitzapi, one found by companyenrich only, one not found. Verify all three results correct, `total_found: 2`, `total_not_found: 1`.
5. **Identifier chaining:** Prospeo returns a LinkedIn URL that wasn't in the original input. Verify blitzapi receives that LinkedIn URL in its `input_data`.
6. **Missing input:** No `companies` key → `missing_inputs`.
7. **Over 50 companies:** 51 items → `failed` with `max_50_companies_exceeded`.
8. **Empty companies list:** → `missing_inputs`.

Commit standalone.

---

**What is NOT in scope:**

- No changes to the existing single-company `execute_company_enrich_profile()`.
- No changes to `execute_company_enrich_bulk_prospeo()` or the Prospeo bulk adapter.
- No changes to the per-provider helper functions (`_blitzapi_company_enrich`, etc.) — reuse them as-is.
- No Trigger.dev workflow changes.
- No deploy commands.
- No new environment variables.
- No bulk person enrichment.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the contract models, (b) the service function signature and how the Prospeo bulk result feeds into per-company waterfalls, (c) whether you implemented concurrent per-company processing or sequential, (d) the operation_id added to the router, (e) test count and what each covers, (f) anything to flag — especially if you hit issues reusing the existing per-provider helpers.
