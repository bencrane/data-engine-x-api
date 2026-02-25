# Directive: ICP Job Titles Table + Backfill from Existing Step Results

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have ~150 companies that already went through Parallel.ai Deep Research for ICP job title discovery. The raw Parallel output is stored in `step_results.output_payload` but is not easily queryable by domain. We need a dedicated table to store the raw Parallel ICP output per company (one row per company, JSONB column for the raw output), an internal endpoint to write to it, a query endpoint to read from it, and a backfill script that extracts from existing step results and populates the new table.

---

## Existing data location

The 150 completed ICP runs are under submission `0921f10b-890b-47ab-8ceb-b1986df51cbb`. Each succeeded child pipeline run has a step result where:
- `output_payload.operation_result.output.company_name` — company name
- `output_payload.operation_result.output.domain` — company domain
- `output_payload.operation_result.output.company_description` — company description
- `output_payload.operation_result.output.parallel_raw_response.output.content` — the actual ICP research content (JSONB)
- `output_payload.operation_result.output.parallel_run_id` — the Parallel task run ID
- `output_payload.operation_result.output.processor` — the processor used ("pro")

The content schema varies per company (Parallel `auto` schema). Some have `titles` array, some have `champion_personas` + `evaluator_personas` + `decision_maker_personas`, some have other structures. Do NOT attempt to normalize — store the raw content as-is.

---

## Existing code to read before starting

- `supabase/migrations/014_entity_relationships.sql` — reference pattern for a recent migration
- `app/services/entity_relationships.py` — reference pattern for a simple service with upsert + query
- `app/routers/internal.py` — where internal endpoints live
- `app/routers/entities_v1.py` — where tenant query endpoints live
- `app/database.py` — `get_supabase_client()`

---

## Deliverable 1: Migration

**File:** `supabase/migrations/015_icp_job_titles.sql` (new file)

```sql
-- 015_icp_job_titles.sql
-- Raw Parallel.ai ICP job title research output per company.

CREATE TABLE IF NOT EXISTS icp_job_titles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    company_description TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_icp_job_titles_dedup
    ON icp_job_titles(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_icp_job_titles_org
    ON icp_job_titles(org_id);
CREATE INDEX IF NOT EXISTS idx_icp_job_titles_domain
    ON icp_job_titles(org_id, company_domain);

DROP TRIGGER IF EXISTS update_icp_job_titles_updated_at ON icp_job_titles;
CREATE TRIGGER update_icp_job_titles_updated_at
    BEFORE UPDATE ON icp_job_titles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE icp_job_titles ENABLE ROW LEVEL SECURITY;
```

Copy this SQL exactly.

Commit standalone with message: `add 015_icp_job_titles migration for raw Parallel ICP output per company`

---

## Deliverable 2: Service Layer

**File:** `app/services/icp_job_titles.py` (new file)

### `upsert_icp_job_titles`

```python
def upsert_icp_job_titles(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    company_description: str | None = None,
    raw_parallel_output: dict[str, Any],
    parallel_run_id: str | None = None,
    processor: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
```

**Logic:**
1. Normalize `company_domain` — strip protocol, www, trailing slash, lowercase (same normalization as entity_relationships).
2. Upsert using Supabase `.upsert()` with `on_conflict="org_id,company_domain"`.
3. On conflict (existing row), update: `raw_parallel_output`, `company_name` (if provided), `company_description` (if provided), `parallel_run_id`, `processor`, `source_submission_id`, `source_pipeline_run_id`, `updated_at`.
4. Return the upserted row.

### `query_icp_job_titles`

```python
def query_icp_job_titles(
    *,
    org_id: str,
    company_domain: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

**Logic:**
1. Query `icp_job_titles` filtered by `org_id`.
2. If `company_domain` provided, normalize and filter by it.
3. Order by `created_at` descending.
4. Apply limit and offset.
5. Return list of rows.

Commit standalone with message: `add icp_job_titles service with upsert and query functions`

---

## Deliverable 3: Internal Endpoint

**File:** `app/routers/internal.py`

### `POST /api/internal/icp-job-titles/upsert`

**Request body:**
```python
class InternalUpsertIcpJobTitlesRequest(BaseModel):
    company_domain: str
    company_name: str | None = None
    company_description: str | None = None
    raw_parallel_output: dict[str, Any]
    parallel_run_id: str | None = None
    processor: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

**Logic:** Extract `org_id` from internal auth headers. Call `upsert_icp_job_titles`. Return `DataEnvelope(data=result)`.

Uses `Depends(require_internal_key)` for auth.

Commit standalone with message: `add internal endpoint for upserting ICP job titles`

---

## Deliverable 4: Query Endpoint

**File:** `app/routers/entities_v1.py`

### `POST /api/v1/icp-job-titles/query`

**Request body:**
```python
class IcpJobTitlesQueryRequest(BaseModel):
    company_domain: str | None = None
    limit: int = 100
    offset: int = 0
    org_id: str | None = None  # required for super-admin auth
```

**Auth:** Uses the same flexible auth as other entity endpoints (`_resolve_flexible_auth`). Tenant auth scopes by org_id. Super-admin requires `org_id` in body.

**Logic:** Call `query_icp_job_titles`. Return `DataEnvelope(data=results)`.

Commit standalone with message: `add ICP job titles query endpoint`

---

## Deliverable 5: Backfill Script

**File:** `scripts/backfill_icp_job_titles.py` (new file)

This script extracts ICP job title data from existing step results and writes to the new `icp_job_titles` table.

**Logic:**

1. Connect to the database using `get_supabase_client()`.
2. Query all succeeded child pipeline runs for submission `0921f10b-890b-47ab-8ceb-b1986df51cbb`:
   ```python
   pipeline_runs = client.table("pipeline_runs") \
       .select("id, submission_id, parent_pipeline_run_id, status") \
       .eq("submission_id", "0921f10b-890b-47ab-8ceb-b1986df51cbb") \
       .eq("status", "succeeded") \
       .not_.is_("parent_pipeline_run_id", "null") \
       .execute()
   ```
3. For each pipeline run, fetch its step result:
   ```python
   step_results = client.table("step_results") \
       .select("output_payload") \
       .eq("pipeline_run_id", run_id) \
       .eq("status", "succeeded") \
       .execute()
   ```
4. Extract from each step result:
   - `company_domain` from `output_payload.operation_result.output.domain`
   - `company_name` from `output_payload.operation_result.output.company_name`
   - `company_description` from `output_payload.operation_result.output.company_description`
   - `raw_parallel_output` from `output_payload.operation_result.output.parallel_raw_response.output.content`
   - `parallel_run_id` from `output_payload.operation_result.output.parallel_run_id`
   - `processor` from `output_payload.operation_result.output.processor`
5. Skip if `company_domain` is missing or `raw_parallel_output` is empty.
6. Call `upsert_icp_job_titles` for each valid record with `org_id = "b0293785-aa7a-4234-8201-cc47305295f8"` (AlumniGTM org).
7. Print progress: company name, domain, success/skip for each record.
8. Print summary: total processed, total upserted, total skipped.

**The script must be runnable with:**
```bash
doppler run -- python scripts/backfill_icp_job_titles.py
```

Make sure to add the necessary imports and use `sys.path` or relative imports so the app modules are accessible.

Commit standalone with message: `add backfill script to extract ICP job titles from step results into dedicated table`

---

## Deliverable 6: Update Documentation

### File: `CLAUDE.md`

Add the new endpoints to the API Endpoints list:
```
- `POST /api/internal/icp-job-titles/upsert`
- `POST /api/v1/icp-job-titles/query`
```

Add to Database / Migrations section:
```
14. `015_icp_job_titles.sql`
```

### File: `docs/SYSTEM_OVERVIEW.md`

Add to the Database Schema section:
```
| 015 | `icp_job_titles` — raw Parallel.ai ICP research output per company (JSONB), one row per company per org |
```

Commit standalone with message: `update documentation for ICP job titles table and endpoints`

---

## What is NOT in scope

- No output schema normalization — raw Parallel output stored as-is in JSONB
- No individual title extraction into rows (future concern)
- No changes to run-pipeline.ts or the ICP job titles operation
- No deploy commands (but the backfill script will need to be run manually after migration)

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file path and table name
(b) Service function signatures
(c) Internal endpoint path and request body fields
(d) Query endpoint path and supported filters
(e) Dedup constraint fields
(f) Backfill script: how to run it, what submission it targets, what org_id it uses
(g) Backfill extraction path (exact keys it reads from step_results)
(h) Anything to flag
