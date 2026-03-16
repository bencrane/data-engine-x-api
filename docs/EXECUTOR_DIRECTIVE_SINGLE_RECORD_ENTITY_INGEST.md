**Directive: Simplify Entity Ingest Endpoint to Single-Record**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting. You just built the bulk ingest endpoint in `docs/EXECUTOR_DIRECTIVE_BULK_ENTITY_INGEST_ENDPOINT.md`. This directive replaces the batch design with a single-record design.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The ingest endpoint was built with a `payloads: list[dict]` field expecting batches. In practice, the caller (Clay webhook) sends one record at a time — always a single company or person payload per request. The batch wrapper adds unnecessary complexity. Simplify the endpoint to accept a single payload directly.

**Existing code to read:**

- `app/routers/entities_v1.py` — the `BulkEntityIngestRequest` model and `bulk_entity_ingest` endpoint
- `app/services/external_ingest.py` — `ingest_entities()` and the mapping functions
- `tests/test_external_ingest.py` — existing tests

---

### Deliverable 1: Simplify Request Model and Endpoint

In `app/routers/entities_v1.py`:

1. Rename `BulkEntityIngestRequest` to `EntityIngestRequest`.
2. Replace `payloads: list[dict[str, Any]]` with `payload: dict[str, Any]` (singular, one record).
3. Update the endpoint function to pass the single payload to the service.

### Deliverable 2: Simplify Service Function

In `app/services/external_ingest.py`:

1. Replace `ingest_entities()` with `ingest_entity()` — accepts a single `payload: dict` instead of `payloads: list[dict]`.
2. Remove the batch loop, error accumulation, and `error_details` list. For a single record, just let exceptions propagate — the endpoint can catch and return an error response.
3. Return shape:

```python
{
    "entity_type": entity_type,
    "source_provider": source_provider,
    "action": "created" | "updated",
    "entity_id": <the upserted entity's entity_id>,
    "relationship_created": True | False,      # person only
    "relationship_matched": True | False,      # person only, True if company entity found
}
```

4. Keep the mapping functions (`map_company_payload`, `map_person_payload`) unchanged — they're clean.
5. Keep `_resolve_company_by_domain` unchanged.

### Deliverable 3: Update Endpoint Error Handling

In `app/routers/entities_v1.py`, the endpoint should catch `EntityStateVersionError` and return a `200` with `"action": "skipped"` (not an error — it means a newer version already exists). All other exceptions should propagate normally (FastAPI returns 500).

### Deliverable 4: Update Tests

In `tests/test_external_ingest.py`:

1. Update all tests to use the single-record interface (`payload` not `payloads`).
2. Remove the batch error handling test (no longer applicable).
3. Keep: mapping tests (unchanged), single-record create/update tests, relationship edge test, version conflict test, auth tests.

---

All four deliverables can be one commit since this is a refactor of existing work.

**What is NOT in scope:**

- No changes to mapping functions.
- No changes to `_resolve_company_by_domain`.
- No new features.
- No deploy commands.

**Commit convention:** One commit. Do not push.

**When done:** Report back with: (a) the new request model fields, (b) the new return shape, (c) test count after cleanup.
