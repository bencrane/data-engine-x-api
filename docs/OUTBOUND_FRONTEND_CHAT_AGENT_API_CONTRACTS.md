# Outbound Frontend Chat Agent API Contracts

Exact contracts for integrating the outbound frontend chat agent with data-engine-x.

---

## 1. Search Endpoint

**`POST /api/v1/search`**

### Request — `IntentSearchRequest`

```python
class IntentSearchRequest(BaseModel):
    search_type: Literal["companies", "people"]
    criteria: dict[str, str | list[str]]
    provider: str | None = None          # "prospeo", "blitzapi", or None (auto)
    limit: int = Field(default=25, ge=1, le=100)
    page: int = Field(default=1, ge=1)
    cursor: str | None = None            # BlitzAPI pagination only
```

### Valid `criteria` Keys

**Enum-resolved fields** (normalized per provider):
- `seniority`
- `department`
- `industry`
- `employee_range`
- `company_type`
- `continent`
- `sales_region`
- `country_code`

**Pass-through fields** (sent as-is):
- `query`
- `company_domain`
- `company_name`
- `company_linkedin_url`
- `job_title`
- `location`

Any other keys are silently ignored.

### Response — `IntentSearchOutput`

```python
class EnumResolutionDetail(BaseModel):
    input_value: str
    resolved_value: str | None
    provider_field: str | None
    match_type: str          # "exact", "synonym", "fuzzy", "none"
    confidence: float

class IntentSearchOutput(BaseModel):
    search_type: str
    provider_used: str                              # "prospeo", "blitzapi", or "none"
    results: list[dict[str, Any]]                   # normalized result dicts
    result_count: int
    enum_resolution: dict[str, EnumResolutionDetail]
    unresolved_fields: list[str]
    pagination: dict[str, Any] | None = None
    provider_attempts: list[dict[str, Any]] = []
```

**Provider fallback order:** Prospeo first, then BlitzAPI (for both search types). First provider to return results wins.

---

## 2. List Management Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/api/v1/lists` | Create list |
| `GET` | `/api/v1/lists` | Get all lists (paginated) |
| `GET` | `/api/v1/lists/{list_id}` | Get list detail + members |
| `POST` | `/api/v1/lists/{list_id}/members` | Add members |
| `DELETE` | `/api/v1/lists/{list_id}/members` | Remove members |
| `DELETE` | `/api/v1/lists/{list_id}` | Soft-delete list |
| `GET` | `/api/v1/lists/{list_id}/export` | Export list |

### Create List Request

```python
class CreateListRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    entity_type: Literal["companies", "people"]
```

### Add Members Request

```python
class AddListMembersRequest(BaseModel):
    members: list[dict[str, Any]] = Field(..., min_length=1, max_length=500)
```

Members are raw search result dicts. The service extracts `entity_id` by checking for `entity_id`, `source_company_id`, or `source_person_id` (first valid UUID found). The full dict is stored as `snapshot_data` (JSONB).

**Max 500 members per request.**

### Remove Members Request

```python
class RemoveListMembersRequest(BaseModel):
    member_ids: list[str] = Field(..., min_length=1, max_length=500)
    # UUIDs of list_member rows
```

### Response Models

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
    entity_type: str              # "company" or "person" (singular)
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
    members: list[dict[str, Any]]  # flat snapshot_data dicts
```

---

## 3. Bulk Enrich

No dedicated bulk enrich path. Both operations go through **`POST /api/v1/execute`** with different `operation_id` values.

### Request — `ExecuteV1Request`

```python
class ExecuteV1Request(BaseModel):
    operation_id: str                      # see below
    entity_type: Literal["company"]
    input: dict[str, Any]                  # { "companies": [...] }
    options: dict[str, Any] | None = None
    org_id: str | None = None              # required for super-admin auth
    company_id: str | None = None          # required for super-admin auth
```

### Two Operation IDs

| `operation_id` | What it does | Provider(s) |
|----------------|--------------|-------------|
| `company.enrich.bulk_prospeo` | Single bulk call | Prospeo only |
| `company.enrich.bulk_profile` | Multi-provider waterfall | Prospeo → BlitzAPI → CompanyEnrich → LeadMagic |

### Input Shape (both operations)

```json
{
  "companies": [
    {
      "company_domain": "intercom.com",
      "company_website": "https://intercom.com",
      "company_linkedin_url": "...",
      "company_name": "Intercom",
      "source_company_id": "..."
    }
  ]
}
```

All company fields optional, but at least one identifier required per entry. **Max 50 companies per request.** No `list_id` support — caller must pass company data directly.

### Response — `bulk_prospeo`

```python
class BulkCompanyEnrichOutput(BaseModel):
    matched: list[BulkCompanyEnrichItem]   # { identifier: str, company_profile: CompanyProfileOutput | None }
    not_matched: list[str]
    invalid_datapoints: list[str]
    total_submitted: int
    total_matched: int
    total_cost: int | None = None
    source_provider: str = "prospeo"
```

### Response — `bulk_profile`

```python
class BulkProfileEnrichOutput(BaseModel):
    results: list[BulkProfileEnrichItem]   # { identifier, status, company_profile, source_providers }
    total_submitted: int
    total_found: int
    total_not_found: int
    total_failed: int
```

Both wrapped in the standard execute envelope:

```json
{
  "data": {
    "run_id": "...",
    "operation_id": "...",
    "status": "...",
    "output": { ... },
    "provider_attempts": [...]
  }
}
```

---

## 4. Authentication

All endpoints use `Authorization: Bearer <token>`. No exceptions for protected routes.

**Public (no auth):**
- `/health`
- `POST /api/auth/login`
- `POST /api/super-admin/login`
- `POST /api/v1/registry/operations`

### Auth Models

```python
class AuthContext(BaseModel):
    user_id: str | None = None
    org_id: str
    company_id: str | None = None
    role: str                                    # "org_admin", "company_admin", "member"
    auth_method: Literal["jwt", "api_token"]

@dataclass
class SuperAdminContext:
    super_admin_id: UUID
    email: str
```

### Token Types Accepted

| Token type | Resolution |
|------------|------------|
| Tenant JWT | Decoded from session JWT → `AuthContext` |
| Tenant API token | SHA-256 hash lookup in `api_tokens` table → `AuthContext` |
| Super-admin API key | Matches `SUPER_ADMIN_API_KEY` env var → `SuperAdminContext` |
| Internal service key | Matches `INTERNAL_API_KEY` + `x-internal-org-id` header → `AuthContext` (Trigger.dev only) |

The `/api/v1/*` endpoints (search, lists, execute, entities) use flexible auth — they accept both tenant tokens and super-admin keys. Super-admin callers must pass `org_id` as a query param or in the request body.
