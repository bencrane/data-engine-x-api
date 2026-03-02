# Directive: AlumniGTM Pipeline Persistence Layer

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The AlumniGTM pipeline produces structured data across multiple operations — company enrichment, ICP job titles (Gemini), customer discovery, ICP criterion generation, Sales Nav URL building, and ICP fit evaluation. Currently, most of this data would only persist to `step_results` (the raw archive). We need dedicated columns and tables so the data is directly queryable. This directive adds the schema, upsert services, internal endpoints, and auto-persist wiring in the Trigger.dev pipeline runner.

---

## Existing code to read before starting

- `supabase/migrations/007_entity_state.sql` — existing `company_entities` table schema
- `supabase/migrations/015_icp_job_titles.sql` — pattern for a dedicated research output table
- `app/services/entity_state.py` — read `_company_fields_from_context` (line ~212) and `upsert_company_entity` (line ~550). You will modify `_company_fields_from_context` to handle the new columns.
- `app/services/icp_job_titles.py` — reference pattern for a dedicated table upsert/query service
- `app/routers/internal.py` — read the `InternalUpsertIcpJobTitlesRequest` model and `/icp-job-titles/upsert` endpoint (line ~498). Pattern for new internal endpoints.
- `trigger/src/tasks/run-pipeline.ts` — read the auto-persist blocks starting at line ~1767 (ICP job titles), ~1793 (company intel briefing), ~1822 (person intel briefing). Pattern for new auto-persist wiring.

---

## Deliverable 1: Migration — New Columns on `company_entities`

**File:** `supabase/migrations/018_alumnigtm_persistence.sql` (new file)

Add these columns to `company_entities`:

```sql
-- 018_alumnigtm_persistence.sql
-- AlumniGTM pipeline dedicated persistence: new columns + tables.

-- New columns on company_entities for 1:1 pipeline output data
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS company_linkedin_id TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_criterion TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS salesnav_url TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_verdict TEXT;
ALTER TABLE company_entities ADD COLUMN IF NOT EXISTS icp_fit_reasoning TEXT;
```

These are all nullable TEXT columns. They persist via the standard entity state upsert path — `_company_fields_from_context` maps from cumulative context → column, and `upsert_company_entity` writes them.

Commit standalone with message: `migration 018: add company_linkedin_id, icp_criterion, salesnav_url, icp_fit columns to company_entities`

---

## Deliverable 2: Migration — New `company_customers` Table

**Same file:** `supabase/migrations/018_alumnigtm_persistence.sql` (append to the migration from Deliverable 1)

```sql
-- Discovered customers per company (from Gemini customers-of operation)
CREATE TABLE IF NOT EXISTS company_customers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_entity_id UUID NOT NULL,
    company_domain TEXT NOT NULL,
    customer_name TEXT,
    customer_domain TEXT,
    customer_linkedin_url TEXT,
    customer_org_id TEXT,
    discovered_by_operation_id TEXT,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_company_customers_dedup
    ON company_customers(org_id, company_domain, customer_domain)
    WHERE customer_domain IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_company_customers_org
    ON company_customers(org_id);
CREATE INDEX IF NOT EXISTS idx_company_customers_company
    ON company_customers(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_company_customers_entity
    ON company_customers(org_id, company_entity_id);

DROP TRIGGER IF EXISTS update_company_customers_updated_at ON company_customers;
CREATE TRIGGER update_company_customers_updated_at
    BEFORE UPDATE ON company_customers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE company_customers ENABLE ROW LEVEL SECURITY;
```

Key decisions:
- Dedup on `(org_id, company_domain, customer_domain)` — one customer per domain per company per org. The `WHERE customer_domain IS NOT NULL` partial index allows rows without customer_domain to coexist.
- `company_entity_id` links to the company entity but is NOT a foreign key (company_entities has a composite PK `(org_id, entity_id)`, and we don't want cascading deletes to wipe customer data).
- `company_domain` is denormalized for easy joins without resolving entity_id.

Commit standalone with message: `migration 018: add company_customers table`

---

## Deliverable 3: Migration — New `gemini_icp_job_titles` Table

**Same file:** `supabase/migrations/018_alumnigtm_persistence.sql` (append)

```sql
-- Gemini-sourced ICP job title research output per company
-- Separate from icp_job_titles (which stores raw Parallel.ai output)
CREATE TABLE IF NOT EXISTS gemini_icp_job_titles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_domain TEXT NOT NULL,
    company_name TEXT,
    company_description TEXT,
    inferred_product TEXT,
    buyer_persona TEXT,
    titles JSONB,
    champion_titles JSONB,
    evaluator_titles JSONB,
    decision_maker_titles JSONB,
    raw_response JSONB NOT NULL,
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_gemini_icp_job_titles_dedup
    ON gemini_icp_job_titles(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_gemini_icp_job_titles_org
    ON gemini_icp_job_titles(org_id);

DROP TRIGGER IF EXISTS update_gemini_icp_job_titles_updated_at ON gemini_icp_job_titles;
CREATE TRIGGER update_gemini_icp_job_titles_updated_at
    BEFORE UPDATE ON gemini_icp_job_titles
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE gemini_icp_job_titles ENABLE ROW LEVEL SECURITY;
```

Follows the same pattern as `icp_job_titles` (015) but stores structured Gemini output with individual JSONB columns for title categories, not a single raw blob.

Commit standalone with message: `migration 018: add gemini_icp_job_titles table`

---

## Deliverable 4: Entity State Mapper — Add New Columns

**File:** `app/services/entity_state.py`

### 4a: Update `_company_fields_from_context` (~line 212)

Add these field mappings to the returned dict:

```python
"company_linkedin_id": _normalize_text(canonical_fields.get("company_linkedin_id")),
"icp_criterion": canonical_fields.get("icp_criterion") or canonical_fields.get("criterion"),
"salesnav_url": canonical_fields.get("salesnav_url") or canonical_fields.get("url"),
"icp_fit_verdict": canonical_fields.get("icp_fit_verdict") or canonical_fields.get("verdict"),
"icp_fit_reasoning": canonical_fields.get("icp_fit_reasoning") or canonical_fields.get("reasoning"),
```

For `icp_criterion`, `salesnav_url`, `icp_fit_verdict`, and `icp_fit_reasoning`: do NOT use `_normalize_text` — these are potentially long-form text fields and should preserve casing. Apply `.strip()` if the value is a string, else pass through as-is. Create a small helper if needed:

```python
def _clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
```

### 4b: Update `upsert_company_entity` (~line 608)

Add the 5 new columns to `row_to_write` following the exact same pattern as the existing columns (preserve existing if new is None):

```python
"company_linkedin_id": normalized_fields["company_linkedin_id"]
if normalized_fields["company_linkedin_id"] is not None
else (existing.get("company_linkedin_id") if existing else None),
"icp_criterion": normalized_fields["icp_criterion"]
if normalized_fields["icp_criterion"] is not None
else (existing.get("icp_criterion") if existing else None),
"salesnav_url": normalized_fields["salesnav_url"]
if normalized_fields["salesnav_url"] is not None
else (existing.get("salesnav_url") if existing else None),
"icp_fit_verdict": normalized_fields["icp_fit_verdict"]
if normalized_fields["icp_fit_verdict"] is not None
else (existing.get("icp_fit_verdict") if existing else None),
"icp_fit_reasoning": normalized_fields["icp_fit_reasoning"]
if normalized_fields["icp_fit_reasoning"] is not None
else (existing.get("icp_fit_reasoning") if existing else None),
```

Place these after `enrichment_confidence` and before `last_enriched_at`.

Commit standalone with message: `add company_linkedin_id, icp_criterion, salesnav_url, icp_fit columns to entity state mapper`

---

## Deliverable 5: Company Customers Upsert Service

**File:** `app/services/company_customers.py` (new file)

Follow the exact pattern of `app/services/icp_job_titles.py`.

### `upsert_company_customers`

```python
def upsert_company_customers(
    *,
    org_id: str,
    company_entity_id: str,
    company_domain: str,
    customers: list[dict[str, Any]],
    discovered_by_operation_id: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

Logic:
1. Normalize `company_domain` using the same `_normalize_company_domain` helper (copy or import from `icp_job_titles.py`).
2. Build a list of rows from `customers`. For each customer dict, extract: `customer_name`, `customer_domain`, `customer_linkedin_url`, `customer_org_id`. Skip entries that have no `customer_name` and no `customer_domain`.
3. Each row includes: `org_id`, `company_entity_id`, `company_domain`, customer fields, `discovered_by_operation_id`, `source_submission_id`, `source_pipeline_run_id`, `updated_at`.
4. Upsert to `company_customers` with `on_conflict="org_id,company_domain,customer_domain"`.
5. Return the upserted rows.

### `query_company_customers`

```python
def query_company_customers(
    *,
    org_id: str,
    company_domain: str | None = None,
    company_entity_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

Standard query with org_id filter, optional company_domain or company_entity_id filter, ordered by created_at desc, with limit/offset.

Commit standalone with message: `add company_customers upsert and query service`

---

## Deliverable 6: Gemini ICP Job Titles Upsert Service

**File:** `app/services/gemini_icp_job_titles.py` (new file)

Follow the exact pattern of `app/services/icp_job_titles.py`.

### `upsert_gemini_icp_job_titles`

```python
def upsert_gemini_icp_job_titles(
    *,
    org_id: str,
    company_domain: str,
    company_name: str | None = None,
    company_description: str | None = None,
    inferred_product: str | None = None,
    buyer_persona: str | None = None,
    titles: list[dict[str, Any]] | None = None,
    champion_titles: list[str] | None = None,
    evaluator_titles: list[str] | None = None,
    decision_maker_titles: list[str] | None = None,
    raw_response: dict[str, Any],
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> dict[str, Any]:
```

Logic:
1. Normalize `company_domain`.
2. Build row with all fields. JSONB columns (`titles`, `champion_titles`, `evaluator_titles`, `decision_maker_titles`) are stored as-is.
3. Upsert to `gemini_icp_job_titles` with `on_conflict="org_id,company_domain"`.
4. Return the upserted row.

### `query_gemini_icp_job_titles`

Standard query — same pattern as `query_icp_job_titles` but against `gemini_icp_job_titles` table.

Commit standalone with message: `add gemini_icp_job_titles upsert and query service`

---

## Deliverable 7: Internal Endpoints

**File:** `app/routers/internal.py`

### 7a: Request models

Add two new Pydantic request models. Follow the exact pattern of `InternalUpsertIcpJobTitlesRequest`:

```python
class InternalUpsertCompanyCustomersRequest(BaseModel):
    company_entity_id: str
    company_domain: str
    customers: list[dict[str, Any]]
    discovered_by_operation_id: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None


class InternalUpsertGeminiIcpJobTitlesRequest(BaseModel):
    company_domain: str
    company_name: str | None = None
    company_description: str | None = None
    inferred_product: str | None = None
    buyer_persona: str | None = None
    titles: list[dict[str, Any]] | None = None
    champion_titles: list[str] | None = None
    evaluator_titles: list[str] | None = None
    decision_maker_titles: list[str] | None = None
    raw_response: dict[str, Any]
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

### 7b: Endpoints

Add two endpoints following the exact pattern of `/icp-job-titles/upsert`:

**`POST /company-customers/upsert`**
- Requires internal key auth
- Extracts `org_id` from `x-internal-org-id` header
- Calls `upsert_company_customers` from `app.services.company_customers`
- Returns `DataEnvelope(data=result)`

**`POST /gemini-icp-job-titles/upsert`**
- Requires internal key auth
- Extracts `org_id` from `x-internal-org-id` header
- Calls `upsert_gemini_icp_job_titles` from `app.services.gemini_icp_job_titles`
- Returns `DataEnvelope(data=result)`

### 7c: Imports

Add imports for both new service functions at the top of the file.

Commit standalone with message: `add internal upsert endpoints for company_customers and gemini_icp_job_titles`

---

## Deliverable 8: Auto-Persist Wiring in Pipeline Runner

**File:** `trigger/src/tasks/run-pipeline.ts`

Add two new auto-persist blocks **after** the existing person intel briefing auto-persist block (~line 1853) and **before** the `cumulativeContext = mergeContext(...)` line (~line 1855).

### 8a: Company Customers auto-persist

```typescript
if (operationId === "company.research.discover_customers_gemini" && result.status === "found" && result.output) {
  try {
    const customers = (result.output as Record<string, unknown>).customers;
    if (Array.isArray(customers) && customers.length > 0) {
      const companyDomain = String(
        cumulativeContext.company_domain || cumulativeContext.domain || cumulativeContext.canonical_domain || ""
      );
      const companyEntityId = String(cumulativeContext.entity_id || "");
      if (companyDomain) {
        await internalPost(internalConfig, "/api/internal/company-customers/upsert", {
          company_entity_id: companyEntityId,
          company_domain: companyDomain,
          customers,
          discovered_by_operation_id: operationId,
          source_submission_id: run.submission_id,
          source_pipeline_run_id: pipeline_run_id,
        });
        logger.info("Company customers persisted to dedicated table", {
          domain: companyDomain,
          customer_count: customers.length,
          pipeline_run_id,
        });
      }
    }
  } catch (error) {
    logger.warn("Failed to persist company customers to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

### 8b: Gemini ICP Job Titles auto-persist

```typescript
if (operationId === "company.research.icp_job_titles_gemini" && result.status === "found" && result.output) {
  try {
    const output = result.output as Record<string, unknown>;
    const companyDomain = String(
      output.domain || output.company_domain || cumulativeContext.company_domain || cumulativeContext.domain || ""
    );
    if (companyDomain) {
      await internalPost(internalConfig, "/api/internal/gemini-icp-job-titles/upsert", {
        company_domain: companyDomain,
        company_name: output.company_name || cumulativeContext.company_name,
        company_description: output.company_description || cumulativeContext.description_raw || cumulativeContext.description,
        inferred_product: output.inferred_product,
        buyer_persona: output.buyer_persona,
        titles: output.titles,
        champion_titles: output.champion_titles,
        evaluator_titles: output.evaluator_titles,
        decision_maker_titles: output.decision_maker_titles,
        raw_response: output,
        source_submission_id: run.submission_id,
        source_pipeline_run_id: pipeline_run_id,
      });
      logger.info("Gemini ICP job titles persisted to dedicated table", {
        domain: companyDomain,
        pipeline_run_id,
      });
    }
  } catch (error) {
    logger.warn("Failed to persist Gemini ICP job titles to dedicated table", {
      pipeline_run_id,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}
```

**Important:** Both blocks follow the existing pattern — wrapped in try/catch, failure logs a warning but does NOT fail the pipeline step. This is the same design decision from the ICP auto-persist incident (see `docs/troubleshooting-fixes/2026-02-25_icp_auto_persist_not_writing.md`).

Commit standalone with message: `add auto-persist wiring for company_customers and gemini_icp_job_titles in pipeline runner`

---

## Deliverable 9: Query Endpoints (Tenant-Facing)

**File:** `app/routers/entities_v1.py`

Add two query endpoints following the existing pattern of `/api/v1/icp-job-titles/query`:

### 9a: `POST /api/v1/company-customers/query`

Request body: `company_domain` (optional), `company_entity_id` (optional), `limit` (default 100), `offset` (default 0).

Calls `query_company_customers` from `app.services.company_customers`. Uses tenant auth (existing `resolve_auth_context` dependency). Scoped by `org_id`.

### 9b: `POST /api/v1/gemini-icp-job-titles/query`

Request body: `company_domain` (optional), `limit` (default 100), `offset` (default 0).

Calls `query_gemini_icp_job_titles` from `app.services.gemini_icp_job_titles`. Uses tenant auth. Scoped by `org_id`.

Commit standalone with message: `add tenant query endpoints for company_customers and gemini_icp_job_titles`

---

## Deliverable 10: Update Documentation

### File: `CLAUDE.md`

Add to the API Endpoints section:
```
- `POST /api/v1/company-customers/query`
- `POST /api/v1/gemini-icp-job-titles/query`
- `POST /api/internal/company-customers/upsert`
- `POST /api/internal/gemini-icp-job-titles/upsert`
```

Add to Database / Migrations:
```
18. `018_alumnigtm_persistence.sql`
```

### File: `docs/SYSTEM_OVERVIEW.md`

Update Infrastructure Features table with the new tables. Update migration table.

Commit standalone with message: `update documentation for AlumniGTM persistence layer`

---

## What is NOT in scope

- No new operations (those are separate directives)
- No changes to the existing `icp_job_titles` table or service
- No changes to the existing Parallel.ai auto-persist blocks
- No deploy commands
- Do NOT run the migration — the chief agent runs migrations after review
- No changes to the existing entity state upsert for person_entities or job_posting_entities

## Prerequisites for testing

The migration must be run before the new services/endpoints can be tested against the database. The executor should write the code assuming the migration has been applied. The chief agent will run the migration separately.

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file name and list of schema changes (columns + tables)
(b) New columns added to `_company_fields_from_context` and their context field aliases
(c) New columns added to `upsert_company_entity` row_to_write
(d) `company_customers` service — upsert function signature, dedup key, query function signature
(e) `gemini_icp_job_titles` service — upsert function signature, dedup key, query function signature
(f) Internal endpoint paths and request model field lists
(g) Auto-persist operation_id triggers in run-pipeline.ts
(h) Tenant query endpoint paths
(i) Anything to flag
