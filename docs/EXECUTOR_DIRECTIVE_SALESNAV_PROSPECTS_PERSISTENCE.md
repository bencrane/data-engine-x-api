# Directive: Sales Nav Prospects Persistence Layer

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The `person.search.sales_nav_url` operation scrapes LinkedIn Sales Navigator search URLs and returns alumni/prospect lists. These are people at target companies who match specific job titles and seniority filters. Currently the data only persists to `step_results`. We need a dedicated `salesnav_prospects` table so this data is directly queryable — particularly for the AlumniGTM use case where we need to join: "prospects who are alumni of companies that are customers of our client's target."

The join path is: `company_customers` (client target → customer company) → `salesnav_prospects` (customer company → person prospect).

---

## Existing code to read before starting

- `app/providers/rapidapi_salesnav.py` — read `_map_person` (~line 38) for the exact person fields returned. Read `scrape_sales_nav_url` (~line 68) for the full mapped output shape: `{results: [person, ...], result_count, total_available, page, source_url}`.
- `app/services/salesnav_operations.py` — existing service function for `person.search.sales_nav_url`. Read to understand the operation output shape.
- `app/services/company_customers.py` — pattern reference for a dedicated table upsert/query service.
- `app/routers/internal.py` — pattern for internal upsert endpoints.
- `app/routers/entities_v1.py` — pattern for tenant query endpoints.
- `trigger/src/tasks/run-pipeline.ts` — read existing auto-persist blocks for the pattern.
- `supabase/migrations/018_alumnigtm_persistence.sql` — pattern for table creation.

---

## Deliverable 1: Migration

**File:** `supabase/migrations/020_salesnav_prospects.sql` (new file)

```sql
-- 020_salesnav_prospects.sql
-- Alumni/prospect data from LinkedIn Sales Navigator scrapes.

CREATE TABLE IF NOT EXISTS salesnav_prospects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,

    -- The person
    full_name TEXT,
    first_name TEXT,
    last_name TEXT,
    linkedin_url TEXT,
    profile_urn TEXT,
    geo_region TEXT,
    summary TEXT,
    current_title TEXT,
    current_company_name TEXT,
    current_company_id TEXT,
    current_company_industry TEXT,
    current_company_location TEXT,
    position_start_month INT,
    position_start_year INT,
    tenure_at_position_years INT,
    tenure_at_position_months INT,
    tenure_at_company_years INT,
    tenure_at_company_months INT,
    open_link BOOLEAN,

    -- Source context: which company were they found at, via what query
    source_company_domain TEXT NOT NULL,
    source_company_name TEXT,
    source_salesnav_url TEXT,

    -- Lineage
    discovered_by_operation_id TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,

    -- Raw archive
    raw_person JSONB NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: one person per company per org, identified by LinkedIn URL
CREATE UNIQUE INDEX IF NOT EXISTS idx_salesnav_prospects_dedup
    ON salesnav_prospects(org_id, source_company_domain, linkedin_url)
    WHERE linkedin_url IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_org
    ON salesnav_prospects(org_id);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_source_company
    ON salesnav_prospects(org_id, source_company_domain);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_linkedin
    ON salesnav_prospects(org_id, linkedin_url);
CREATE INDEX IF NOT EXISTS idx_salesnav_prospects_title
    ON salesnav_prospects(org_id, current_title);

DROP TRIGGER IF EXISTS update_salesnav_prospects_updated_at ON salesnav_prospects;
CREATE TRIGGER update_salesnav_prospects_updated_at
    BEFORE UPDATE ON salesnav_prospects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE salesnav_prospects ENABLE ROW LEVEL SECURITY;
```

**Column rationale:**
- Person fields match exactly what `_map_person` in `rapidapi_salesnav.py` returns — no guessing, no mismatch.
- `source_company_domain` — the company this Sales Nav search was scoped to (e.g., `aoshearman.com`). This is the join key to `company_customers`.
- `source_company_name` — denormalized for display without needing to join.
- `source_salesnav_url` — the exact Sales Nav URL that was scraped. Encodes the title/seniority/geo filters used.
- `raw_person` — the full raw person object from the RapidAPI response. Authoritative store.
- Dedup on `(org_id, source_company_domain, linkedin_url)` — same person at the same company only stored once per org. Partial index since `linkedin_url` can theoretically be null.

Commit standalone with message: `migration 020: add salesnav_prospects table`

---

## Deliverable 2: Upsert + Query Service

**File:** `app/services/salesnav_prospects.py` (new file)

### `upsert_salesnav_prospects`

```python
def upsert_salesnav_prospects(
    *,
    org_id: str,
    source_company_domain: str,
    source_company_name: str | None = None,
    source_salesnav_url: str | None = None,
    prospects: list[dict[str, Any]],
    discovered_by_operation_id: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

Logic:
1. Normalize `source_company_domain` (lowercase, strip protocol/www — use same `_normalize_company_domain` helper pattern from `icp_job_titles.py`).
2. For each prospect dict in `prospects`, build a row mapping each field directly from the person dict. The prospect dicts come from `_map_person` in `rapidapi_salesnav.py` and have these exact keys:
   - `full_name`, `first_name`, `last_name`, `linkedin_url`, `profile_urn`, `geo_region`, `summary`
   - `current_title`, `current_company_name`, `current_company_id`, `current_company_industry`, `current_company_location`
   - `position_start_month`, `position_start_year`
   - `tenure_at_position_years`, `tenure_at_position_months`, `tenure_at_company_years`, `tenure_at_company_months`
   - `open_link`
3. Set `raw_person = prospect` (the full dict).
4. Set `org_id`, `source_company_domain`, `source_company_name`, `source_salesnav_url`, `discovered_by_operation_id`, source IDs, `updated_at`.
5. Skip prospects that have no `linkedin_url` AND no `full_name` (unusable).
6. Upsert to `salesnav_prospects` with `on_conflict="org_id,source_company_domain,linkedin_url"`.
7. Return upserted rows.

### `query_salesnav_prospects`

```python
def query_salesnav_prospects(
    *,
    org_id: str,
    source_company_domain: str | None = None,
    current_title: str | None = None,
    linkedin_url: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

Standard query with optional filters. If `current_title` is provided, use `ilike` for partial matching. Ordered by `created_at` desc.

Commit standalone with message: `add salesnav_prospects upsert and query service`

---

## Deliverable 3: Internal Endpoint

**File:** `app/routers/internal.py`

### Request model

```python
class InternalUpsertSalesNavProspectsRequest(BaseModel):
    source_company_domain: str
    source_company_name: str | None = None
    source_salesnav_url: str | None = None
    prospects: list[dict[str, Any]]
    discovered_by_operation_id: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

### Endpoint

**`POST /salesnav-prospects/upsert`**
- Requires internal key auth
- Extracts `org_id` from `x-internal-org-id` header
- Calls `upsert_salesnav_prospects` from `app.services.salesnav_prospects`
- Returns `DataEnvelope(data=result)`

Import the service function at the top of the file.

Commit standalone with message: `add internal upsert endpoint for salesnav_prospects`

---

## Deliverable 4: Auto-Persist Wiring in Pipeline Runner

**File:** `trigger/src/tasks/run-pipeline.ts`

Add an auto-persist block after the existing auto-persist blocks, before the `cumulativeContext = mergeContext(...)` line.

```typescript
if (operationId === "person.search.sales_nav_url" && result.status === "found" && result.output) {
  try {
    const output = result.output as Record<string, unknown>;
    const results = output.results;
    if (Array.isArray(results) && results.length > 0) {
      const sourceCompanyDomain = String(
        cumulativeContext.company_domain || cumulativeContext.domain || cumulativeContext.canonical_domain || ""
      );
      const sourceCompanyName = String(
        cumulativeContext.company_name || cumulativeContext.canonical_name || ""
      );
      const sourceSalesnavUrl = String(output.source_url || "");
      if (sourceCompanyDomain) {
        await internalPost(internalConfig, "/api/internal/salesnav-prospects/upsert", {
          source_company_domain: sourceCompanyDomain,
          source_company_name: sourceCompanyName || null,
          source_salesnav_url: sourceSalesnavUrl || null,
          prospects: results,
          discovered_by_operation_id: operationId,
          source_submission_id: run.submission_id,
          source_pipeline_run_id: pipeline_run_id,
        });
        logger.info("Sales Nav prospects persisted to dedicated table", {
          domain: sourceCompanyDomain,
          prospect_count: results.length,
          pipeline_run_id,
        });
      }
    }
  } catch (error) {
    logger.warn("Failed to persist Sales Nav prospects to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

**Key data flow note:** The `results` array contains person dicts with exactly the fields from `_map_person` in `rapidapi_salesnav.py`. The `source_url` is in `output.source_url` — this is the Sales Nav URL that was scraped. The `source_company_domain` comes from cumulative context, which is the company this pipeline run is processing.

Wrapped in try/catch — failure logs warning, never fails pipeline.

Commit standalone with message: `add auto-persist wiring for salesnav_prospects in pipeline runner`

---

## Deliverable 5: Tenant Query Endpoint

**File:** `app/routers/entities_v1.py`

### `POST /api/v1/salesnav-prospects/query`

Request body: `source_company_domain` (optional), `current_title` (optional, partial match), `linkedin_url` (optional), `limit` (default 100), `offset` (default 0).

Calls `query_salesnav_prospects` from `app.services.salesnav_prospects`. Uses tenant auth. Scoped by `org_id`.

Commit standalone with message: `add tenant query endpoint for salesnav_prospects`

---

## Deliverable 6: Update Documentation

### File: `CLAUDE.md`

Add to API Endpoints:
```
- `POST /api/v1/salesnav-prospects/query`
- `POST /api/internal/salesnav-prospects/upsert`
```

Add to Database / Migrations:
```
20. `020_salesnav_prospects.sql`
```

### File: `docs/SYSTEM_OVERVIEW.md`

Add `salesnav_prospects` table to Infrastructure Features. Update migration table.

Commit standalone with message: `update documentation for salesnav_prospects persistence layer`

---

## What is NOT in scope

- No changes to the existing `person.search.sales_nav_url` operation or `rapidapi_salesnav.py` provider
- No changes to existing service functions
- No deploy commands
- Do NOT run the migration — the chief agent runs it after review

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file name, table name, column list, dedup strategy
(b) Upsert function signature — how prospect fields are mapped (confirm they match `_map_person` output exactly)
(c) Query function signature and available filters (confirm `current_title` uses ilike)
(d) Internal endpoint path and request model fields
(e) Auto-persist — operation_id trigger, where `source_company_domain` and `source_salesnav_url` come from in context
(f) Tenant query endpoint path
(g) Anything to flag
