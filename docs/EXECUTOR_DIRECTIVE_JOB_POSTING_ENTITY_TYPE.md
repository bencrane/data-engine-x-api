# Directive: Job Posting Entity Type

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The system currently supports two entity types: `company` and `person`. We are adding `job` as a third entity type for job postings. This supports a staffing agency product where we search for job postings (via TheirStack), enrich the companies posting them, find hiring contacts, and track whether postings are still active. Job posting entities follow the exact same patterns as company and person entities: org-scoped, UUIDv5 identity resolution, additive upserts, snapshots, timeline, and canonical payload.

---

## Existing code to read before starting:

- `supabase/migrations/007_entity_state.sql` — `company_entities` and `person_entities` table definitions (follow this pattern exactly)
- `supabase/migrations/009_entity_timeline.sql` — `entity_timeline` table with CHECK constraint to update
- `supabase/migrations/012_entity_snapshots.sql` — `entity_snapshots` table with CHECK constraint to update
- `app/services/entity_state.py` — `resolve_company_entity_id`, `upsert_company_entity`, `upsert_person_entity`, `check_entity_freshness`, `_company_fields_from_context`, all helper functions
- `app/services/entity_timeline.py` — `record_entity_event`
- `app/routers/entities_v1.py` — entity query endpoints (companies, persons, timeline)
- `app/routers/internal.py` — internal entity-state upsert endpoint
- `trigger/src/tasks/run-pipeline.ts` — `entityTypeFromOperationId` function, entity type TypeScript types
- `app/contracts/theirstack.py` — `TheirStackJobItem` model (the canonical output from `job.search`)

---

## Deliverable 1: SQL Migration — `job_posting_entities` Table + ALTER Constraints

**File:** `supabase/migrations/013_job_posting_entities.sql`

### Create `job_posting_entities` table

Follow the exact pattern of `company_entities` from migration 007. Same structure: `org_id` + `entity_id` composite PK, `record_version`, `canonical_payload` JSONB, timestamps, triggers.

```sql
CREATE TABLE IF NOT EXISTS job_posting_entities (
    org_id                  UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
    company_id              UUID REFERENCES companies(id) ON DELETE SET NULL,
    entity_id               UUID NOT NULL,

    -- Identity
    theirstack_job_id       BIGINT,
    job_url                 TEXT,

    -- Core fields
    job_title               TEXT,
    normalized_title        TEXT,
    company_name            TEXT,
    company_domain          TEXT,

    -- Location
    location                TEXT,
    short_location          TEXT,
    state_code              TEXT,
    country_code            TEXT,
    remote                  BOOLEAN,
    hybrid                  BOOLEAN,

    -- Job attributes
    seniority               TEXT,
    employment_statuses     TEXT[],
    date_posted             TEXT,
    discovered_at           TEXT,

    -- Salary
    salary_string           TEXT,
    min_annual_salary_usd   DOUBLE PRECISION,
    max_annual_salary_usd   DOUBLE PRECISION,

    -- Content
    description             TEXT,
    technology_slugs        TEXT[],
    hiring_team             JSONB,

    -- Lifecycle
    posting_status          TEXT DEFAULT 'active' CHECK (posting_status IN ('active', 'likely_closed', 'confirmed_closed')),

    -- Enrichment tracking (same as company/person)
    enrichment_confidence   NUMERIC,
    last_enriched_at        TIMESTAMPTZ,
    last_operation_id       TEXT,
    last_run_id             UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    source_providers        TEXT[],
    record_version          BIGINT NOT NULL DEFAULT 1 CHECK (record_version > 0),
    canonical_payload       JSONB,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT pk_job_posting_entities PRIMARY KEY (org_id, entity_id)
);
```

### Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_theirstack_id
    ON job_posting_entities(org_id, theirstack_job_id);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_domain
    ON job_posting_entities(org_id, company_domain);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_name
    ON job_posting_entities(org_id, company_name);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_job_title
    ON job_posting_entities(org_id, job_title);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_posting_status
    ON job_posting_entities(org_id, posting_status);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_country_code
    ON job_posting_entities(org_id, country_code);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_seniority
    ON job_posting_entities(org_id, seniority);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_company_id
    ON job_posting_entities(org_id, company_id);
CREATE INDEX IF NOT EXISTS idx_job_posting_entities_org_remote
    ON job_posting_entities(org_id, remote);
```

### Updated `updated_at` trigger

```sql
DROP TRIGGER IF EXISTS update_job_posting_entities_updated_at ON job_posting_entities;
CREATE TRIGGER update_job_posting_entities_updated_at
    BEFORE UPDATE ON job_posting_entities
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

### RLS

```sql
ALTER TABLE job_posting_entities ENABLE ROW LEVEL SECURITY;
```

### ALTER existing CHECK constraints to allow 'job'

```sql
ALTER TABLE entity_timeline DROP CONSTRAINT IF EXISTS entity_timeline_entity_type_check;
ALTER TABLE entity_timeline ADD CONSTRAINT entity_timeline_entity_type_check
    CHECK (entity_type IN ('company', 'person', 'job'));

ALTER TABLE entity_snapshots DROP CONSTRAINT IF EXISTS entity_snapshots_entity_type_check;
ALTER TABLE entity_snapshots ADD CONSTRAINT entity_snapshots_entity_type_check
    CHECK (entity_type IN ('company', 'person', 'job'));
```

Commit standalone with message: `add job_posting_entities table and update entity type constraints for job postings`

---

## Deliverable 2: Entity State Service — Job Posting Identity Resolution + Upsert

**File:** `app/services/entity_state.py`

### Add `_job_posting_fields_from_context`:

Extract canonical job posting fields from the cumulative context. Map from the TheirStack output field names:

```python
def _job_posting_fields_from_context(canonical_fields: dict[str, Any]) -> dict[str, Any]:
    return {
        "theirstack_job_id": _normalize_int(
            canonical_fields.get("theirstack_job_id")
            or canonical_fields.get("job_id")
        ),
        "job_url": _normalize_text(
            canonical_fields.get("job_url")
            or canonical_fields.get("url")
        ),
        "job_title": _normalize_text(canonical_fields.get("job_title")),
        "normalized_title": _normalize_text(canonical_fields.get("normalized_title")),
        "company_name": _normalize_text(canonical_fields.get("company_name")),
        "company_domain": _normalize_domain(
            canonical_fields.get("company_domain")
            or canonical_fields.get("domain")
        ),
        "location": _normalize_text(
            canonical_fields.get("location")
            or canonical_fields.get("short_location")
        ),
        "short_location": _normalize_text(canonical_fields.get("short_location")),
        "state_code": _normalize_text(canonical_fields.get("state_code")),
        "country_code": _normalize_text(canonical_fields.get("country_code")),
        "remote": canonical_fields.get("remote") if isinstance(canonical_fields.get("remote"), bool) else None,
        "hybrid": canonical_fields.get("hybrid") if isinstance(canonical_fields.get("hybrid"), bool) else None,
        "seniority": _normalize_text(canonical_fields.get("seniority")),
        "employment_statuses": _extract_str_list(canonical_fields.get("employment_statuses")),
        "date_posted": _normalize_text(canonical_fields.get("date_posted")),
        "discovered_at": _normalize_text(canonical_fields.get("discovered_at")),
        "salary_string": _normalize_text(canonical_fields.get("salary_string")),
        "min_annual_salary_usd": _normalize_float(canonical_fields.get("min_annual_salary_usd")),
        "max_annual_salary_usd": _normalize_float(canonical_fields.get("max_annual_salary_usd")),
        "description": _normalize_text(canonical_fields.get("description")),
        "technology_slugs": _extract_str_list(canonical_fields.get("technology_slugs")),
        "source_providers": _extract_str_list(canonical_fields.get("source_providers")),
    }
```

Note: `hiring_team` is stored in `canonical_payload` JSONB, not as a structured column extraction. Same with `company_object`. The structured columns above are for indexing and querying.

### Add `resolve_job_posting_entity_id`:

Natural key priority: `theirstack_job_id` > `job_url` > fallback.

```python
def resolve_job_posting_entity_id(
    *,
    org_id: str,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
) -> str:
    explicit_entity_id = _as_uuid_str(entity_id)
    if explicit_entity_id:
        return explicit_entity_id

    normalized_fields = _job_posting_fields_from_context(canonical_fields)
    theirstack_job_id = normalized_fields.get("theirstack_job_id")
    job_url = normalized_fields.get("job_url")
    job_title = normalized_fields.get("job_title")
    company_domain = normalized_fields.get("company_domain")
    if theirstack_job_id:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:theirstack:{theirstack_job_id}"))
    if job_url:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:url:{job_url}"))
    if job_title and company_domain:
        return str(uuid5(NAMESPACE_URL, f"job:{org_id}:title_domain:{job_title.lower()}:{company_domain}"))
    return _stable_identity_fallback("job", org_id, canonical_fields)
```

### Add lookup helpers:

- `_lookup_job_posting_by_theirstack_id(org_id, theirstack_job_id)` — query `job_posting_entities` by `org_id` + `theirstack_job_id`
- `_load_job_posting_by_id(org_id, entity_id)` — query by `org_id` + `entity_id`

Follow the exact pattern of `_lookup_company_by_natural_key` and `_load_company_by_id`.

### Add `upsert_job_posting_entity`:

Follow the exact pattern of `upsert_company_entity`. Same signature shape:

```python
def upsert_job_posting_entity(
    *,
    org_id: str,
    company_id: str | None,
    canonical_fields: dict[str, Any],
    entity_id: str | None = None,
    last_operation_id: str | None = None,
    last_run_id: str | None = None,
    incoming_record_version: int | None = None,
) -> dict[str, Any]:
```

Logic (same as company/person):
1. Resolve entity_id via natural key lookup or `resolve_job_posting_entity_id`
2. Load existing record if any
3. Version check (incoming > existing)
4. Capture entity snapshot of existing state before update
5. Merge non-null fields
6. Write row (insert or update with optimistic concurrency on `record_version`)

The `row_to_write` dict should include all structured columns from `_job_posting_fields_from_context` plus `posting_status` (default "active" on insert, preserve existing on update unless explicitly set), `hiring_team` (from `canonical_fields.get("hiring_team")` stored as JSONB), and all standard fields (`org_id`, `company_id`, `entity_id`, `last_enriched_at`, `last_operation_id`, `last_run_id`, `source_providers`, `record_version`, `canonical_payload`).

### Update `check_entity_freshness`:

Add a `"job"` branch alongside the existing `"person"` and default (company) branches:

```python
elif entity_type == "job":
    theirstack_job_id = _normalize_int(
        normalized_identifiers.get("theirstack_job_id")
        or normalized_identifiers.get("job_id")
    )
    if not theirstack_job_id:
        return {"fresh": False, "entity_id": None}
    entity = _lookup_job_posting_by_theirstack_id(org_id, theirstack_job_id)
```

Commit standalone with message: `add job posting entity state resolution, upsert, and freshness check`

---

## Deliverable 3: Internal Upsert Endpoint — Handle `job` Entity Type

**File:** `app/routers/internal.py`

Find the internal entity-state upsert handler (the endpoint at `/api/internal/entity-state/upsert`). It currently dispatches to `upsert_company_entity` or `upsert_person_entity` based on `entity_type`.

Add a branch for `entity_type == "job"`:

```python
elif entity_type == "job":
    result = upsert_job_posting_entity(
        org_id=org_id,
        company_id=company_id,
        canonical_fields=cumulative_context,
        last_operation_id=last_operation_id,
        last_run_id=pipeline_run_id,
    )
```

Import `upsert_job_posting_entity` from `app.services.entity_state`.

Commit standalone with message: `wire job posting entity upsert into internal endpoint`

---

## Deliverable 4: Pipeline Runner — Add `job` Entity Type

**File:** `trigger/src/tasks/run-pipeline.ts`

### Update `entityTypeFromOperationId`:

Current (line ~207):
```typescript
function entityTypeFromOperationId(operationId: string): "person" | "company" {
  if (operationId.startsWith("person.")) return "person";
  return "company";
}
```

Change to:
```typescript
function entityTypeFromOperationId(operationId: string): "person" | "company" | "job" {
  if (operationId.startsWith("person.")) return "person";
  if (operationId.startsWith("job.")) return "job";
  return "company";
}
```

### Update all TypeScript type annotations

Search for `"person" | "company"` throughout the file. Every occurrence must become `"person" | "company" | "job"`. This includes:
- The `entity` type in the blueprint snapshot interface (~line 29)
- The `entityType` parameter in `callExecuteOperation` (~line 150)
- The `entityType` parameter in `callEntityStateFreshnessCheck` (~line 182)
- The `entityType` in the `recordStepTimelineEvent` parameters (~line 305)
- Any other occurrences

Commit standalone with message: `add job entity type to pipeline runner entity type derivation`

---

## Deliverable 5: Entity Query Endpoint — Job Postings

**File:** `app/routers/entities_v1.py`

### Add `JobPostingEntitiesListRequest`:

```python
class JobPostingEntitiesListRequest(BaseModel):
    company_id: str | None = None
    company_domain: str | None = None
    company_name: str | None = None
    job_title: str | None = None
    seniority: str | None = None
    country_code: str | None = None
    remote: bool | None = None
    posting_status: str | None = None
    page: int = Field(default=1, ge=1)
    per_page: int = Field(default=25, ge=1, le=100)
```

### Add `POST /api/v1/entities/job-postings` endpoint:

Follow the exact pattern of the existing `POST /api/v1/entities/companies` endpoint. Query `job_posting_entities` table with optional filters. Support both tenant auth and super-admin auth (via `_resolve_flexible_auth`). Paginate with `page` / `per_page`.

Apply filters:
- `company_id` → `.eq("company_id", ...)`
- `company_domain` → `.eq("company_domain", ...)`
- `company_name` → `.ilike("company_name", f"%{...}%")`
- `job_title` → `.ilike("job_title", f"%{...}%")`
- `seniority` → `.eq("seniority", ...)`
- `country_code` → `.eq("country_code", ...)`
- `remote` → `.eq("remote", ...)`
- `posting_status` → `.eq("posting_status", ...)`

Order by `created_at DESC`.

### Register in SUPPORTED paths:

Make sure the endpoint is accessible. Follow the exact import/registration pattern of the existing entity endpoints.

Commit standalone with message: `add job posting entity query endpoint`

---

## Deliverable 6: Tests

**File:** `tests/test_job_posting_entity.py` (new file)

### Required test cases:

**Identity resolution:**
1. `test_resolve_job_posting_entity_id_by_theirstack_id` — verify UUIDv5 from theirstack_job_id
2. `test_resolve_job_posting_entity_id_by_url` — fallback when no theirstack_job_id
3. `test_resolve_job_posting_entity_id_by_title_domain` — fallback when no URL
4. `test_resolve_job_posting_entity_id_deterministic` — same inputs produce same entity_id

**Field extraction:**
5. `test_job_posting_fields_from_context_full` — verify all fields extracted correctly
6. `test_job_posting_fields_from_context_minimal` — verify graceful handling of sparse input
7. `test_job_posting_fields_boolean_handling` — verify `remote` and `hybrid` booleans preserved correctly (not coerced from None)

**Entity type derivation (if testable without full Trigger setup):**
8. `test_entity_type_from_job_operation_id` — verify "job.search" → "job" (may need to be a note if Trigger code isn't directly testable from Python)

Mock all database calls. Follow the test patterns in existing entity tests.

Commit standalone with message: `add tests for job posting entity identity resolution and field extraction`

---

## What is NOT in scope

- No Bright Data integration or cross-source matching logic
- No changes to `job.search` operation or TheirStack adapter
- No changes to existing `company_entities` or `person_entities` behavior
- No deploy commands (no `git push`, no `trigger deploy`, no migration execution)
- No changes to `app/registry/operations.yaml`

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) `job_posting_entities` column count and column names
(b) Index list
(c) Entity ID resolution natural key priority chain
(d) `check_entity_freshness` — what identifier is used for job freshness lookup
(e) TypeScript type changes in run-pipeline.ts (list every location changed)
(f) Entity query endpoint path and supported filters
(g) Test count and names
(h) Anything to flag — especially any existing code that assumes only "company" | "person" that you found but is NOT in scope to change
