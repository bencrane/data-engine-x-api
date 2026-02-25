# Directive: Company + Person Intel Briefing Dedicated Tables, Auto-Persist, and Backfill

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have three Parallel.ai Deep Research operations: ICP job titles, company intel briefing, and person intel briefing. The ICP job titles operation already has a dedicated table (`icp_job_titles`), an internal upsert endpoint, a query endpoint, and a backfill script. The company and person intel briefing operations do NOT — their output is buried in `step_results` and not easily queryable. This directive creates the same pattern for both: dedicated table, service, internal upsert endpoint, query endpoint, backfill script from existing runs, and auto-persist wiring in the pipeline runner. It also adds the auto-persist for ICP job titles that is currently missing from the pipeline runner.

---

## Reference implementations (read ALL of these before starting)

These are the EXACT patterns you will replicate. Do not invent new patterns.

- `supabase/migrations/015_icp_job_titles.sql` — migration pattern (table, unique index, updated_at trigger, RLS)
- `app/services/icp_job_titles.py` — service pattern (upsert with domain normalization, query with filters)
- `app/routers/internal.py` — find the `POST /api/internal/icp-job-titles/upsert` endpoint. Replicate for both new tables.
- `app/routers/entities_v1.py` — find the `POST /api/v1/icp-job-titles/query` endpoint. Replicate for both new tables.
- `scripts/backfill_icp_job_titles.py` — backfill script pattern (find succeeded child runs by submission, extract from step_results, upsert)
- `trigger/src/tasks/run-pipeline.ts` — the step execution branch (around line 1308) where you will add auto-persist blocks

---

## Deliverable 1: Migrations

**File:** `supabase/migrations/016_intel_briefing_tables.sql` (new file)

Two tables in one migration. Follow the `015_icp_job_titles.sql` pattern exactly.

### Table: `company_intel_briefings`

```sql
CREATE TABLE IF NOT EXISTS company_intel_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    client_company_name TEXT,
    client_company_description TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_intel_briefings_dedup
    ON company_intel_briefings(org_id, company_domain, client_company_name);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_org
    ON company_intel_briefings(org_id);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_domain
    ON company_intel_briefings(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_intel_briefings_client
    ON company_intel_briefings(org_id, client_company_name);

DROP TRIGGER IF EXISTS update_company_intel_briefings_updated_at ON company_intel_briefings;
CREATE TRIGGER update_company_intel_briefings_updated_at
    BEFORE UPDATE ON company_intel_briefings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_intel_briefings ENABLE ROW LEVEL SECURITY;
```

**Note:** The dedup is on `(org_id, company_domain, client_company_name)` — NOT just domain. The same company (CoreWeave) can have briefings through different client lenses (SecurityPal vs WithCoverage). Each client+target combination is unique.

### Table: `person_intel_briefings`

```sql
CREATE TABLE IF NOT EXISTS person_intel_briefings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    person_linkedin_url TEXT,
    person_full_name TEXT NOT NULL,
    person_current_company_name TEXT,
    person_current_job_title TEXT,
    client_company_name TEXT,
    client_company_description TEXT,
    customer_company_name TEXT,
    raw_parallel_output JSONB NOT NULL,
    parallel_run_id TEXT,
    processor TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_person_intel_briefings_dedup
    ON person_intel_briefings(org_id, person_full_name, person_current_company_name, client_company_name);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_org
    ON person_intel_briefings(org_id);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_linkedin
    ON person_intel_briefings(org_id, person_linkedin_url);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_company
    ON person_intel_briefings(org_id, person_current_company_name);
CREATE INDEX IF NOT EXISTS idx_person_intel_briefings_client
    ON person_intel_briefings(org_id, client_company_name);

DROP TRIGGER IF EXISTS update_person_intel_briefings_updated_at ON person_intel_briefings;
CREATE TRIGGER update_person_intel_briefings_updated_at
    BEFORE UPDATE ON person_intel_briefings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE person_intel_briefings ENABLE ROW LEVEL SECURITY;
```

**Note:** The dedup is on `(org_id, person_full_name, person_current_company_name, client_company_name)`. The same person can have briefings through different client lenses.

Copy this SQL exactly.

Commit standalone with message: `add 016 migration for company_intel_briefings and person_intel_briefings tables`

---

## Deliverable 2: Service Layer

### File: `app/services/company_intel_briefings.py` (new file)

Follow `app/services/icp_job_titles.py` exactly. Same normalization helpers, same upsert/query pattern.

**`upsert_company_intel_briefing`:**
```python
def upsert_company_intel_briefing(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    client_company_name: str | None = None,
    client_company_description: str | None = None,
    raw_parallel_output: dict[str, Any],
    parallel_run_id: str | None = None,
    processor: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
```

Upsert on conflict `org_id,company_domain,client_company_name`. Normalize `company_domain` same as ICP service.

**`query_company_intel_briefings`:**
```python
def query_company_intel_briefings(
    *,
    org_id: str,
    company_domain: str | None = None,
    client_company_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

### File: `app/services/person_intel_briefings.py` (new file)

Same pattern.

**`upsert_person_intel_briefing`:**
```python
def upsert_person_intel_briefing(
    *,
    org_id: str,
    person_full_name: str,
    person_linkedin_url: str | None = None,
    person_current_company_name: str | None = None,
    person_current_job_title: str | None = None,
    client_company_name: str | None = None,
    client_company_description: str | None = None,
    customer_company_name: str | None = None,
    raw_parallel_output: dict[str, Any],
    parallel_run_id: str | None = None,
    processor: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
```

Upsert on conflict `org_id,person_full_name,person_current_company_name,client_company_name`. Normalize `person_linkedin_url` if provided (lowercase, strip trailing slash).

**`query_person_intel_briefings`:**
```python
def query_person_intel_briefings(
    *,
    org_id: str,
    person_linkedin_url: str | None = None,
    person_current_company_name: str | None = None,
    client_company_name: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

Commit standalone with message: `add service layers for company and person intel briefings`

---

## Deliverable 3: Internal Endpoints

**File:** `app/routers/internal.py`

Add two new endpoints following the exact pattern of `POST /api/internal/icp-job-titles/upsert`.

### `POST /api/internal/company-intel-briefings/upsert`

Request body fields: `company_domain`, `company_name`, `client_company_name`, `client_company_description`, `raw_parallel_output`, `parallel_run_id`, `processor`, `source_submission_id`, `source_pipeline_run_id`.

### `POST /api/internal/person-intel-briefings/upsert`

Request body fields: `person_full_name`, `person_linkedin_url`, `person_current_company_name`, `person_current_job_title`, `client_company_name`, `client_company_description`, `customer_company_name`, `raw_parallel_output`, `parallel_run_id`, `processor`, `source_submission_id`, `source_pipeline_run_id`.

Both use `Depends(require_internal_key)` and extract `org_id` from `x-internal-org-id` header.

Commit standalone with message: `add internal upsert endpoints for company and person intel briefings`

---

## Deliverable 4: Query Endpoints

**File:** `app/routers/entities_v1.py`

Add two new endpoints following the exact pattern of `POST /api/v1/icp-job-titles/query`.

### `POST /api/v1/company-intel-briefings/query`

Filters: `company_domain`, `client_company_name`, `limit`, `offset`, `org_id` (super-admin).

### `POST /api/v1/person-intel-briefings/query`

Filters: `person_linkedin_url`, `person_current_company_name`, `client_company_name`, `limit`, `offset`, `org_id` (super-admin).

Both use `_resolve_flexible_auth`.

Commit standalone with message: `add query endpoints for company and person intel briefings`

---

## Deliverable 5: Auto-Persist in Pipeline Runner

**File:** `trigger/src/tasks/run-pipeline.ts`

Add three auto-persist blocks. All three go in the same location: after the step execution branch produces a result, BEFORE the `cumulativeContext = mergeContext(...)` line (around line 1324).

Each block follows the same pattern: check operation ID + result status, call internal upsert endpoint, wrapped in try/catch that logs warning on failure but does NOT fail the pipeline step.

### Block 1: ICP Job Titles auto-persist

```typescript
if (operationId === "company.derive.icp_job_titles" && result.status === "found" && result.output) {
  try {
    await internalPost(internalConfig, "/api/internal/icp-job-titles/upsert", {
      company_domain: result.output.domain || result.output.company_domain,
      company_name: result.output.company_name,
      company_description: result.output.company_description,
      raw_parallel_output: (result.output.parallel_raw_response as Record<string, unknown>)?.output?.content || result.output.parallel_raw_response,
      parallel_run_id: result.output.parallel_run_id,
      processor: result.output.processor,
      source_submission_id: run.submission_id,
      source_pipeline_run_id: pipeline_run_id,
    });
    logger.info("ICP job titles persisted to dedicated table", {
      domain: result.output.domain || result.output.company_domain,
      pipeline_run_id,
    });
  } catch (error) {
    logger.warn("Failed to persist ICP job titles to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

### Block 2: Company Intel Briefing auto-persist

```typescript
if (operationId === "company.derive.intel_briefing" && result.status === "found" && result.output) {
  try {
    await internalPost(internalConfig, "/api/internal/company-intel-briefings/upsert", {
      company_domain: result.output.domain || result.output.target_company_domain,
      company_name: result.output.company_name || result.output.target_company_name,
      client_company_name: result.output.client_company_name,
      client_company_description: result.output.client_company_description,
      raw_parallel_output: (result.output.parallel_raw_response as Record<string, unknown>)?.output?.content || result.output.parallel_raw_response,
      parallel_run_id: result.output.parallel_run_id,
      processor: result.output.processor,
      source_submission_id: run.submission_id,
      source_pipeline_run_id: pipeline_run_id,
    });
    logger.info("Company intel briefing persisted to dedicated table", {
      domain: result.output.domain || result.output.target_company_domain,
      client: result.output.client_company_name,
      pipeline_run_id,
    });
  } catch (error) {
    logger.warn("Failed to persist company intel briefing to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

### Block 3: Person Intel Briefing auto-persist

```typescript
if (operationId === "person.derive.intel_briefing" && result.status === "found" && result.output) {
  try {
    await internalPost(internalConfig, "/api/internal/person-intel-briefings/upsert", {
      person_full_name: result.output.full_name || result.output.person_full_name,
      person_linkedin_url: result.output.linkedin_url || result.output.person_linkedin_url,
      person_current_company_name: result.output.person_current_company_name,
      person_current_job_title: result.output.title || result.output.person_current_job_title,
      client_company_name: result.output.client_company_name,
      client_company_description: result.output.client_company_description,
      customer_company_name: result.output.customer_company_name,
      raw_parallel_output: (result.output.parallel_raw_response as Record<string, unknown>)?.output?.content || result.output.parallel_raw_response,
      parallel_run_id: result.output.parallel_run_id,
      processor: result.output.processor,
      source_submission_id: run.submission_id,
      source_pipeline_run_id: pipeline_run_id,
    });
    logger.info("Person intel briefing persisted to dedicated table", {
      person: result.output.full_name || result.output.person_full_name,
      pipeline_run_id,
    });
  } catch (error) {
    logger.warn("Failed to persist person intel briefing to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

Commit standalone with message: `add auto-persist to dedicated tables for all three Parallel Deep Research operations`

---

## Deliverable 6: Backfill Scripts

### File: `scripts/backfill_company_intel_briefings.py` (new file)

Follow `scripts/backfill_icp_job_titles.py` exactly.

**Targets:** Two submissions that ran company intel briefings:
- `b8001673-d0a4-4c4f-824a-9904964d8400` (SecurityPal → CoreWeave)
- `5d1cb2b3-bbf9-4582-a29f-3167d22dec51` (SecurityPal → Elastic)
- `31484f3a-5285-42ad-a8a9-892e79e9eabe` (WithCoverage → HelloFresh)

**Org ID:** `b0293785-aa7a-4234-8201-cc47305295f8`

**Extraction path from step_results:**
- `company_domain` from `output_payload.operation_result.output.domain` or `output_payload.operation_result.output.target_company_domain`
- `company_name` from `output_payload.operation_result.output.company_name` or `output_payload.operation_result.output.target_company_name`
- `client_company_name` from `output_payload.operation_result.output.client_company_name`
- `client_company_description` from `output_payload.operation_result.output.client_company_description`
- `raw_parallel_output` from `output_payload.operation_result.output.parallel_raw_response.output.content`
- `parallel_run_id` from `output_payload.operation_result.output.parallel_run_id`
- `processor` from `output_payload.operation_result.output.processor`

**Logic:** Iterate all three submission IDs. For each, find succeeded pipeline runs, extract step results, upsert. Print progress and summary.

### File: `scripts/backfill_person_intel_briefings.py` (new file)

Same pattern.

**Targets:** One submission:
- `35d818c4-2159-4e5d-89a7-dddf92470c57` (Jim Higgins @ CoreWeave)

**Org ID:** `b0293785-aa7a-4234-8201-cc47305295f8`

**Extraction path from step_results:**
- `person_full_name` from `output_payload.operation_result.output.full_name` or `output_payload.operation_result.output.person_full_name`
- `person_linkedin_url` from `output_payload.operation_result.output.linkedin_url` or `output_payload.operation_result.output.person_linkedin_url`
- `person_current_company_name` from `output_payload.operation_result.output.person_current_company_name`
- `person_current_job_title` from `output_payload.operation_result.output.title` or `output_payload.operation_result.output.person_current_job_title`
- `client_company_name` from `output_payload.operation_result.output.client_company_name`
- `client_company_description` from `output_payload.operation_result.output.client_company_description`
- `customer_company_name` from `output_payload.operation_result.output.customer_company_name`
- `raw_parallel_output` from `output_payload.operation_result.output.parallel_raw_response.output.content`
- `parallel_run_id` from `output_payload.operation_result.output.parallel_run_id`
- `processor` from `output_payload.operation_result.output.processor`

Both scripts runnable with: `doppler run -p data-engine-x-api -c prd -- uv run python scripts/backfill_<name>.py`

Commit standalone with message: `add backfill scripts for company and person intel briefings`

---

## Deliverable 7: Update Documentation

### File: `CLAUDE.md`

Add new endpoints to the API Endpoints list:
```
- `POST /api/internal/company-intel-briefings/upsert`
- `POST /api/internal/person-intel-briefings/upsert`
- `POST /api/v1/company-intel-briefings/query`
- `POST /api/v1/person-intel-briefings/query`
```

Add to Database / Migrations section:
```
15. `016_intel_briefing_tables.sql`
```

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Database Schema section:
```
| 016 | `company_intel_briefings` + `person_intel_briefings` — raw Parallel.ai intel briefing output, one row per entity per client lens |
```

Commit standalone with message: `update documentation for intel briefing tables and endpoints`

---

## What is NOT in scope

- No changes to the Parallel prompt templates or operation functions
- No schema normalization of the raw Parallel output
- No changes to entity_relationships wiring
- No deploy commands (but migration and backfill scripts need to be run manually)

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file path and both table names
(b) Service function signatures (all 4: 2 upserts + 2 queries)
(c) Internal endpoint paths
(d) Query endpoint paths and supported filters
(e) Dedup constraint fields for each table
(f) All three auto-persist blocks: confirm operation ID, status gate, try/catch wrapping
(g) Backfill scripts: file paths, submission IDs targeted, how to run
(h) Anything to flag
