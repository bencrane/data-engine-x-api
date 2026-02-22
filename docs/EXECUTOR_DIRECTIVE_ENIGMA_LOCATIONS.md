# Directive: `company.enrich.locations` Operation — Enigma Operating Locations

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We already have `company.enrich.card_revenue` which calls Enigma's GraphQL API to get card transaction revenue data for a brand. That operation uses a two-step flow: (1) match company name/domain to Enigma brand ID via `match_business()`, then (2) query analytics for that brand. This new operation follows the same two-step pattern but queries the brand's operating locations instead — returning physical addresses, operating status (Open/Closed/Temporarily Closed), and location counts. This enables expansion/contraction signal detection for multi-location businesses.

---

## Enigma GraphQL API — Operating Locations Query

**Endpoint:** `POST https://api.enigma.com/graphql` (same as existing)

**Auth:** `x-api-key` header (same `ENIGMA_API_KEY` used by existing operations)

### GraphQL Query

```graphql
query GetBrandLocations($searchInput: SearchInput!, $locationLimit: Int!, $locationConditions: ConnectionConditions) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      namesConnection(first: 1) {
        edges {
          node {
            name
          }
        }
      }
      totalLocationCount: count(field: "operatingLocations")
      operatingLocationsConnection(first: $locationLimit, conditions: $locationConditions) {
        totalCount
        edges {
          node {
            id
            names(first: 1) {
              edges {
                node {
                  name
                }
              }
            }
            addresses(first: 1) {
              edges {
                node {
                  fullAddress
                  streetAddress1
                  city
                  state
                  postalCode
                }
              }
            }
            operatingStatuses(first: 1) {
              edges {
                node {
                  operatingStatus
                }
              }
            }
          }
        }
        pageInfo {
          hasNextPage
          endCursor
        }
      }
    }
  }
}
```

### Variables

```json
{
  "searchInput": {
    "entityType": "BRAND",
    "id": "<enigma_brand_id>"
  },
  "locationLimit": 25,
  "locationConditions": null
}
```

Optional `locationConditions` to filter by operating status:
```json
{
  "filter": {"EQ": ["operatingStatuses.operatingStatus", "Open"]}
}
```

### Response Shape (per location in `operatingLocationsConnection.edges[].node`)

```json
{
  "id": "some-uuid",
  "names": { "edges": [{ "node": { "name": "McDonald's - Austin" } }] },
  "addresses": { "edges": [{ "node": { "fullAddress": "1901 E 6TH ST AUSTIN TX 78702", "streetAddress1": "1901 E 6TH ST", "city": "AUSTIN", "state": "TX", "postalCode": "78702" } }] },
  "operatingStatuses": { "edges": [{ "node": { "operatingStatus": "Open" } }] }
}
```

`operatingStatus` values: `"Open"`, `"Closed"`, `"Temporarily Closed"`, `"Unknown"`

---

## Existing code to read before starting:

- `app/providers/enigma.py` — existing provider adapter with `match_business()`, `get_card_analytics()`, `_graphql_post()`, `_first_brand()`, `_extract_brand_name()`, `_as_str()`, `_as_int()`, all helpers. **Follow this pattern exactly.**
- `app/services/company_operations.py` — `execute_company_enrich_card_revenue()` (reference pattern for two-step Enigma operation: match → query)
- `app/contracts/company_enrich.py` — `CardRevenueOutput` and related models (reference pattern for contracts)
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — `enigma_api_key` setting (already exists)

---

## Deliverable 1: Provider Adapter — `get_brand_locations`

**File:** `app/providers/enigma.py`

### Add `GET_BRAND_LOCATIONS_QUERY` GraphQL string

Add the query from the API reference section above as a module-level constant, same style as `SEARCH_BRAND_QUERY` and `GET_BRAND_ANALYTICS_QUERY`.

### Add `get_brand_locations` function

```python
async def get_brand_locations(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 25,
    operating_status_filter: str | None = None,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `api_key` is missing → `status: "skipped"`, `skip_reason: "missing_provider_api_key"`.
2. Skip if `brand_id` is missing → `status: "skipped"`, `skip_reason: "missing_required_inputs"`.
3. Clamp `limit` to range [1, 100].
4. Build variables:
   - `searchInput`: `{"entityType": "BRAND", "id": brand_id}`
   - `locationLimit`: clamped limit value
   - `locationConditions`: if `operating_status_filter` is provided (e.g. `"Open"`), set `{"filter": {"EQ": ["operatingStatuses.operatingStatus", operating_status_filter]}}`. Otherwise `None`.
5. Call `_graphql_post(api_key=api_key, action="get_brand_locations", query=GET_BRAND_LOCATIONS_QUERY, variables=variables)`.
6. If not found or failed, return as-is (same pattern as `get_card_analytics`).
7. Map the response:

```python
"mapped": {
    "brand_name": _extract_brand_name(brand),
    "enigma_brand_id": _as_str(brand.get("id")),
    "total_location_count": _as_int(brand.get("totalLocationCount")),
    "locations": locations,  # list built below
    "location_count": len(locations),
    "open_count": sum(1 for loc in locations if loc.get("operating_status") == "Open"),
    "closed_count": sum(1 for loc in locations if loc.get("operating_status") in ("Closed", "Temporarily Closed")),
    "has_next_page": has_next_page,
    "end_cursor": end_cursor,
}
```

### Add `_map_operating_location` helper

```python
def _map_operating_location(node: dict[str, Any]) -> dict[str, Any]:
```

Extracts from a single location node:
- `enigma_location_id`: from `node["id"]` via `_as_str`
- `location_name`: from `node["names"]["edges"][0]["node"]["name"]` (use `_first_edge_node` pattern)
- `full_address`: from address node `fullAddress`
- `street`: from address node `streetAddress1`
- `city`: from address node `city`
- `state`: from address node `state`
- `postal_code`: from address node `postalCode`
- `operating_status`: from operating statuses node `operatingStatus`

Use the existing `_first_edge_node` helper to extract from connection patterns. Build a small `_first_address_node` helper if needed (same logic — navigate `edges[0].node`).

Commit standalone with message: `add Enigma get_brand_locations provider adapter for operating location retrieval`

---

## Deliverable 2: Contract

**File:** `app/contracts/company_enrich.py`

Add these models (place them near the existing `CardRevenueOutput`):

```python
class EnigmaLocationItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None


class EnigmaLocationsOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaLocationItem] | None = None
    location_count: int | None = None
    open_count: int | None = None
    closed_count: int | None = None
    has_next_page: bool | None = None
    end_cursor: str | None = None
    source_provider: str = "enigma"
```

Commit standalone with message: `add EnigmaLocationsOutput contract for operating location enrichment`

---

## Deliverable 3: Service Operation

**File:** `app/services/company_operations.py`

Add `execute_company_enrich_locations`:

```python
async def execute_company_enrich_locations(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Follow the exact pattern of `execute_company_enrich_card_revenue`.**

### Input extraction (from `input_data` or cumulative context):

- `enigma_brand_id` — check `input_data.get("enigma_brand_id")` first, then cumulative context. If present, skip the match step.
- `company_name` — from `input_data` or cumulative context (same extraction as card_revenue)
- `company_domain` — from `input_data` or cumulative context (same extraction as card_revenue)
- If no `enigma_brand_id` AND no `company_name`/`company_domain` → return `status: "failed"` with `missing_inputs: ["enigma_brand_id|company_name|company_domain"]`

### Step config:

- `limit` from `step_config.limit` (default 25, clamp 1-100)
- `operating_status_filter` from `step_config.operating_status_filter` (default `None`)

### Logic:

1. If `enigma_brand_id` is NOT in input/context: call `enigma.match_business()` to resolve it (same as card_revenue does). Append match attempt. If match fails, return failed.
2. Call `enigma.get_brand_locations(api_key=..., brand_id=enigma_brand_id, limit=limit, operating_status_filter=operating_status_filter)`.
3. Append attempt.
4. Build merged output with `enigma_brand_id`, `brand_name`, all location data.
5. Validate with `EnigmaLocationsOutput` contract.
6. Return with status `"found"` if locations exist, `"not_found"` if empty.

### Key output fields for context chaining:

Keep `enigma_brand_id`, `total_location_count`, `location_count`, `open_count`, `closed_count` at top level so downstream steps can read them from cumulative context.

Commit standalone with message: `add company.enrich.locations operation service with brand match fallback`

---

## Deliverable 4: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"company.enrich.locations"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_company_enrich_locations` from `app.services.company_operations`.
3. Add dispatch branch (follow existing pattern, place near `company.enrich.card_revenue`):

```python
if payload.operation_id == "company.enrich.locations":
    result = await execute_company_enrich_locations(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire company.enrich.locations into execute router`

---

## Deliverable 5: Tests

**File:** `tests/test_enigma_locations.py` (new file)

Follow patterns from existing Enigma tests. Mock all HTTP calls.

### Required test cases:

1. `test_get_brand_locations_missing_api_key` — skipped with `missing_provider_api_key`
2. `test_get_brand_locations_missing_brand_id` — skipped with `missing_required_inputs`
3. `test_get_brand_locations_success` — mock GraphQL response with 3 locations (2 Open, 1 Closed). Verify mapped output: `location_count` == 3, `open_count` == 2, `closed_count` == 1, each location has `enigma_location_id`, `full_address`, `operating_status`.
4. `test_get_brand_locations_empty` — mock response with empty `operatingLocationsConnection`. Verify `location_count` == 0, `locations` is empty list.
5. `test_get_brand_locations_with_status_filter` — verify `locationConditions` variable is set correctly when `operating_status_filter="Open"` is passed.
6. `test_execute_company_enrich_locations_missing_inputs` — no brand_id, no company_name, no domain → failed with missing_inputs.
7. `test_execute_company_enrich_locations_with_brand_id` — `enigma_brand_id` in input → skips match, calls `get_brand_locations` directly.
8. `test_execute_company_enrich_locations_with_domain_fallback` — no `enigma_brand_id` → calls `match_business` first, then `get_brand_locations`.

Use realistic mock data (e.g., "McDonald's" with locations in Austin TX, New York NY, San Francisco CA).

Commit standalone with message: `add tests for Enigma operating locations provider adapter and operation`

---

## Deliverable 6: Update System Overview

**File:** `docs/SYSTEM_OVERVIEW.md`

- Update operation count from 50 to 51.
- Add `company.enrich.locations` to the Company Enrichment table:

```
| `company.enrich.locations` | Enigma (operating locations with addresses and open/closed status) |
```

This makes it 8 company enrichment operations.

Commit standalone with message: `update system overview for company.enrich.locations operation`

---

## What is NOT in scope

- No per-location revenue queries (future operation)
- No per-location market rank queries (future operation)
- No fan-out implementation for locations (the output supports it, but wiring fan-out is a blueprint concern)
- No entity snapshots or change detection for locations (future work)
- No deploy commands
- No changes to other operations

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) GraphQL query variable names and what they control
(b) Provider adapter function signature
(c) `_map_operating_location` field list
(d) Contract field counts (EnigmaLocationItem, EnigmaLocationsOutput)
(e) Operation service input extraction logic (where it reads enigma_brand_id, company_name, company_domain)
(f) Router wiring confirmation
(g) Test count and names
(h) Anything to flag
