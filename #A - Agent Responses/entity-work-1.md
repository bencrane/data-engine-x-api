Implemented all 6 deliverables with standalone commits, no deploy/push.
Commits created
d0d5dc7 — add 014_entity_relationships migration for typed directional entity relationships
87e8310 — add entity_relationships service with record, batch, invalidate, and query functions
727c996 — add internal endpoints for recording, batch recording, and invalidating entity relationships
b444d54 — add entity relationships query endpoint for dashboard and API consumers
efaae70 — add tests for entity relationships service and endpoints
584efe9 — update documentation for entity relationships table and endpoints
(a) Migration file path and table name
File: supabase/migrations/014_entity_relationships.sql
Table: entity_relationships
(b) Service function signatures (all 4)
record_entity_relationship(*, org_id: str, source_entity_type: str, source_identifier: str, relationship: str, target_entity_type: str, target_identifier: str, source_entity_id: str | None = None, target_entity_id: str | None = None, metadata: dict[str, Any] | None = None, source_submission_id: str | None = None, source_pipeline_run_id: str | None = None, source_operation_id: str | None = None) -> dict[str, Any]
record_entity_relationships_batch(*, org_id: str, relationships: list[dict[str, Any]]) -> list[dict[str, Any]]
invalidate_entity_relationship(*, org_id: str, source_identifier: str, relationship: str, target_identifier: str) -> dict[str, Any] | None
query_entity_relationships(*, org_id: str, source_identifier: str | None = None, target_identifier: str | None = None, relationship: str | None = None, source_entity_type: str | None = None, target_entity_type: str | None = None, include_invalidated: bool = False, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]
(c) Internal endpoint paths and request body fields
POST /api/internal/entity-relationships/record
Fields: source_entity_type, source_identifier, relationship, target_entity_type, target_identifier, source_entity_id?, target_entity_id?, metadata?, source_submission_id?, source_pipeline_run_id?, source_operation_id?
POST /api/internal/entity-relationships/record-batch
Fields: relationships (list of relationship dicts)
POST /api/internal/entity-relationships/invalidate
Fields: source_identifier, relationship, target_identifier
All 3 use Depends(require_internal_key) and enforce x-internal-org-id from headers.
(d) Query endpoint path, auth model, supported filters
Path: POST /api/v1/entity-relationships/query
Auth model: flexible auth via _resolve_flexible_auth
Tenant auth: org_id from auth context
Super-admin auth: org_id required in request body
Supported filters/body fields:
source_identifier?
target_identifier?
relationship?
source_entity_type?
target_entity_type?
include_invalidated (default False)
limit (default 100)
offset (default 0)
org_id? (used/required for super-admin path)
(e) Dedup constraint fields
(org_id, source_identifier, relationship, target_identifier)
(f) Identifier normalization logic applied
Common: trim whitespace + lowercase
Domain identifiers:
strip protocol (http://, https://)
strip www.
strip path/trailing slash (host-level canonical domain)
LinkedIn identifiers:
lowercase
strip trailing slash
strip protocol
strip www.
Applied in record, invalidate, and query paths.
(g) Test count and names
9 tests in tests/test_entity_relationships.py:
test_record_entity_relationship_creates_new
test_record_entity_relationship_dedup_updates
test_record_entity_relationship_normalizes_identifiers
test_invalidate_entity_relationship
test_invalidate_revalidates_on_re_record
test_query_filters_by_source
test_query_filters_by_relationship_type
test_query_excludes_invalidated_by_default
test_batch_record
Validation run:
PYTHONPATH=. uv run --with pytest --with pytest-asyncio --with pyyaml pytest tests/test_entity_relationships.py
Result: 9 passed
(h) Anything to flag
To expose the exact requested public path /api/v1/entity-relationships/query, I added a dedicated router in app/routers/entities_v1.py and mounted it in app/main.py under /api/v1.
A normalization hardening was added after test feedback so LinkedIn URLs with/without protocol dedupe to the same key.
Existing unrelated workspace changes (pre-existing dirty state) were left untouched.