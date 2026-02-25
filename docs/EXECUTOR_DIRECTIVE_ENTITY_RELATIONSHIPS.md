# Directive: Entity Relationships Table + Service + Endpoints

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need a foundational table that records typed, directional relationships between entities (companies and persons). Examples: "securitypal.com has_customer snap.com", "linkedin.com/in/jhiggins works_at coreweave.com", "coreweave.com has_competitor aws.amazon.com". This enables flat SQL queries for dashboard assembly, lead magnet generation, and GTM briefing construction — replacing the current need to walk pipeline run trees and parse step results. One table, many relationship types (not a closed enum — new types are just new string values, no migration needed).

---

## Existing code to read before starting

- `supabase/migrations/013_job_posting_entities.sql` — reference pattern for a migration with table, indexes, RLS, updated_at trigger, CHECK constraints
- `app/services/entity_state.py` — reference pattern for a service that upserts entities with dedup logic
- `app/services/entity_timeline.py` — reference pattern for a simple record-writing service
- `app/routers/internal.py` — where internal endpoints live (pipeline runner → FastAPI). Add new endpoints here.
- `app/routers/entities_v1.py` — where tenant entity query endpoints live. Add the query endpoint here.
- `app/routers/_responses.py` — `DataEnvelope`, `ErrorEnvelope`, `error_response` helpers
- `app/database.py` — `get_supabase_client()`
- `app/config.py` — `get_settings()`

---

## Deliverable 1: Migration

**File:** `supabase/migrations/014_entity_relationships.sql` (new file)

```sql
-- 014_entity_relationships.sql
-- Typed, directional relationships between entities (companies and persons).

CREATE TABLE IF NOT EXISTS entity_relationships (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,

    -- Source entity
    source_entity_type TEXT NOT NULL CHECK (source_entity_type IN ('company', 'person')),
    source_entity_id UUID,
    source_identifier TEXT NOT NULL,

    -- Relationship
    relationship TEXT NOT NULL,

    -- Target entity
    target_entity_type TEXT NOT NULL CHECK (target_entity_type IN ('company', 'person')),
    target_entity_id UUID,
    target_identifier TEXT NOT NULL,

    -- Context
    metadata JSONB DEFAULT '{}',
    source_submission_id UUID REFERENCES submissions(id) ON DELETE SET NULL,
    source_pipeline_run_id UUID REFERENCES pipeline_runs(id) ON DELETE SET NULL,
    source_operation_id TEXT,

    -- Lifecycle
    valid_as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    invalidated_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup constraint: same relationship between same entities is recorded once
CREATE UNIQUE INDEX IF NOT EXISTS idx_entity_relationships_dedup
    ON entity_relationships(org_id, source_identifier, relationship, target_identifier);

-- Query patterns
CREATE INDEX IF NOT EXISTS idx_entity_relationships_source
    ON entity_relationships(org_id, source_identifier, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_target
    ON entity_relationships(org_id, target_identifier, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_type
    ON entity_relationships(org_id, relationship);
CREATE INDEX IF NOT EXISTS idx_entity_relationships_submission
    ON entity_relationships(org_id, source_submission_id);

DROP TRIGGER IF EXISTS update_entity_relationships_updated_at ON entity_relationships;
CREATE TRIGGER update_entity_relationships_updated_at
    BEFORE UPDATE ON entity_relationships
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

ALTER TABLE entity_relationships ENABLE ROW LEVEL SECURITY;
```

Copy this SQL exactly. Do not modify the schema.

Commit standalone with message: `add 014_entity_relationships migration for typed directional entity relationships`

---

## Deliverable 2: Service Layer

**File:** `app/services/entity_relationships.py` (new file)

Create the following functions:

### `record_entity_relationship`

```python
def record_entity_relationship(
    *,
    org_id: str,
    source_entity_type: str,
    source_identifier: str,
    relationship: str,
    target_entity_type: str,
    target_identifier: str,
    source_entity_id: str | None = None,
    target_entity_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
    source_operation_id: str | None = None,
) -> dict[str, Any]:
```

**Logic:**
1. Normalize `source_identifier` and `target_identifier` — strip whitespace, lowercase. For domains, strip protocol/www. For LinkedIn URLs, strip trailing slash, lowercase.
2. Attempt upsert using Supabase's `.upsert()` with `on_conflict="org_id,source_identifier,relationship,target_identifier"`.
3. On upsert (existing row), update: `valid_as_of` to NOW(), `metadata` to the new value (if provided), `source_submission_id`, `source_pipeline_run_id`, `source_operation_id`, `invalidated_at` to NULL (re-validates a previously invalidated relationship), `updated_at` to NOW().
4. On insert (new row), write all fields.
5. Return the upserted row.

### `record_entity_relationships_batch`

```python
def record_entity_relationships_batch(
    *,
    org_id: str,
    relationships: list[dict[str, Any]],
) -> list[dict[str, Any]]:
```

**Logic:** Iterate and call `record_entity_relationship` for each item. Each item in the list is a dict with the same fields as `record_entity_relationship` (minus `org_id` which is shared). Return list of upserted rows. If any individual upsert fails, log the error and continue — do not fail the batch.

### `invalidate_entity_relationship`

```python
def invalidate_entity_relationship(
    *,
    org_id: str,
    source_identifier: str,
    relationship: str,
    target_identifier: str,
) -> dict[str, Any] | None:
```

**Logic:** Find the row by `(org_id, source_identifier, relationship, target_identifier)`. Set `invalidated_at` to NOW(). Return the updated row, or None if not found.

### `query_entity_relationships`

```python
def query_entity_relationships(
    *,
    org_id: str,
    source_identifier: str | None = None,
    target_identifier: str | None = None,
    relationship: str | None = None,
    source_entity_type: str | None = None,
    target_entity_type: str | None = None,
    include_invalidated: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
```

**Logic:**
1. Build a Supabase query on `entity_relationships` filtered by `org_id`.
2. Apply optional filters: `source_identifier`, `target_identifier`, `relationship`, `source_entity_type`, `target_entity_type`.
3. If `include_invalidated` is False (default), filter to `invalidated_at IS NULL`.
4. Order by `created_at` descending.
5. Apply `limit` and `offset`.
6. Return list of rows.

Normalize identifier inputs (same normalization as `record_entity_relationship`) before querying.

Commit standalone with message: `add entity_relationships service with record, batch, invalidate, and query functions`

---

## Deliverable 3: Internal Endpoints

**File:** `app/routers/internal.py`

Add three new endpoints. Import the service functions from `app.services.entity_relationships`.

### `POST /api/internal/entity-relationships/record`

**Request body:**
```python
class InternalRecordEntityRelationshipRequest(BaseModel):
    source_entity_type: str
    source_identifier: str
    relationship: str
    target_entity_type: str
    target_identifier: str
    source_entity_id: str | None = None
    target_entity_id: str | None = None
    metadata: dict[str, Any] | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
    source_operation_id: str | None = None
```

**Logic:** Extract `org_id` from internal auth headers (`x-internal-org-id`). Call `record_entity_relationship`. Return `DataEnvelope(data=result)`.

### `POST /api/internal/entity-relationships/record-batch`

**Request body:**
```python
class InternalRecordEntityRelationshipsBatchRequest(BaseModel):
    relationships: list[dict[str, Any]]
```

**Logic:** Extract `org_id` from internal auth headers. Call `record_entity_relationships_batch`. Return `DataEnvelope(data=results)`.

### `POST /api/internal/entity-relationships/invalidate`

**Request body:**
```python
class InternalInvalidateEntityRelationshipRequest(BaseModel):
    source_identifier: str
    relationship: str
    target_identifier: str
```

**Logic:** Extract `org_id` from internal auth headers. Call `invalidate_entity_relationship`. Return `DataEnvelope(data=result)` or 404 if not found.

All three endpoints use `Depends(require_internal_key)` for auth — same as existing internal endpoints.

Commit standalone with message: `add internal endpoints for recording, batch recording, and invalidating entity relationships`

---

## Deliverable 4: Query Endpoint

**File:** `app/routers/entities_v1.py`

Add one new endpoint:

### `POST /api/v1/entity-relationships/query`

**Request body:**
```python
class EntityRelationshipQueryRequest(BaseModel):
    source_identifier: str | None = None
    target_identifier: str | None = None
    relationship: str | None = None
    source_entity_type: str | None = None
    target_entity_type: str | None = None
    include_invalidated: bool = False
    limit: int = 100
    offset: int = 0
```

**Auth:** Uses the same flexible auth as other entity endpoints in this file (`_resolve_flexible_auth`). For tenant auth, scope by org_id from auth context. For super-admin auth, require `org_id` in the request body (add as optional field).

**Logic:** Call `query_entity_relationships` with the auth-resolved `org_id` and all filter params. Return `DataEnvelope(data=results)`.

Commit standalone with message: `add entity relationships query endpoint for dashboard and API consumers`

---

## Deliverable 5: Tests

**File:** `tests/test_entity_relationships.py` (new file)

### Required test cases:

1. `test_record_entity_relationship_creates_new` — record a new relationship, verify it returns with all fields populated.
2. `test_record_entity_relationship_dedup_updates` — record the same relationship twice. Second call should update `valid_as_of` and `metadata` rather than creating a duplicate.
3. `test_record_entity_relationship_normalizes_identifiers` — verify domain identifiers are normalized (strip protocol, www, trailing slash, lowercase). E.g., `https://www.CoreWeave.com/` becomes `coreweave.com`.
4. `test_invalidate_entity_relationship` — record a relationship, invalidate it, verify `invalidated_at` is set.
5. `test_invalidate_revalidates_on_re_record` — record, invalidate, then record again. Verify `invalidated_at` is set back to NULL.
6. `test_query_filters_by_source` — record 3 relationships with different sources. Query by one source, verify only that source's relationships are returned.
7. `test_query_filters_by_relationship_type` — record `has_customer` and `has_competitor` for the same source. Query by `has_customer`, verify only customers returned.
8. `test_query_excludes_invalidated_by_default` — record and invalidate a relationship. Default query should not return it. Query with `include_invalidated=True` should return it.
9. `test_batch_record` — batch record 5 relationships. Verify all 5 are created.

Mock all database calls. Use realistic data: SecurityPal, CoreWeave, Snap, AWS, LinkedIn URLs.

Commit standalone with message: `add tests for entity relationships service and endpoints`

---

## Deliverable 6: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add a new section after the Entity Snapshots / Change Detection section:

```
### Entity Relationships

The `entity_relationships` table records typed, directional relationships between entities. Each relationship has a source entity (identified by domain or LinkedIn URL), a relationship type (e.g., `has_customer`, `has_competitor`, `works_at`, `alumni_of`), and a target entity. Relationships are org-scoped, deduplicated on (source, relationship, target), and support invalidation for time-bounded facts like employment.

Internal endpoints: `/api/internal/entity-relationships/record`, `/record-batch`, `/invalidate`.
Query endpoint: `/api/v1/entity-relationships/query`.
```

Add these endpoints to the API endpoint list in both `docs/SYSTEM_OVERVIEW.md` and `CLAUDE.md`:

```
- `POST /api/internal/entity-relationships/record`
- `POST /api/internal/entity-relationships/record-batch`
- `POST /api/internal/entity-relationships/invalidate`
- `POST /api/v1/entity-relationships/query`
```

Also add to the Infrastructure Features table:
```
| Entity relationships (typed, directional, deduped) | ✅ Live |
```

### File: `CLAUDE.md`

Add the 4 new endpoints to the API Endpoints list.

Commit standalone with message: `update documentation for entity relationships table and endpoints`

---

## What is NOT in scope

- No changes to existing entity tables (`company_entities`, `person_entities`, `job_posting_entities`)
- No changes to the pipeline runner (`run-pipeline.ts`) — relationship recording will be wired later
- No automatic relationship discovery from existing step results (backfill is separate)
- No graph query support (traversals like "targets of targets") — flat queries only
- No UI/dashboard
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Migration file path and table name
(b) Service function signatures (all 4)
(c) Internal endpoint paths and request body fields
(d) Query endpoint path, auth model, and supported filters
(e) Dedup constraint fields
(f) Normalization logic applied to identifiers (what gets stripped/lowercased)
(g) Test count and names
(h) Anything to flag
