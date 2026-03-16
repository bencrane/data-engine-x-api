**Directive: Backfill `entity_relationships` with `works_at` Edges + Leads Query Endpoint**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The `entity_relationships` table exists in production (migration `014_entity_relationships.sql`) but has 0 rows. Meanwhile, `person_entities` has 503 rows and `company_entities` has 88 rows — both populated with canonical data. The connection between a person and their employer company exists implicitly inside the `canonical_payload` JSONB on person records (fields like `current_company_domain`, `company_domain`, `current_company_name`, `company_name`, `current_company_linkedin_url`, `company_linkedin_url`), but there is no structured link between the two entity tables. This directive creates that link via a backfill script, then builds a leads query endpoint that joins persons + relationships + companies into a flat, filterable response for OEX campaign enrollment.

**Existing code to read:**

- `CLAUDE.md` — project conventions, auth model, API surface
- `supabase/migrations/007_entity_state.sql` — `company_entities` and `person_entities` schemas
- `supabase/migrations/014_entity_relationships.sql` — `entity_relationships` schema (source/target identifiers, relationship type, dedup constraint, lifecycle columns)
- `app/services/entity_relationships.py` — `record_entity_relationship()`, `query_entity_relationships()`, normalization helpers. **Use `record_entity_relationship` for writes; do not write raw SQL inserts.**
- `app/services/entity_state.py` — `_person_fields_from_context()` (shows what gets extracted to top-level columns vs what stays only in `canonical_payload`), `_normalize_domain()`, `_normalize_linkedin_url()`, `resolve_company_entity_id()`, `resolve_person_entity_id()`
- `app/routers/entities_v1.py` — existing entity query endpoints (companies, persons, job-postings, entity-relationships). **Follow the same auth pattern (`_resolve_flexible_auth`), pagination style, and `DataEnvelope` response shape.**
- `app/routers/_responses.py` — `DataEnvelope`, `ErrorEnvelope`, `error_response` helpers
- `app/main.py` — router registration (see how `entity_relationships_router` is mounted at `/api/v1`)
- `scripts/backfill_icp_job_titles.py` — reference pattern for backfill scripts (repo-root path insertion, Supabase client usage, Doppler-injected env)
- `app/database.py` — `get_supabase_client()`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md` — entity schema doctrine (especially Principle 9: relationships are first-class)

---

### Deliverable 1: Backfill Script — Extract `works_at` Edges from Person Entities

Create `scripts/backfill_entity_relationships.py`.

**What it does:**

1. Fetch all rows from `person_entities` (paginate if needed — there are 503 rows currently, but design for growth).
2. For each person record, extract the employer company identifier from `canonical_payload`. Check these keys in priority order:
   - `current_company_domain` or `company_domain` — normalize with domain normalization (strip protocol, www, trailing slash, lowercase)
   - `current_company_linkedin_url` or `company_linkedin_url` — normalize with LinkedIn URL normalization
   - `current_company_name` or `company_name` — use as fallback identifier only if no domain or LinkedIn URL is available
3. Skip the person if no company identifier can be extracted.
4. Attempt to match against `company_entities` in the same `org_id`:
   - First: match on `canonical_domain` (if domain was extracted)
   - Second: match on `linkedin_url` (if LinkedIn URL was extracted)
   - If a match is found, capture the `entity_id` of the matched company as `target_entity_id`.
   - If no match is found, still create the relationship row — use the best available identifier as `target_identifier` and leave `target_entity_id` as `None`. The relationship is still valuable for the leads query even without a resolved company entity.
5. Call `record_entity_relationship()` from `app/services/entity_relationships.py` for each edge:
   - `source_entity_type`: `"person"`
   - `source_entity_id`: the person's `entity_id`
   - `source_identifier`: the person's `linkedin_url` (preferred) or `work_email` (fallback) — must be a non-null unique person identifier
   - `relationship`: `"works_at"`
   - `target_entity_type`: `"company"`
   - `target_entity_id`: the matched company's `entity_id` (or `None` if unresolved)
   - `target_identifier`: the normalized company domain (preferred), LinkedIn URL (second), or company name (fallback)
   - `metadata`: include `{"source": "backfill", "extracted_from": "canonical_payload"}` plus any additional company fields extracted (e.g., `company_name` if the identifier used was domain)
   - `source_operation_id`: `"backfill.entity_relationships.works_at"`
6. Print summary stats: total persons processed, relationships created, skipped (no company identifier), matched (with `target_entity_id`), unmatched (relationship created but no company entity found).

**Run convention:** `doppler run -- python scripts/backfill_entity_relationships.py`

**Idempotency:** The `record_entity_relationship` function uses upsert on the dedup constraint `(org_id, source_identifier, relationship, target_identifier)`. Running the script twice produces the same result.

Commit standalone.

---

### Deliverable 2: Leads Query Service Function

Create `app/services/leads_query.py`.

**What it does:**

Implement `query_leads(*, org_id, filters, limit, offset) -> dict` that returns a flat list of lead records by joining `person_entities` + `entity_relationships` + `company_entities`.

**Query logic:**

1. Start from `entity_relationships` where `org_id` matches, `relationship = 'works_at'`, `source_entity_type = 'person'`, `target_entity_type = 'company'`, and `invalidated_at IS NULL`.
2. Join `person_entities` on `(org_id, entity_id) = (org_id, source_entity_id)`.
3. Join `company_entities` on `(org_id, entity_id) = (org_id, target_entity_id)`. Use a LEFT JOIN so that relationships without a resolved company entity are still returned (company fields will be null).
4. Apply filters (all optional, combine with AND):
   - **Company-level:** `industry` (ILIKE partial match), `employee_range` (exact), `hq_country` (exact), `canonical_domain` (exact, normalized), `canonical_name` (ILIKE partial match)
   - **Person-level:** `title` (ILIKE partial match), `seniority` (exact), `department` (ILIKE partial match), `email_status` (exact), `has_email` (boolean — filters to `work_email IS NOT NULL` when true), `has_phone` (boolean — filters to `phone_e164 IS NOT NULL` when true)
5. Return shape per lead:

```
{
  "person_entity_id": ...,
  "full_name": ...,
  "first_name": ...,
  "last_name": ...,
  "linkedin_url": ...,
  "title": ...,
  "seniority": ...,
  "department": ...,
  "work_email": ...,
  "email_status": ...,
  "phone_e164": ...,
  "contact_confidence": ...,
  "person_last_enriched_at": ...,
  "company_entity_id": ...,       # null if unresolved
  "company_domain": ...,           # null if unresolved
  "company_name": ...,             # null if unresolved
  "company_linkedin_url": ...,     # null if unresolved
  "company_industry": ...,         # null if unresolved
  "company_employee_count": ...,   # null if unresolved
  "company_employee_range": ...,   # null if unresolved
  "company_revenue_band": ...,     # null if unresolved
  "company_hq_country": ...,       # null if unresolved
  "relationship_id": ...,
  "relationship_valid_as_of": ...
}
```

6. Order by `person_entities.updated_at DESC`.
7. Paginate with `limit` / `offset`.
8. Return `{"items": [...], "total_matched": <count>, "limit": ..., "offset": ...}`.

**Implementation approach:** The Supabase PostgREST client does not natively support multi-table joins with filters across tables. Use `get_supabase_client()` to get the client, then call `client.rpc(...)` against a Postgres function that performs the join. The Postgres function is created in Deliverable 3.

Commit standalone.

---

### Deliverable 3: Migration — Leads Query Postgres Function

Create `supabase/migrations/028_leads_query_function.sql`.

**What it does:**

Create a Postgres function `query_leads(...)` that performs the three-table join described in Deliverable 2. The function should:

1. Accept parameters: `p_org_id UUID`, plus all optional filter parameters (use `NULL` defaults for optional filters), plus `p_limit INT DEFAULT 25`, `p_offset INT DEFAULT 0`.
2. Perform the join: `entity_relationships er JOIN person_entities pe ON (er.org_id = pe.org_id AND er.source_entity_id = pe.entity_id) LEFT JOIN company_entities ce ON (er.org_id = ce.org_id AND er.target_entity_id = ce.entity_id)`.
3. Apply WHERE clause: `er.org_id = p_org_id AND er.relationship = 'works_at' AND er.source_entity_type = 'person' AND er.target_entity_type = 'company' AND er.invalidated_at IS NULL`.
4. Apply optional filters using `AND (p_filter IS NULL OR ...)` pattern.
5. Return `SETOF JSON` — each row as a JSON object with the flat shape from Deliverable 2.
6. Include a companion function or a count query approach so that `total_matched` can be returned without a second round-trip. One pragmatic approach: return the count as a field in each row (`total_matched`), computed via a window function (`COUNT(*) OVER()`). The service layer reads it from the first row and strips it from the response items.

**Naming:** The migration number is `028`. Check that no other migration uses this number — if it conflicts, use the next available number.

Commit standalone.

---

### Deliverable 4: Leads Query API Endpoint

Add the endpoint to `app/routers/entities_v1.py`.

**Endpoint:** `POST /api/v1/leads/query`

**Request model** (add to `entities_v1.py`):

```python
class LeadsQueryRequest(BaseModel):
    # Company filters
    industry: str | None = None
    employee_range: str | None = None
    hq_country: str | None = None
    canonical_domain: str | None = None
    company_name: str | None = None
    # Person filters
    title: str | None = None
    seniority: str | None = None
    department: str | None = None
    email_status: str | None = None
    has_email: bool | None = None
    has_phone: bool | None = None
    # Pagination
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    # Super-admin override
    org_id: str | None = None
```

**Auth:** Use the `_resolve_flexible_auth` pattern (supports both tenant auth and super-admin). Tenant auth scopes to `auth.org_id`. Super-admin can pass `org_id` in the request body.

**Response:** Standard `DataEnvelope` wrapping the result from `query_leads()`.

**Router registration:** This is a new route prefix. Add a new router instance in `entities_v1.py` (e.g., `leads_router = APIRouter()`) and register it in `app/main.py` at prefix `/api/v1`. Alternatively, if it fits cleanly on the existing `entity_relationships_router`, use that — but only if it doesn't create naming confusion. Use your judgment.

Commit standalone.

---

### Deliverable 5: Tests

Create `tests/test_leads_query.py`.

Test cases (mock all DB calls):

1. **Basic join returns flat lead shape** — mock the RPC call to return a sample row, verify the response matches the expected flat shape with both person and company fields.
2. **Unresolved company returns nulls** — mock a row where `target_entity_id` is null, verify company fields are null but person fields are populated.
3. **Filters are passed through** — verify that when filters are provided in the request, they are forwarded to the service function / RPC call correctly.
4. **Auth scoping** — verify that tenant auth uses `auth.org_id`, not the request body `org_id`.
5. **Super-admin org_id override** — verify that super-admin auth uses the request body `org_id`.
6. **Pagination** — verify limit/offset are respected.
7. **Empty result** — verify graceful empty response when no leads match.

Commit standalone.

---

**What is NOT in scope:**

- No changes to `run-pipeline.ts` or any Trigger.dev task files.
- No changes to existing entity upsert logic or existing endpoints.
- No deploy commands.
- No changes to the entity_relationships internal write endpoints (`/api/internal/entity-relationships/*`).
- No forward-looking auto-persist wiring (this directive backfills historical data and adds a query endpoint; future pipeline runs that create `works_at` edges at enrichment time are a separate concern).
- No schema changes to `person_entities` or `company_entities`.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with:
(a) Backfill script: how many company-identifier extraction paths are implemented and the priority order.
(b) Migration: the exact function signature and return type of the Postgres function.
(c) Leads endpoint: the full request model fields and the route path.
(d) Test count and what each test covers.
(e) Any ambiguities encountered in the `canonical_payload` field names — did you find person records where none of the expected company fields were present?
(f) Anything to flag.
