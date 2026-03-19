# Executor Directive: Enigma SMB Discovery & Enrichment — End-to-End Build

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Enigma's GraphQL API provides semantic brand discovery, per-brand and per-location card revenue analytics, location data, competitive ranking, and contact/role data. Today, data-engine-x has 3 Enigma adapters and 2 wired operations (`company.enrich.card_revenue` — production-used; `company.enrich.locations` — wired but never called). There is no Trigger.dev workflow, no blueprint, no dedicated persistence table, and no discovery/search operation. This directive builds the full Enigma SMB discovery and enrichment capability end-to-end: new operations, extended operations, a new persistence table with migration, array-capable upsert services, a dedicated Trigger.dev workflow using confirmed writes, and a blueprint.

**Critical read-first:**
- `docs/PERSISTENCE_MODEL.md` — the persistence model reference. This build MUST use confirmed writes (`trigger/src/workflows/persistence.ts`). Do NOT use auto-persist. Do NOT add anything to `run-pipeline.ts`.
- `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference with credit model, query chains, and GraphQL endpoint details.
- `docs/ENIGMA_INTEGRATION_AUDIT.md` — what exists today and what's missing.

---

## Existing code to read

Before writing any code, read these files carefully and understand the patterns:

### Enigma adapter and operations (what exists today)

- `app/providers/enigma.py` — the existing GraphQL adapter. Three functions: `match_business()`, `get_card_analytics()`, `get_brand_locations()`. Study the `_graphql_post()` helper, the auth header pattern (`x-api-key`), and the error handling. **All new adapter functions must follow this same pattern.**
- `app/contracts/company_enrich.py` — existing contracts: `CardRevenueOutput`, `EnigmaLocationsOutput`, `EnigmaLocationItem`, `CardRevenueTimeSeriesPoint`. New contracts go in this file.
- `app/services/company_operations.py` — existing service functions: `execute_company_enrich_card_revenue()`, `execute_company_enrich_locations()`. Study how they chain `match_business()` → domain operation, how they build the operation result dict (`run_id`, `operation_id`, `status`, `output`, `provider_attempts`), and how the `input_data` dict carries context from earlier pipeline steps.
- `app/routers/execute_v1.py` — existing dispatch pattern for Enigma ops (lines ~615-635). Study the if-statement routing and `persist_operation_execution()` call.

### Confirmed writes and dedicated workflow patterns

- `trigger/src/workflows/persistence.ts` — `confirmedInternalWrite()`, `upsertEntityStateConfirmed()`, `writeDedicatedTableConfirmed()`, `PersistenceConfirmationError`. **All persistence in this build must use these functions.**
- `trigger/src/tasks/icp-job-titles-discovery.ts` — the reference dedicated workflow. Study the overall structure: payload interface, task wrapper, workflow function, step chaining with `mergeStepOutput()`, confirmed write wrapper function, persistence outcome tracking, and pipeline status setting based on persistence results.
- `trigger/src/workflows/internal-api.ts` — `createInternalApiClient()`, `InternalApiClient.post()`. Study how auth context (orgId, companyId) flows from payload to headers.
- `trigger/src/workflows/context.ts` — `buildCompanySeedContext()`, `mergeStepOutput()`, `WorkflowContext`.
- `trigger/src/workflows/lineage.ts` — `markPipelineRunRunning()`, `markPipelineRunSucceeded()`, `markPipelineRunFailed()`, `markStepResultRunning()`, `markStepResultSucceeded()`, `markStepResultFailed()`, `markRemainingStepsSkipped()`.

### Array upsert pattern

- `app/services/company_customers.py` — `upsert_company_customers()`. Study how it handles arrays: iterates through `customers` list, normalizes per item, builds row dicts, upserts with conflict key. **The new Enigma brand upsert service should follow this pattern but with confirmed writes on the Trigger side.**

### Internal endpoint pattern

- `app/routers/internal.py` — study the ICP job titles upsert endpoint (lines ~651-669) for the request model, dependency injection (`require_internal_key`, `_require_internal_org_id`), and `DataEnvelope` response pattern.

### Blueprint format

- `docs/blueprints/alumnigtm_company_workflow_v1.json` — reference blueprint structure: `name`, `description`, `entity_type`, `org_id`, `steps` array with `position`, `operation_id`, `step_config`, optional `condition`.

### Enigma API documentation

- `docs/ENIGMA_API_REFERENCE.md` — sections 1-8. Pay particular attention to:
  - Section 4: credit model (per-entity billing, tier costs: Core=1, Plus=3, Premium=5)
  - Section 5: brand search with `prompt` parameter for semantic discovery
  - Section 6: brand → locations connection with nested attributes
  - Section 7: card transactions connection with filter/condition syntax
  - Section 8: roles connection for contact data
- `docs/api-reference-docs/enigma/08-reference/` — GraphQL schema SDL and data attribute reference for exact field names

### Deploy protocol

- `docs/DEPLOY_PROTOCOL.md` — migration numbering convention and migration list to update.

---

## Credit Cost Model

All credit estimates are from `docs/ENIGMA_API_REFERENCE.md` Section 4. Credits are charged **per entity returned**, not per attribute. Multiple attributes on one entity in a single query = one charge at the highest tier.

| Tier | Per Entity | Attributes |
|---|---|---|
| Core | 1 credit | Name, address, website, phone, industry, operating status |
| Plus | 3 credits | Card transactions, ranks, reviews, roles/contacts |
| Premium | 5 credits | Technologies, registrations, TINs, watchlist |

### Cost Scenarios

| Scenario | Brands | Locations (avg 2/brand) | Credits |
|---|---|---|---|
| Discover 10 brands only (Core) | 10 | 0 | 10 |
| Discover 10 brands + card revenue (Plus per brand) | 10 | 0 | 30 |
| Discover 10 brands + card revenue + locations (Core per location) | 10 | 20 | 50 |
| Discover 10 brands + card revenue + locations + location card revenue (Plus per location) | 10 | 20 | 90 |
| Discover 10 brands + full enrichment (card rev + locations + loc card rev + roles) | 10 | 20 | 90 |
| Discover 50 brands + full enrichment | 50 | 100 | 450 |

**Key insight:** The most expensive step is per-location Plus-tier attributes (card transactions, roles). Location count multiplies cost quickly. The `limit` parameter on brand discovery and the enrichment option flags are the primary credit controls.

---

## Deliverable 1: New Provider Adapters

Add two new functions to `app/providers/enigma.py`.

### Adapter 1: `search_brands_by_prompt()`

Semantic brand discovery using Enigma's `prompt` field in `SearchInput`.

```python
async def search_brands_by_prompt(
    *,
    api_key: str | None,
    prompt: str,
    state: str | None = None,
    city: str | None = None,
    limit: int = 10,
    page_token: str | None = None,
) -> ProviderAdapterResult:
```

**GraphQL query:** Define a new `SEARCH_BRANDS_BY_PROMPT_QUERY` constant. The query should:
- Use `search(searchInput: $searchInput)` with `entityType: BRAND`
- Pass `prompt` as the semantic search term
- Use `conditions` for `limit` and `pageToken`
- If `state` or `city` is provided, include geographic filtering via the `address` field in `searchInput` (e.g., `address: { state: "TX" }` or `address: { city: "Austin", state: "TX" }`)
- Request Core-tier fields per brand: `id`, `enigmaId`, `names(first: 1)`, `websites(first: 1)`, `count(field: "operatingLocations")`, `industries(first: 3)`
- Request `pageInfo { hasNextPage endCursor }` for pagination

**Important:** Study `docs/ENIGMA_API_REFERENCE.md` Section 5 and the GraphQL schema in `docs/api-reference-docs/enigma/08-reference/` to get the exact field names and connection syntax. The prompt-based search may use slightly different GraphQL syntax than the name/website search in the existing `match_business()` adapter.

**Return shape:** The `mapped` dict should contain:
```python
{
    "brands": [
        {
            "enigma_brand_id": str,
            "brand_name": str,
            "website": str | None,
            "location_count": int,
            "industries": list[str],
        },
        ...
    ],
    "total_returned": int,
    "has_next_page": bool,
    "next_page_token": str | None,
}
```

**Error handling:** Same pattern as existing adapters — check HTTP status, GraphQL errors, empty results. Return `status: "not_found"` if the search returns zero brands.

### Adapter 2: `get_locations_enriched()`

Extended location retrieval with optional Plus-tier attributes.

```python
async def get_locations_enriched(
    *,
    api_key: str | None,
    brand_id: str,
    limit: int = 25,
    operating_status_filter: str | None = None,
    include_card_transactions: bool = False,
    include_ranks: bool = False,
    include_reviews: bool = False,
    include_roles: bool = False,
    page_token: str | None = None,
) -> ProviderAdapterResult:
```

**GraphQL query:** Define a new `GET_LOCATIONS_ENRICHED_QUERY` constant. Build it dynamically based on the boolean flags — or define multiple query variants. The executor should decide the best approach (dynamic query string construction vs. multiple static queries).

**Core fields (always included):** `id`, `enigmaId`, `names(first: 1)`, `addresses(first: 1)`, `operatingStatuses(first: 1)`, `phoneNumbers(first: 1)`, `websites(first: 1)`

**Plus-tier fields (conditionally included based on flags):**
- `include_card_transactions` → `cardTransactions(first: 12, conditions: ...)` with trailing-12-month and most recent monthly revenue, growth, customers, transactions
- `include_ranks` → `ranks(first: 1)` with competitive position data
- `include_reviews` → `reviewSummaries(first: 1)` with review aggregates
- `include_roles` → `roles(first: 10)` with `jobTitle`, `jobFunction`, `managementLevel`, `emailAddresses(first: 3)`, `phoneNumbers(first: 3)`

**Return shape:** The `mapped` dict should extend `EnigmaLocationsOutput` with optional enrichment data per location. The executor should design the return shape based on what the GraphQL API actually returns — study the schema SDL in `docs/api-reference-docs/enigma/08-reference/`.

**Pagination:** Use `pageToken` in conditions for cursor-based pagination. Return `has_next_page` and `end_cursor` in the response.

Commit standalone.

---

## Deliverable 2: New Output Contracts

Add new Pydantic models to `app/contracts/company_enrich.py`.

### `EnigmaBrandDiscoveryOutput`

```python
class EnigmaBrandDiscoveryOutput(BaseModel):
    brands: list[EnigmaBrandItem] | None = None
    total_returned: int | None = None
    has_next_page: bool | None = None
    next_page_token: str | None = None
    prompt: str | None = None
    geography_filter: str | None = None
    source_provider: str = "enigma"

class EnigmaBrandItem(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    industries: list[str] | None = None
```

### `EnigmaLocationEnrichedItem`

Extend `EnigmaLocationItem` with optional Plus-tier fields:

```python
class EnigmaLocationEnrichedItem(EnigmaLocationItem):
    # Card transactions (Plus tier)
    annual_card_revenue: float | None = None
    annual_card_revenue_yoy_growth: float | None = None
    annual_avg_daily_customers: float | None = None
    annual_transaction_count: float | None = None
    # Competitive rank (Plus tier)
    competitive_rank: int | None = None
    competitive_rank_total: int | None = None
    # Reviews (Plus tier)
    review_count: int | None = None
    review_avg_rating: float | None = None
    # Roles/contacts (Plus tier)
    contacts: list[EnigmaContactItem] | None = None

class EnigmaContactItem(BaseModel):
    full_name: str | None = None
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None
    email: str | None = None
    phone: str | None = None
```

The executor should verify the exact field names against the GraphQL schema SDL and adjust. These models should represent the canonical output shape — the adapter maps GraphQL responses into these models.

Commit standalone.

---

## Deliverable 3: New Service Functions & Operation Wiring

### Service function 1: `execute_company_search_enigma_brands()`

Add to `app/services/company_operations.py`:

```python
async def execute_company_search_enigma_brands(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Input fields:**
- `prompt` (required) — semantic vertical/business description (e.g., "pizza restaurants")
- `state` (optional) — US state code for geographic filtering
- `city` (optional) — city name for geographic filtering
- `limit` (optional, default 10) — max brands to return (credit control)
- `page_token` (optional) — for pagination

**Implementation:** Call `enigma.search_brands_by_prompt()`. Validate output against `EnigmaBrandDiscoveryOutput`. Return operation result dict with `operation_id: "company.search.enigma.brands"`.

### Service function 2: `execute_company_enrich_locations_extended()`

Modify the existing `execute_company_enrich_locations()` in `app/services/company_operations.py` to support extended attributes via an `options` parameter. **Do NOT create a separate function — extend the existing one.**

**Extended input fields (via `options` dict in `input_data`):**
- `include_card_transactions` (bool, default false)
- `include_ranks` (bool, default false)
- `include_reviews` (bool, default false)
- `include_roles` (bool, default false)

**Implementation:** If any extended flag is true, call the new `get_locations_enriched()` adapter instead of `get_brand_locations()`. Otherwise, call the existing `get_brand_locations()` for backward compatibility. Map the response to the extended output model when extended attributes are requested.

### Operation wiring

Add to `app/routers/execute_v1.py`:

1. Add `"company.search.enigma.brands"` to `SUPPORTED_OPERATION_IDS`
2. Add dispatch block for `company.search.enigma.brands` → `execute_company_search_enigma_brands()`
3. The existing `company.enrich.locations` dispatch already works — the extension is in the service function

Follow the exact same dispatch pattern as the existing Enigma operations (lines ~615-635): call service function → `persist_operation_execution()` → `return DataEnvelope(data=result)`.

Commit standalone.

---

## Deliverable 4: Migration — Enigma Discovery Table

Create migration `supabase/migrations/041_enigma_brand_discoveries.sql`.

### Table: `entities.enigma_brand_discoveries`

This table stores the results of Enigma brand discovery runs — one row per brand per discovery run. Org-scoped.

```sql
SET statement_timeout = '0';
BEGIN;

CREATE TABLE IF NOT EXISTS entities.enigma_brand_discoveries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scoping
    org_id UUID NOT NULL,
    company_id UUID,

    -- Discovery context
    discovery_prompt TEXT NOT NULL,
    geography_state TEXT,
    geography_city TEXT,

    -- Brand data (Core tier)
    enigma_brand_id TEXT NOT NULL,
    brand_name TEXT,
    brand_website TEXT,
    location_count INTEGER,
    industries JSONB,

    -- Card revenue (Plus tier, populated if enrichment ran)
    annual_card_revenue NUMERIC,
    annual_card_revenue_yoy_growth NUMERIC,
    annual_avg_daily_customers NUMERIC,
    annual_transaction_count NUMERIC,
    monthly_revenue JSONB,

    -- Source tracking
    discovered_by_operation_id TEXT DEFAULT 'company.search.enigma.brands',
    source_submission_id UUID,
    source_pipeline_run_id UUID,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one brand per discovery prompt per org
-- This allows re-running the same prompt to update data
CREATE UNIQUE INDEX idx_enigma_brand_disc_upsert_key
    ON entities.enigma_brand_discoveries (org_id, enigma_brand_id, discovery_prompt);

CREATE INDEX idx_enigma_brand_disc_org
    ON entities.enigma_brand_discoveries (org_id);

CREATE INDEX idx_enigma_brand_disc_brand
    ON entities.enigma_brand_discoveries (enigma_brand_id);

CREATE INDEX idx_enigma_brand_disc_prompt
    ON entities.enigma_brand_discoveries (org_id, discovery_prompt);

COMMIT;
```

### Table: `entities.enigma_location_enrichments`

This table stores per-location enrichment results. Org-scoped. Linked to brand discoveries.

```sql
-- Within the same migration file, after enigma_brand_discoveries

CREATE TABLE IF NOT EXISTS entities.enigma_location_enrichments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Scoping
    org_id UUID NOT NULL,
    company_id UUID,

    -- Parent brand reference
    enigma_brand_id TEXT NOT NULL,
    brand_name TEXT,

    -- Location data (Core tier)
    enigma_location_id TEXT NOT NULL,
    location_name TEXT,
    full_address TEXT,
    street TEXT,
    city TEXT,
    state TEXT,
    postal_code TEXT,
    operating_status TEXT,
    phone TEXT,
    website TEXT,

    -- Card transactions (Plus tier)
    annual_card_revenue NUMERIC,
    annual_card_revenue_yoy_growth NUMERIC,
    annual_avg_daily_customers NUMERIC,
    annual_transaction_count NUMERIC,

    -- Competitive rank (Plus tier)
    competitive_rank INTEGER,
    competitive_rank_total INTEGER,

    -- Reviews (Plus tier)
    review_count INTEGER,
    review_avg_rating NUMERIC,

    -- Contacts (Plus tier, stored as JSONB array)
    contacts JSONB,

    -- Source tracking
    enriched_by_operation_id TEXT DEFAULT 'company.enrich.locations',
    source_submission_id UUID,
    source_pipeline_run_id UUID,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: one location per brand per org
CREATE UNIQUE INDEX idx_enigma_loc_enrich_upsert_key
    ON entities.enigma_location_enrichments (org_id, enigma_brand_id, enigma_location_id);

CREATE INDEX idx_enigma_loc_enrich_org
    ON entities.enigma_location_enrichments (org_id);

CREATE INDEX idx_enigma_loc_enrich_brand
    ON entities.enigma_location_enrichments (enigma_brand_id);

CREATE INDEX idx_enigma_loc_enrich_state
    ON entities.enigma_location_enrichments (state);
```

The executor should verify that these column names match the adapter return shapes from Deliverable 1. Adjust if needed.

Commit standalone.

---

## Deliverable 5: Array-Capable Upsert Services

### Service 1: `app/services/enigma_brand_discoveries.py`

Create a new service file.

```python
def upsert_enigma_brand_discoveries(
    *,
    org_id: str,
    company_id: str | None = None,
    discovery_prompt: str,
    geography_state: str | None = None,
    geography_city: str | None = None,
    brands: list[dict[str, Any]],
    discovered_by_operation_id: str = "company.search.enigma.brands",
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

**Implementation:** Follow `upsert_company_customers()` pattern:
1. Iterate through `brands` list
2. For each brand dict, extract and normalize: `enigma_brand_id` (required — skip if missing), `brand_name`, `brand_website`, `location_count`, `industries`
3. Build row dict with all fields including scoping (org_id, company_id), discovery context (prompt, geography), source tracking, and `updated_at`
4. Upsert to `entities.enigma_brand_discoveries` with conflict key `org_id,enigma_brand_id,discovery_prompt`
5. Return `result.data`

Use `client.schema("entities").table("enigma_brand_discoveries")` — never bare `client.table()`.

### Service 2: `app/services/enigma_location_enrichments.py`

Create a new service file.

```python
def upsert_enigma_location_enrichments(
    *,
    org_id: str,
    company_id: str | None = None,
    enigma_brand_id: str,
    brand_name: str | None = None,
    locations: list[dict[str, Any]],
    enriched_by_operation_id: str = "company.enrich.locations",
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

**Implementation:** Same array iteration pattern. Extract per location: `enigma_location_id` (required — skip if missing), core fields (name, address, status, phone, website), and optional Plus-tier fields (card transactions, rank, reviews, contacts as JSONB).

### Internal endpoints

Add two new endpoints to `app/routers/internal.py`:

**`POST /api/internal/enigma-brand-discoveries/upsert`**

Follow the ICP job titles endpoint pattern:
- Request model: `InternalUpsertEnigmaBrandDiscoveriesRequest` with all fields from the upsert service signature
- Auth: `require_internal_key` + `_require_internal_org_id`
- Response: `DataEnvelope(data=result)`

**`POST /api/internal/enigma-location-enrichments/upsert`**

Same pattern:
- Request model: `InternalUpsertEnigmaLocationEnrichmentsRequest`
- Auth: same
- Response: same

Commit standalone.

---

## Deliverable 6: Dedicated Trigger.dev Workflow

Create `trigger/src/tasks/enigma-smb-discovery.ts`.

This is the most complex deliverable. Follow the `icp-job-titles-discovery.ts` workflow pattern exactly.

### Payload Interface

```typescript
export interface EnigmaSmBDiscoveryWorkflowPayload {
  pipeline_run_id: string;
  org_id: string;
  company_id: string;
  submission_id?: string;
  step_results: WorkflowStepReference[];
  initial_context?: WorkflowContext;

  // Discovery parameters
  prompt: string;
  geography_state?: string;
  geography_city?: string;
  brand_limit?: number; // default 10

  // Enrichment flags (control credit spend)
  enrich_card_revenue?: boolean; // default false
  enrich_locations?: boolean; // default false
  location_limit?: number; // default 5 per brand
  include_location_card_transactions?: boolean; // default false
  include_location_ranks?: boolean; // default false
  include_location_reviews?: boolean; // default false
  include_location_roles?: boolean; // default false

  // Override defaults
  api_url?: string;
  internal_api_key?: string;
}
```

### Task Wrapper

```typescript
export const enigmaSmBDiscovery = task({
  id: "enigma-smb-discovery",
  retry: { maxAttempts: 1 },
  run: async (payload: EnigmaSmBDiscoveryWorkflowPayload) => {
    return runEnigmaSmBDiscoveryWorkflow(payload);
  },
});
```

### Workflow Steps

The workflow should execute these steps in order. Each step corresponds to a `step_results` row in the blueprint. The executor should map each step to the correct `step_results` entry by position.

**Step 1: Brand Discovery**
- Mark step running
- Call `POST /api/v1/execute` with `operation_id: "company.search.enigma.brands"`, passing `prompt`, `state`, `city`, `limit`
- Mark step succeeded/failed
- Merge output into cumulative context
- **Critical:** The output contains a `brands` array. This is the data that feeds all subsequent steps.

**Step 2: Per-Brand Card Revenue (conditional)**
- Only runs if `enrich_card_revenue` is true AND brands were discovered
- For each brand in the `brands` array:
  - Call `POST /api/v1/execute` with `operation_id: "company.enrich.card_revenue"`, passing the brand's `enigma_brand_id` (or `brand_name` + `website` for the match step)
  - Merge card revenue data back into the brand object in context
- Mark step succeeded/failed
- **Implementation decision:** The executor should decide whether to loop through brands sequentially (simpler) or use a batch approach. Sequential is safer for credit control and error isolation.

**Step 3: Per-Brand Location Enrichment (conditional)**
- Only runs if `enrich_locations` is true AND brands were discovered
- For each brand in the `brands` array:
  - Call `POST /api/v1/execute` with `operation_id: "company.enrich.locations"`, passing the brand's `enigma_brand_id` and the extended options (`include_card_transactions`, `include_ranks`, `include_reviews`, `include_roles`)
  - Merge location data back into the brand object in context
- Mark step succeeded/failed

**Step 4: Persistence (confirmed writes)**
- **Brand discoveries:** Call `POST /api/internal/enigma-brand-discoveries/upsert` via `writeDedicatedTableConfirmed()` with the full brands array (including any card revenue enrichment data merged in Step 2)
- **Location enrichments:** If locations were retrieved, call `POST /api/internal/enigma-location-enrichments/upsert` via `writeDedicatedTableConfirmed()` for each brand's locations
- **Entity state:** Call `upsertEntityStateConfirmed()` with cumulative context
- Track persistence outcomes — if any confirmed write fails, mark pipeline as failed

### Confirmed Write Wrappers

Define confirmed write wrapper functions following the `writeIcpJobTitlesConfirmed()` pattern:

```typescript
async function writeEnigmaBrandDiscoveriesConfirmed(
  client: InternalApiClient,
  params: { ... },
): Promise<EnigmaBrandDiscoveryWriteResult> {
  return writeDedicatedTableConfirmed<EnigmaBrandDiscoveryWriteResult>(client, {
    path: "/api/internal/enigma-brand-discoveries/upsert",
    payload: { ... },
    validate: (response) => Array.isArray(response) && response.length > 0,
    confirmationErrorMessage: "Enigma brand discoveries dedicated-table write could not be confirmed",
  });
}
```

Same pattern for location enrichments.

### Error Handling

- If brand discovery returns zero results, mark step as succeeded with `status: "not_found"`. Do not proceed to enrichment steps.
- If a per-brand enrichment call fails (card revenue or locations), log a warning, skip that brand, and continue with remaining brands. Do not fail the entire pipeline for a single brand failure.
- If persistence fails (confirmed write throws), mark the pipeline as failed. This is the critical difference from auto-persist.

### Fan-Out Router Registration

If the fan-out router task (`trigger/src/tasks/`) maintains a routing table for dedicated workflows, register `enigma-smb-discovery` in it. The executor should check how existing dedicated workflows are registered and follow the same pattern.

Commit standalone.

---

## Deliverable 7: Blueprint Definition

Create `docs/blueprints/enigma_smb_discovery_v1.json`.

```json
{
  "name": "Enigma SMB Discovery v1",
  "description": "Discover SMB brands by vertical/geography using Enigma semantic search, optionally enrich with card revenue and location data",
  "entity_type": "company",
  "org_id": "7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19",
  "steps": [
    {
      "position": 1,
      "operation_id": "company.search.enigma.brands",
      "step_config": {}
    },
    {
      "position": 2,
      "operation_id": "company.enrich.card_revenue",
      "step_config": {},
      "condition": {
        "exists": "brands"
      }
    },
    {
      "position": 3,
      "operation_id": "company.enrich.locations",
      "step_config": {},
      "condition": {
        "exists": "brands"
      }
    }
  ]
}
```

**Org ID:** `7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19` (Substrate — the active org for new work).

**Note:** The blueprint defines the step sequence. The dedicated workflow (`enigma-smb-discovery`) handles the per-brand iteration and enrichment flag logic internally. The blueprint's steps map to the workflow's logical stages.

The executor should verify this blueprint format against existing blueprints and adjust if needed. In particular, confirm whether `condition` syntax supports `{"exists": "brands"}` or if a different pattern is needed.

### Blueprint Database Registration

The executor should document how to register this blueprint in the database (insert into `public.blueprints` and `public.blueprint_steps`). Include the SQL statements but do NOT run them. The chief agent will handle registration.

Commit standalone.

---

## Deliverable 8: Update Deploy Protocol

Update `docs/DEPLOY_PROTOCOL.md`:

1. Add migration 041 to the migration list with description: "Enigma brand discoveries + location enrichments tables"
2. Note that this migration creates two new tables in the `entities` schema with indexes

Commit standalone.

---

## Deliverable 9: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: built Enigma SMB discovery and enrichment end-to-end:
- 2 new provider adapters (prompt-based brand search, enriched location retrieval)
- 2 new Pydantic contracts
- 1 new operation wired (`company.search.enigma.brands`) + 1 extended (`company.enrich.locations`)
- 1 migration with 2 new tables (`enigma_brand_discoveries`, `enigma_location_enrichments`)
- 2 array-capable upsert services + 2 internal endpoints
- 1 dedicated Trigger.dev workflow with confirmed writes
- 1 blueprint definition (Substrate org)
- Credit cost estimates documented

Add a last-updated timestamp at the top of each file you create or modify, in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No applying migrations to production.** Commit files only.
- **No deploying to Railway or Trigger.dev.** Commit files only.
- **No pushing to remote.** Commit locally only.
- **No modifications to `run-pipeline.ts`.** The workflow uses a dedicated task file with confirmed writes.
- **No auto-persist branches.** All persistence uses confirmed writes via `persistence.ts`.
- **No modifications to existing Enigma adapters.** `match_business()`, `get_card_analytics()`, `get_brand_locations()` remain unchanged. New adapters are additive.
- **No blueprint database registration.** Document the SQL statements in the blueprint file but do not run them.
- **No test data or production API calls.** The executor builds the code; testing happens separately.
- **No changes to CLAUDE.md.** The chief agent decides when to update CLAUDE.md.
- **No FMCSA, federal data, or non-Enigma work.** Stay within scope.

## Commit convention

Each deliverable is one commit. Do not push. Commit messages should be descriptive (e.g., "Add Enigma prompt-based brand search adapter and enriched location retrieval").

## When done

Report back with:
(a) **Adapters:** list each new adapter function, its parameters, and the GraphQL query it uses
(b) **Contracts:** list each new Pydantic model and its field count
(c) **Operations:** list each operation ID (new and extended), its service function, and its dispatch line in execute_v1.py
(d) **Migration:** file path, table names, column counts, index counts
(e) **Upsert services:** list each service, its array handling approach, its conflict key
(f) **Internal endpoints:** list each endpoint path, its request model
(g) **Workflow:** file path, step count, which steps are conditional, confirmed write wrapper count
(h) **Blueprint:** file path, step count, org_id confirmed
(i) **Credit model verification:** confirm the credit costs match the API reference, flag any discrepancies
(j) **Anything to flag:** GraphQL schema surprises, field names that didn't match documentation, pagination edge cases, any design decisions made that differed from this directive
