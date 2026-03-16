**Directive: List Management CRUD Endpoints**

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We just shipped `POST /api/v1/search` which returns normalized search results. The next piece is list management — users search for companies or people, preview results, and save them as a named list for later enrichment, export, or campaign enrollment. This is straightforward CRUD with a join table. No Trigger.dev, no async jobs.

**The user flow this enables:**

1. User searches via `POST /api/v1/search` → gets normalized results
2. User says "save this as my Money20/20 list" → `POST /api/v1/lists` creates the list
3. The search results are added as members → `POST /api/v1/lists/{id}/members`
4. Later, user retrieves the list → `GET /api/v1/lists/{id}`
5. User exports for campaign enrollment → `GET /api/v1/lists/{id}/export`

**Existing code to read before starting:**

- `app/routers/entities_v1.py` lines 40-50 — `_resolve_flexible_auth` pattern (copy for the new router)
- `app/routers/search_v1.py` — recently built, shows the FastAPI body parameter pattern with `Field(ge=, le=)` constraints
- `app/contracts/intent_search.py` — `IntentSearchOutput` shows the shape of search results that become list members
- `app/main.py` — how routers are registered
- `app/database.py` — `get_supabase_client()` for DB access
- `supabase/migrations/026_client_automation_and_entity_associations.sql` — recent migration format reference (uses `ops.` schema, `BEGIN`/`COMMIT` wrapping, UUID PKs, org_id scoping, indexes)
- `supabase/migrations/021_schema_split_ops_entities.sql` — schema split context. Lists belong in `ops` schema (they're user-created operational data, not canonical entities)
- Memory file `feedback_schema_qualified_queries.md` — **all queries must use `client.schema("ops").table(...)` or `client.schema("entities").table(...)`. Bare `client.table()` is always a bug.**

---

### Deliverable 1: Migration

Create `supabase/migrations/029_lists.sql`:

```sql
BEGIN;

CREATE TABLE IF NOT EXISTS ops.lists (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('companies', 'people')),
    member_count INT NOT NULL DEFAULT 0,
    created_by_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at TIMESTAMPTZ,
    CONSTRAINT fk_lists_org FOREIGN KEY (org_id)
        REFERENCES ops.orgs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lists_org_id ON ops.lists(org_id);
CREATE INDEX IF NOT EXISTS idx_lists_org_id_deleted_at ON ops.lists(org_id, deleted_at);
CREATE INDEX IF NOT EXISTS idx_lists_created_by ON ops.lists(created_by_user_id);

CREATE TABLE IF NOT EXISTS ops.list_members (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    list_id UUID NOT NULL,
    org_id UUID NOT NULL,
    entity_id UUID,
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    snapshot_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_list_members_list FOREIGN KEY (list_id)
        REFERENCES ops.lists(id) ON DELETE CASCADE,
    CONSTRAINT fk_list_members_org FOREIGN KEY (org_id)
        REFERENCES ops.orgs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_list_members_list_id ON ops.list_members(list_id);
CREATE INDEX IF NOT EXISTS idx_list_members_org_id ON ops.list_members(org_id);
CREATE INDEX IF NOT EXISTS idx_list_members_entity_id ON ops.list_members(entity_id);

COMMIT;
```

**Schema design notes:**

- `ops.lists` — the list itself. `entity_type` is `'companies'` or `'people'` (plural, matching search_type from the search endpoint). `member_count` is a denormalized counter maintained by the service layer on add/remove. Soft delete via `deleted_at`.
- `ops.list_members` — join table. `entity_id` is nullable — it's set when the member references an existing entity in `entities.company_entities` or `entities.person_entities`, and null when the member is a fresh search result not yet ingested. `entity_type` is `'company'` or `'person'` (singular, matching the entity table naming). `snapshot_data` stores the full provider result dict as JSONB — this is the source of truth for display, regardless of whether `entity_id` is set.
- Both tables scoped by `org_id`. The service layer filters by org from auth context.
- No unique constraint on `(list_id, entity_id)` — a member can appear in the same list twice if added from different searches (the snapshot_data may differ). If the executor believes a unique constraint is better, use judgment.

Commit standalone.

### Deliverable 2: Contracts

Create `app/contracts/lists.py`:

**Request models:**

```python
class CreateListRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity_type: Literal["companies", "people"]

class AddListMembersRequest(BaseModel):
    members: list[dict[str, Any]] = Field(..., min_length=1, max_length=500)
    # Each member is a raw result dict from the search endpoint.
    # The service extracts entity_id if present and stores the full dict as snapshot_data.

class RemoveListMembersRequest(BaseModel):
    member_ids: list[str] = Field(..., min_length=1, max_length=500)
    # UUIDs of list_member rows to remove.
```

**Response models:**

```python
class ListSummary(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    member_count: int
    created_by_user_id: str | None
    created_at: str
    updated_at: str

class ListMember(BaseModel):
    id: str
    entity_id: str | None
    entity_type: str
    snapshot_data: dict[str, Any]
    added_at: str

class ListDetail(BaseModel):
    id: str
    name: str
    description: str | None
    entity_type: str
    member_count: int
    created_by_user_id: str | None
    created_at: str
    updated_at: str
    members: list[ListMember]
    page: int
    per_page: int

class ListExport(BaseModel):
    list_id: str
    list_name: str
    entity_type: str
    member_count: int
    members: list[dict[str, Any]]
    # Each member is the snapshot_data dict directly — flat, no wrapper.
```

Commit standalone.

### Deliverable 3: Service Layer

Create `app/services/list_management.py`:

Six functions. All take a Supabase client and `org_id` (extracted from auth context by the router). All queries MUST use `client.schema("ops").table("lists")` and `client.schema("ops").table("list_members")` — never bare `client.table()`.

**1. `create_list`**

```python
async def create_list(
    *,
    client,
    org_id: str,
    name: str,
    description: str | None,
    entity_type: str,
    created_by_user_id: str | None,
) -> dict[str, Any]:
```

Insert into `ops.lists`. Return the created row.

**2. `get_lists`**

```python
async def get_lists(
    *,
    client,
    org_id: str,
    page: int = 1,
    per_page: int = 25,
) -> tuple[list[dict[str, Any]], int]:
```

Select from `ops.lists` where `org_id` matches and `deleted_at IS NULL`. Order by `created_at DESC`. Paginate. Return `(rows, total_count)`.

**3. `get_list_detail`**

```python
async def get_list_detail(
    *,
    client,
    org_id: str,
    list_id: str,
    page: int = 1,
    per_page: int = 25,
) -> dict[str, Any] | None:
```

Fetch the list row (org_id match, deleted_at IS NULL). If not found, return None. Then fetch paginated members from `ops.list_members` where `list_id` matches, ordered by `added_at DESC`. Return combined dict with list metadata + members.

**4. `add_list_members`**

```python
async def add_list_members(
    *,
    client,
    org_id: str,
    list_id: str,
    members: list[dict[str, Any]],
) -> list[dict[str, Any]]:
```

First verify the list exists and belongs to org_id (and is not deleted). If not found, raise or return an error indicator.

For each member dict:
- Extract `entity_id` if present in the dict (check keys: `entity_id`, `source_company_id`, `source_person_id` — any of these can serve as entity_id if it's a valid UUID).
- Determine `entity_type`: if the list's `entity_type` is `'companies'`, member type is `'company'`; if `'people'`, member type is `'person'`.
- Store the entire member dict as `snapshot_data`.

Insert all members in a single batch insert into `ops.list_members`.

After insert, update `ops.lists` set `member_count = member_count + len(members)`, `updated_at = NOW()`.

Return the inserted member rows.

**5. `remove_list_members`**

```python
async def remove_list_members(
    *,
    client,
    org_id: str,
    list_id: str,
    member_ids: list[str],
) -> int:
```

Delete from `ops.list_members` where `id` in `member_ids` and `list_id` matches and `org_id` matches. Count deleted rows.

Update `ops.lists` set `member_count = member_count - deleted_count`, `updated_at = NOW()`. Clamp `member_count` to 0 minimum.

Return deleted count.

**6. `delete_list`**

```python
async def delete_list(
    *,
    client,
    org_id: str,
    list_id: str,
) -> bool:
```

Soft delete: update `ops.lists` set `deleted_at = NOW()`, `updated_at = NOW()` where `id = list_id` and `org_id` matches and `deleted_at IS NULL`. Return True if a row was updated, False if not found.

**7. `export_list`**

```python
async def export_list(
    *,
    client,
    org_id: str,
    list_id: str,
) -> dict[str, Any] | None:
```

Fetch the list (org_id match, not deleted). If not found, return None. Fetch ALL members (no pagination). Return dict with list metadata + flat array of `snapshot_data` dicts.

Commit standalone.

### Deliverable 4: Router

Create `app/routers/lists_v1.py`:

Seven endpoints on a single router:

| Method | Path | Handler | Notes |
|--------|------|---------|-------|
| `POST` | `/lists` | `create_list` | Body: `CreateListRequest`. Returns created list. |
| `GET` | `/lists` | `get_lists` | Query params: `page`, `per_page`. Returns paginated list summaries. |
| `GET` | `/lists/{list_id}` | `get_list_detail` | Query params: `page`, `per_page` (for members). 404 if not found. |
| `POST` | `/lists/{list_id}/members` | `add_members` | Body: `AddListMembersRequest`. 404 if list not found. |
| `DELETE` | `/lists/{list_id}/members` | `remove_members` | Body: `RemoveListMembersRequest`. 404 if list not found. |
| `DELETE` | `/lists/{list_id}` | `delete_list` | Soft delete. 404 if not found. |
| `GET` | `/lists/{list_id}/export` | `export_list` | Returns flat member data. 404 if not found. |

**Auth:** `_resolve_flexible_auth` — same pattern as `entities_v1.py`. Extract `org_id` from auth context:
- If `AuthContext`: `auth.org_id`
- If `SuperAdminContext`: require `org_id` as a query parameter (or in the body for POST endpoints). This matches how super-admin accesses org-scoped resources elsewhere.

**Response wrapping:** Use `DataEnvelope(data=result)` for consistency with other v1 endpoints.

**Register in `app/main.py`:**
```python
app.include_router(lists_v1.router, prefix="/api/v1", tags=["lists-v1"])
```

Commit standalone.

### Deliverable 5: Tests

Create `tests/test_list_management.py`.

**Minimum 12 tests:**

**CRUD lifecycle (5):**
1. `test_create_list` — Create a companies list. Assert returned row has correct name, entity_type, member_count=0.
2. `test_get_lists_returns_only_org_scoped` — Create lists for two different org_ids. Assert each org only sees its own lists.
3. `test_get_list_detail_with_members` — Create a list, add 3 members, fetch detail. Assert member_count=3, members array has 3 items with correct snapshot_data.
4. `test_delete_list_soft_deletes` — Create a list, delete it, assert get_lists no longer returns it. Verify the row still exists in DB with deleted_at set.
5. `test_delete_list_not_found` — Delete a nonexistent list_id. Assert returns False / 404.

**Member management (4):**
6. `test_add_members_with_entity_id` — Add a member dict that includes `entity_id`. Assert the stored row has `entity_id` set and `snapshot_data` contains the full dict.
7. `test_add_members_without_entity_id` — Add a member dict with no entity_id (fresh search result). Assert `entity_id` is null and `snapshot_data` is stored.
8. `test_remove_members` — Add 3 members, remove 2 by member_id. Assert member_count decremented to 1. Assert removed member_ids no longer in list detail.
9. `test_add_members_to_deleted_list_fails` — Create and delete a list, then try to add members. Assert failure / 404.

**Export (2):**
10. `test_export_list_returns_flat_snapshots` — Create list, add 3 members with different snapshot_data. Export. Assert the export contains 3 flat dicts matching the original snapshot_data, no wrapper objects.
11. `test_export_empty_list` — Create list with no members. Export. Assert members array is empty, member_count is 0.

**Auth / edge cases (1):**
12. `test_member_count_stays_consistent` — Add 5 members, remove 2, add 3 more. Assert member_count = 6 (5 - 2 + 3).

**Testing approach:** These are service-layer tests. Mock or use a test Supabase client depending on the existing test patterns in the repo. If existing tests use mocks for Supabase, follow that pattern. If they use a real test database, follow that pattern. Check `tests/` for precedent.

Commit standalone.

---

**What is NOT in scope:**

- No CSV export. JSON export only for now.
- No enrichment triggering from lists. That's a future directive.
- No campaign enrollment integration. That's a future directive.
- No Trigger.dev changes.
- No changes to existing endpoints or services.
- No changes to the search endpoint. Lists consume search results as-is.
- No deploy.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the migration — table schemas and indexes, (b) the contracts — all request/response models, (c) the service functions — signatures and key behaviors (especially entity_id extraction and member_count maintenance), (d) the router — all 7 endpoints with their paths and auth handling, (e) test count and what each covers, (f) anything to flag — especially around Supabase client usage patterns, org_id scoping, or the member_count denormalization approach.
