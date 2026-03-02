# Directive: `company.derive.extract_icp_titles` — Modal/Anthropic ICP Title Extraction

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have raw Parallel.ai ICP job title research output stored in the `icp_job_titles` table (one row per company, JSONB). The output schema varies per company (Parallel's auto schema). A Modal function exists that sends the raw output to Anthropic, which extracts a consistent array of `{ title, buyer_role, reasoning }` objects. This directive builds the data-engine-x operation that calls that Modal function and persists the extracted titles in two places: (1) an `extracted_titles` JSONB column on the existing `icp_job_titles` table, and (2) a new flat `extracted.icp_job_title_details` table with one row per title per company for joins.

---

## Modal Endpoint Reference

**Endpoint:** `POST https://bencrane--hq-master-data-ingest-extract-icp-titles.modal.run`

**Request body:**
```json
{
  "company_domain": "withcoverage.com",
  "raw_parallel_output": "<the raw_parallel_output JSONB from icp_job_titles, as a JSON string>",
  "raw_parallel_icp_id": "<UUID from icp_job_titles.id>"
}
```

All 3 fields should be passed.

**Response (success):**
```json
{
  "success": true,
  "normalized_id": "a1b2c3d4-...",
  "company_domain": "withcoverage.com",
  "company_name": "WithCoverage",
  "titles": [
    {
      "title": "Chief Financial Officer (CFO)",
      "buyer_role": "decision_maker",
      "reasoning": "Multiple testimonials are authored by CFOs..."
    }
  ],
  "title_count": 42,
  "usage": {
    "input_tokens": 5200,
    "output_tokens": 3800,
    "total_tokens": 9000,
    "cost_usd": 0.01936
  }
}
```

`buyer_role` values: `"champion"`, `"evaluator"`, `"decision_maker"`

**Response (failure):**
```json
{
  "success": false,
  "error": "..."
}
```

**No auth required.** Timeout: 60 seconds (Anthropic call is typically 10-20 seconds).

---

## Existing code to read before starting

- `app/providers/revenueinfra/validate_job.py` — reference pattern for calling an external HTTP endpoint from a provider adapter
- `app/providers/revenueinfra/_common.py` — shared helpers
- `app/services/research_operations.py` — reference pattern for operation service functions
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/services/icp_job_titles.py` — existing service for the `icp_job_titles` table (you will add an update function here)
- `app/routers/internal.py` — reference for internal endpoints
- `app/routers/entities_v1.py` — reference for query endpoints
- `supabase/migrations/015_icp_job_titles.sql` — existing icp_job_titles table schema

---

## Deliverable 1: Migration

**File:** `supabase/migrations/017_icp_title_extraction.sql` (new file)

### Add column to existing table:

```sql
ALTER TABLE icp_job_titles
ADD COLUMN IF NOT EXISTS extracted_titles JSONB;
```

### Create new flat table:

```sql
CREATE TABLE IF NOT EXISTS extracted_icp_job_title_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    title TEXT NOT NULL,
    title_normalized TEXT GENERATED ALWAYS AS (LOWER(TRIM(title))) STORED,
    buyer_role TEXT,
    reasoning TEXT,
    source_icp_job_titles_id UUID REFERENCES icp_job_titles(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_domain
    ON extracted_icp_job_title_details(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_title_normalized
    ON extracted_icp_job_title_details(org_id, title_normalized);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_org_buyer_role
    ON extracted_icp_job_title_details(org_id, buyer_role);
CREATE INDEX IF NOT EXISTS idx_icp_title_details_source
    ON extracted_icp_job_title_details(source_icp_job_titles_id);

CREATE UNIQUE INDEX IF NOT EXISTS idx_icp_title_details_dedup
    ON extracted_icp_job_title_details(org_id, company_domain, title_normalized);

DROP TRIGGER IF EXISTS update_icp_title_details_updated_at ON extracted_icp_job_title_details;
CREATE TRIGGER update_icp_title_details_updated_at
    BEFORE UPDATE ON extracted_icp_job_title_details
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE extracted_icp_job_title_details ENABLE ROW LEVEL SECURITY;
```

Note: `title_normalized` is a generated column for join compatibility with `person_work_history.title_normalized`.

Copy this SQL exactly.

Commit standalone with message: `add 017 migration for icp title extraction — extracted_titles column + flat details table`

---

## Deliverable 2: Provider Adapter

**File:** `app/providers/modal_extract_icp.py` (new file)

```python
async def extract_icp_titles(
    *,
    company_domain: str,
    raw_parallel_output: dict[str, Any] | str,
    raw_parallel_icp_id: str | None = None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `company_domain` is missing → `skipped`, `missing_required_inputs`
2. Skip if `raw_parallel_output` is missing/empty → `skipped`, `missing_required_inputs`
3. If `raw_parallel_output` is a dict, convert to JSON string for the request body.
4. Call `POST https://bencrane--hq-master-data-ingest-extract-icp-titles.modal.run` with JSON body containing all 3 fields.
5. No auth header needed.
6. Timeout: 60 seconds.
7. If HTTP error → `failed`
8. Parse response. If `success: false` → `failed` with error from response.
9. If `success: true`, map to:

```python
"mapped": {
    "company_domain": body.get("company_domain"),
    "company_name": body.get("company_name"),
    "titles": body.get("titles", []),
    "title_count": body.get("title_count", 0),
    "usage": body.get("usage"),
}
```

Follow the error handling pattern from `app/providers/revenueinfra/validate_job.py`.

Commit standalone with message: `add Modal provider adapter for ICP title extraction via Anthropic`

---

## Deliverable 3: Contract

**File:** `app/contracts/icp_extraction.py` (new file)

```python
from pydantic import BaseModel


class IcpTitleItem(BaseModel):
    title: str
    buyer_role: str | None = None
    reasoning: str | None = None


class ExtractIcpTitlesOutput(BaseModel):
    company_domain: str | None = None
    company_name: str | None = None
    titles: list[IcpTitleItem] | None = None
    title_count: int | None = None
    usage: dict | None = None
    source_provider: str = "modal_anthropic"
```

Commit standalone with message: `add contract for ICP title extraction output`

---

## Deliverable 4: Service Layer — Persistence Functions

### File: `app/services/icp_job_titles.py` (existing file — add functions, do NOT modify existing functions)

Add:

**`update_icp_extracted_titles`:**
```python
def update_icp_extracted_titles(
    *,
    org_id: str,
    company_domain: str,
    extracted_titles: list[dict[str, Any]],
) -> dict[str, Any] | None:
```

Finds the `icp_job_titles` row by `(org_id, company_domain)` and updates the `extracted_titles` JSONB column. Returns the updated row, or None if not found.

**`upsert_icp_title_details_batch`:**
```python
def upsert_icp_title_details_batch(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None,
    titles: list[dict[str, Any]],
    source_icp_job_titles_id: str | None = None,
) -> list[dict[str, Any]]:
```

For each title in the list, upsert into `extracted_icp_job_title_details` with `on_conflict="org_id,company_domain,title_normalized"`. Each row gets: `org_id`, `company_domain`, `company_name`, `title`, `buyer_role`, `reasoning`, `source_icp_job_titles_id`. Returns list of upserted rows.

Normalize `company_domain` using the same `_normalize_company_domain` function already in this file.

Commit standalone with message: `add persistence functions for extracted ICP titles`

---

## Deliverable 5: Service Operation

**File:** `app/services/icp_extraction_operations.py` (new file)

```python
async def execute_company_derive_extract_icp_titles(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction from cumulative context:**
- `company_domain` — from `input_data` or `cumulative_context`
- `raw_parallel_output` — from `input_data` or `cumulative_context.parallel_raw_response.output.content` or `cumulative_context.raw_parallel_output`
- `raw_parallel_icp_id` — from `input_data` or `cumulative_context`

If `company_domain` and `raw_parallel_output` are not available in cumulative context, attempt to look them up from the `icp_job_titles` table by `company_domain` using the existing `query_icp_job_titles` function.

**Required inputs:** `company_domain` and `raw_parallel_output`. Missing either → return `status: "failed"` with `missing_inputs`.

**Provider call:**
```python
result = await extract_icp_titles(
    company_domain=company_domain,
    raw_parallel_output=raw_parallel_output,
    raw_parallel_icp_id=raw_parallel_icp_id,
)
```

**On success:**
1. Validate with `ExtractIcpTitlesOutput` contract.
2. Call `update_icp_extracted_titles` to write the titles array to `icp_job_titles.extracted_titles`.
3. Call `upsert_icp_title_details_batch` to write flat rows to `extracted_icp_job_title_details`.
4. Return the standard result shape with status `"found"` and the mapped output.

**Operation ID:** `"company.derive.extract_icp_titles"`

Follow the attempt tracking + status derivation pattern from existing operation services.

Commit standalone with message: `add company.derive.extract_icp_titles operation service`

---

## Deliverable 6: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.derive.extract_icp_titles"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_derive_extract_icp_titles` from `app.services.icp_extraction_operations`.
3. Add dispatch branch:

```python
if payload.operation_id == "company.derive.extract_icp_titles":
    result = await execute_company_derive_extract_icp_titles(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire company.derive.extract_icp_titles into execute router`

---

## Deliverable 7: Query Endpoint

**File:** `app/routers/entities_v1.py`

### `POST /api/v1/icp-title-details/query`

**Request body:**
```python
class IcpTitleDetailsQueryRequest(BaseModel):
    company_domain: str | None = None
    buyer_role: str | None = None
    limit: int = 100
    offset: int = 0
    org_id: str | None = None
```

**Auth:** `_resolve_flexible_auth`. Tenant scoped by org_id. Super-admin requires org_id in body.

**Logic:** Query `extracted_icp_job_title_details` with filters. Return `DataEnvelope(data=results)`.

Add a simple query function in `app/services/icp_job_titles.py`:

```python
def query_icp_title_details(
    *,
    org_id: str,
    company_domain: str | None = None,
    buyer_role: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

Commit standalone with message: `add query endpoint for extracted ICP title details`

---

## Deliverable 8: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Company Derive section:
```
| `company.derive.extract_icp_titles` | Modal/Anthropic (extracts consistent title/buyer_role/reasoning from raw Parallel ICP output) |
```

Update operation count (61 total).

Add to Database Schema section:
```
| 017 | `extracted_icp_job_title_details` + `icp_job_titles.extracted_titles` column — extracted ICP titles in flat and JSONB form |
```

### File: `CLAUDE.md`

Add to migration list:
```
17. `017_icp_title_extraction.sql`
```

Add to API Endpoints:
```
- `POST /api/v1/icp-title-details/query`
```

Commit standalone with message: `update documentation for ICP title extraction operation`

---

## What is NOT in scope

- No changes to the existing `company.derive.icp_job_titles` operation or its Trigger.dev function
- No changes to the Modal function itself
- No backfill of existing icp_job_titles records (separate task after testing)
- No job title comparison/matching against alumni
- No blueprint creation
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file path, new table name, new column added to existing table
(b) Provider adapter function signature and Modal endpoint it calls
(c) Contract field counts
(d) Persistence function signatures (both)
(e) Operation service input extraction logic (what context fields it checks)
(f) Router wiring confirmation
(g) Query endpoint path and supported filters
(h) Anything to flag
