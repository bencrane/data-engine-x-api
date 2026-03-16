**Directive: Bulk Entity Ingest Endpoint for Externally-Sourced Data**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** data-engine-x currently has no way to ingest pre-enriched entity data from external sources. The only entity upsert path (`POST /api/internal/entity-state/upsert`) is internal-only, requires a valid `pipeline_run_id` referencing a succeeded pipeline run, and is coupled to the orchestration layer. We need a tenant/super-admin-facing bulk ingest endpoint that accepts raw payloads from external tools — starting with Clay — and writes them into `company_entities` and `person_entities` using the existing upsert and identity-resolution logic. For person records, the endpoint must auto-create `works_at` relationship edges between the person and their employer company.

**Source payload samples:**

Two Clay payload samples are provided for field mapping reference:

**Clay Find Companies sample** (`#A - User Inputs/clay-find-companies/sample-payload.json`):
```json
{
    "name": "Russell Tobin",
    "size": "201-500 employees",
    "type": "Privately Held",
    "domain": "russelltobin.com",
    "country": "United States",
    "industry": "Staffing and Recruiting",
    "location": "New York, New York",
    "industries": ["Staffing and Recruiting"],
    "description": "...",
    "linkedin_url": "https://www.linkedin.com/company/russell-tobin-&-associates-llc",
    "annual_revenue": "25M-75M",
    "clay_company_id": 49371725,
    "resolved_domain": { "is_live": true, "resolved_domain": "russelltobin.com", ... },
    "derived_datapoints": { "industry": [...], "description": "...", "subindustry": [...], ... },
    "linkedin_company_id": 827183,
    "total_funding_amount_range_usd": "Funding unknown"
}
```

**Clay Find People sample** (`#A - User Inputs/clay-find-people/sample-payload.json`):
```json
{
    "url": "https://www.linkedin.com/in/lauriecanepa/",
    "name": "Laurie Canepa",
    "domain": "stevendouglas.com",
    "last_name": "Canepa",
    "first_name": "Laurie",
    "location_name": "Austin, Texas, United States",
    "company_table_id": "t_0tbworv5nq5XoEu2xwe",
    "company_record_id": "r_0tbwory2twswCf8544H",
    "latest_experience_title": "Managing Director - State of Texas (Accounting and Finance Executive Search)",
    "latest_experience_company": "StevenDouglas",
    "latest_experience_start_date": "2023-01-01"
}
```

**Existing code to read:**

- `CLAUDE.md` — project conventions, auth model, API surface
- `app/services/entity_state.py` — `upsert_company_entity()`, `upsert_person_entity()`, `_company_fields_from_context()`, `_person_fields_from_context()`. These are the functions you will call. Study which canonical field names they expect so your field mapping feeds them correctly.
- `app/services/entity_relationships.py` — `record_entity_relationship()`. Use this for `works_at` edges.
- `app/routers/entities_v1.py` — existing entity query endpoints. Follow the same auth pattern (`_resolve_flexible_auth`), response shape (`DataEnvelope`), and request model style.
- `app/routers/_responses.py` — `DataEnvelope`, `ErrorEnvelope`, `error_response`
- `app/main.py` — router registration
- `app/database.py` — `SchemaAwareSupabaseClient`, schema routing. Note: `.rpc()` calls need explicit `.schema()` routing; `.table()` calls are auto-routed.
- `scripts/backfill_entity_relationships.py` — reference pattern for how `works_at` edges are created (matched vs unmatched, source_identifier selection, metadata shape)
- `supabase/migrations/007_entity_state.sql` — `company_entities` and `person_entities` column definitions
- `supabase/migrations/021_schema_split_ops_entities.sql` — confirms all entity tables live in the `entities` schema

---

### Deliverable 1: Field Mapping Module

Create `app/services/external_ingest.py`.

**What it does:**

Implements two mapping functions that translate raw external payloads into the canonical field dictionaries that `upsert_company_entity()` and `upsert_person_entity()` expect.

**`map_company_payload(raw: dict, source_provider: str) -> dict`**

Map Clay company fields to the canonical field names that `_company_fields_from_context()` consumes:

| Clay field | Canonical field | Notes |
|---|---|---|
| `domain` | `canonical_domain` | Primary identity key |
| `name` | `canonical_name` | |
| `linkedin_url` | `linkedin_url` | |
| `linkedin_company_id` | `company_linkedin_id` | Cast to string |
| `industry` | `industry` | |
| `size` | `employee_range` | e.g., "201-500 employees" |
| `country` | `hq_country` | |
| `description` | `description` | |
| `annual_revenue` | `revenue_band` | e.g., "25M-75M" |
| `source_provider` (injected) | `source_providers` | Wrap as `[source_provider]` |

**Everything else in the raw payload** (`type`, `location`, `industries`, `resolved_domain`, `derived_datapoints`, `clay_company_id`, `total_funding_amount_range_usd`, and any other fields) must be preserved in the returned dict. The existing `upsert_company_entity()` merges the full dict into `canonical_payload` via `_merge_non_null()` — so all fields survive, even if they don't have a dedicated column. Do not discard any fields.

**`map_person_payload(raw: dict, source_provider: str) -> dict`**

Map Clay person fields to the canonical field names that `_person_fields_from_context()` consumes:

| Clay field | Canonical field | Notes |
|---|---|---|
| `url` | `linkedin_url` | Primary identity key |
| `name` | `full_name` | |
| `first_name` | `first_name` | |
| `last_name` | `last_name` | |
| `latest_experience_title` | `title` | Maps to `title` or `current_title` |
| `domain` | `current_company_domain` | Used for `works_at` edge creation |
| `latest_experience_company` | `current_company_name` | |
| `source_provider` (injected) | `source_providers` | Wrap as `[source_provider]` |

**Everything else** (`location_name`, `company_table_id`, `company_record_id`, `latest_experience_start_date`, and any other fields) must be preserved in the returned dict for storage in `canonical_payload`.

**Important design constraint:** These mapping functions must not import or call `upsert_company_entity` / `upsert_person_entity` — they only produce the canonical dict. The ingest service (Deliverable 2) calls the upsert functions. This keeps mapping testable in isolation.

Commit standalone.

---

### Deliverable 2: Bulk Ingest Service Function

Add to `app/services/external_ingest.py`.

**`ingest_entities(*, org_id: str, company_id: str | None, entity_type: str, source_provider: str, payloads: list[dict]) -> dict`**

**What it does:**

1. For each raw payload in `payloads`:
   a. Call the appropriate mapping function from Deliverable 1 to produce a canonical dict.
   b. Call `upsert_company_entity()` or `upsert_person_entity()` with `org_id`, `company_id`, the mapped canonical fields, `last_operation_id=f"external.ingest.{source_provider}"`, and `last_run_id=None`.
   c. Catch `EntityStateVersionError` — count as skipped (version conflict means a newer version already exists).
   d. Track whether the upsert was a create or update (check if the returned record's `record_version` is 1 for create, >1 for update).

2. **For person payloads only:** after the person entity is upserted, auto-create a `works_at` relationship edge if the mapped dict contains `current_company_domain`:
   a. Extract the person's `linkedin_url` (preferred) or `work_email` from the mapped dict as `source_identifier`. Skip edge creation if neither is available.
   b. Normalize the company domain and attempt to match against `company_entities` in the same `org_id` by `canonical_domain`. If matched, capture the `entity_id` as `target_entity_id`. If not matched, still create the edge with `target_entity_id=None`.
   c. Call `record_entity_relationship()` with:
      - `source_entity_type`: `"person"`
      - `source_entity_id`: the upserted person's `entity_id`
      - `source_identifier`: person's linkedin_url or work_email
      - `relationship`: `"works_at"`
      - `target_entity_type`: `"company"`
      - `target_entity_id`: matched company entity_id or None
      - `target_identifier`: normalized company domain
      - `metadata`: `{"source": "external_ingest", "source_provider": source_provider}`
      - `source_operation_id`: `f"external.ingest.{source_provider}"`
   d. Count edges created, matched (with target_entity_id), and unmatched.

3. Return a summary dict:
```python
{
    "entity_type": entity_type,
    "source_provider": source_provider,
    "total_submitted": len(payloads),
    "created": <count>,
    "updated": <count>,
    "skipped": <count>,
    "errors": <count>,
    "relationships_created": <count>,          # person only
    "relationships_matched": <count>,          # person only
    "relationships_unmatched": <count>,        # person only
    "relationships_skipped_no_identifier": <count>,  # person only
    "error_details": [{"index": i, "error": str(exc)}, ...]  # first 10 errors max
}
```

4. **Error handling:** Individual payload failures must not abort the batch. Catch exceptions per-record, increment the error count, and continue. Log each failure. Cap `error_details` at 10 entries to avoid massive responses.

Commit standalone.

---

### Deliverable 3: Bulk Ingest API Endpoint

Add the endpoint to `app/routers/entities_v1.py`.

**Endpoint:** `POST /api/v1/entities/ingest`

**Request model:**

```python
class BulkEntityIngestRequest(BaseModel):
    entity_type: Literal["company", "person"]
    source_provider: str = Field(..., min_length=1, max_length=100)
    payloads: list[dict[str, Any]] = Field(..., min_length=1, max_length=1000)
    # Super-admin override
    org_id: str | None = None
    company_id: str | None = None
```

**Auth:** Use the `_resolve_flexible_auth` pattern. Tenant auth scopes to `auth.org_id` and `auth.company_id`. Super-admin can override via request body `org_id` / `company_id`. Super-admin must provide `org_id`.

**Response:** Standard `DataEnvelope` wrapping the summary dict from `ingest_entities()`.

**Router:** Add to the existing `leads_router` (which is mounted at `/api/v1`). Or create a new `ingest_router` if cleaner — use your judgment, but it must be registered in `app/main.py`.

**Validation:** If `entity_type` is not `"company"` or `"person"`, return 400. If `payloads` is empty, return 400.

Commit standalone.

---

### Deliverable 4: Tests

Create `tests/test_external_ingest.py`.

**Mapping tests (unit, no mocks needed):**

1. **Company mapping — all fields present** — verify Clay company payload maps to correct canonical field names.
2. **Company mapping — preserves unmapped fields** — verify `clay_company_id`, `derived_datapoints`, `resolved_domain`, `type`, `location`, etc. survive in the returned dict (they'll end up in `canonical_payload`).
3. **Company mapping — minimal payload** — verify a payload with only `domain` works without errors.
4. **Person mapping — all fields present** — verify Clay person payload maps to correct canonical field names.
5. **Person mapping — preserves unmapped fields** — verify `company_table_id`, `company_record_id`, `location_name`, `latest_experience_start_date` survive.
6. **Person mapping — url maps to linkedin_url** — verify `url` becomes `linkedin_url`.
7. **Person mapping — domain maps to current_company_domain** — verify `domain` becomes `current_company_domain` (not `canonical_domain`, which is for companies).

**Service tests (mock DB calls):**

8. **Company ingest — creates entity** — mock `upsert_company_entity` to return a record with `record_version=1`, verify summary shows `created=1`.
9. **Person ingest — creates entity and works_at edge** — mock both `upsert_person_entity` and `record_entity_relationship`, verify both are called and summary includes relationship counts.
10. **Batch error handling** — mock `upsert_company_entity` to raise on the second call, verify first record succeeds, second is counted as error, and processing continues.
11. **Version conflict counted as skipped** — mock `upsert_company_entity` to raise `EntityStateVersionError`, verify `skipped=1`.

**Endpoint tests (mock service):**

12. **Auth scoping** — verify tenant auth uses `auth.org_id`.
13. **Super-admin org_id override** — verify super-admin uses request body `org_id`.
14. **Super-admin without org_id returns 400**.

Commit standalone.

---

**What is NOT in scope:**

- No CSV upload or file parsing.
- No webhook receiver.
- No enrichment workflow triggering after ingest.
- No changes to `upsert_company_entity()` or `upsert_person_entity()` — use them as-is.
- No changes to entity_relationships service functions.
- No changes to the existing leads query endpoint or backfill script.
- No migrations — the existing table schemas support this work.
- No deploy commands.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with:
(a) The exact field mapping tables for both company and person — which Clay fields map to which canonical fields, and which are pass-through to canonical_payload.
(b) The request model fields and route path.
(c) How `source_provider` is threaded — where it appears on the upserted entity record and the relationship edge.
(d) Test count and coverage summary.
(e) Whether you found any Clay fields that conflict with existing canonical field names (e.g., Clay's `domain` vs the existing `canonical_domain` / `company_domain` distinction).
(f) Anything to flag.
