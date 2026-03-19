# Executor Directive: Enigma SMB Discovery & Enrichment — End-to-End Build

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Enigma is the most reliable source of data on U.S. small and medium businesses — brand identity, operating locations, card revenue analytics, competitive ranks, review summaries, and contact data. Today the repo has 3 provider adapter functions and 2 wired operations (`company.enrich.card_revenue`, `company.enrich.locations`), none of which are integrated into Trigger.dev workflows, blueprints, or dedicated persistence. This directive builds the full Enigma SMB discovery and enrichment capability end-to-end: two new operations (aggregate market sizing and brand discovery), one extended operation (locations with card revenue, ranks, reviews, contacts), a dedicated persistence table with migration, an array-capable upsert service using confirmed writes, a dedicated Trigger.dev workflow, and a blueprint to make it submittable. Every piece, built the right way — confirmed writes, not auto-persist; dedicated workflow, not run-pipeline.ts.

---

## Critical Design Constraint: Confirmed Writes Only

**Read `docs/PERSISTENCE_MODEL.md` before starting.** This is the most important file for understanding what works and what is broken.

**DO NOT:**
- Add any code to `trigger/src/tasks/run-pipeline.ts`
- Use the auto-persist try/catch pattern anywhere
- Swallow persistence failures silently

**DO:**
- Use `writeDedicatedTableConfirmed()` from `trigger/src/workflows/persistence.ts` for all dedicated table writes
- Use `upsertEntityStateConfirmed()` for entity state writes
- Track persistence outcomes in a structured result object — if any write fails, the pipeline must fail

Production evidence for why this matters: `company_customers` has 0 rows despite 18 successful upstream steps. `salesnav_prospects` has 0 rows despite 35 successful steps. Both use auto-persist. The healthy tables (`icp_job_titles`, `company_intel_briefings`, `person_intel_briefings`) use confirmed writes in dedicated workflows.

---

## Reference Documents (Read Before Starting)

**Must read — persistence model (THE key file):**
- `docs/PERSISTENCE_MODEL.md` — how persistence works, confirmed writes vs auto-persist, data loss risks

**Must read — Enigma API:**
- `docs/ENIGMA_API_REFERENCE.md` — consolidated Enigma API reference (query chains, credit model, GraphQL patterns)
- `docs/ENIGMA_INTEGRATION_AUDIT.md` — current integration state (3 adapters, 2 operations, 0 Trigger)

**Must read — existing Enigma code:**
- `app/providers/enigma.py` — existing adapter functions and GraphQL queries
- `app/contracts/company_enrich.py` — existing Pydantic contracts (CardRevenueOutput, EnigmaLocationsOutput, EnigmaLocationItem)
- `app/services/company_operations.py` — existing service functions (execute_company_enrich_card_revenue at line 662, execute_company_enrich_locations at line 761)
- `app/routers/execute_v1.py` — operation wiring (SUPPORTED_OPERATION_IDS, dispatch)

**Must read — Enigma source API docs (determine actual query shapes):**
- `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/02-search-and-get-data-via-api.md` — SearchInput, prompt field, entityType, conditions
- `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/03-get-aggregate-location-counts.md` — aggregate query pattern
- `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/04-use-case-examples.md` — worked examples
- `docs/api-reference-docs/enigma/08-reference/01-data-attribute-reference.md` — attribute tiers, per-location attributes
- `docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md` — full GraphQL schema reference
- `docs/api-reference-docs/enigma/04-resources/03-pricing-and-credit-use.md` — credit pricing per tier

Also check for newer docs at `docs/api-reference-docs-new/enigma/` — if this directory exists and contains updated content, prefer it over the originals above.

**Must read — persistence and workflow patterns:**
- `trigger/src/workflows/persistence.ts` — confirmed writes module (writeDedicatedTableConfirmed, upsertEntityStateConfirmed, PersistenceConfirmationError)
- `trigger/src/workflows/internal-api.ts` — InternalApiClient (post, gzip, headers, error handling)
- `trigger/src/workflows/icp-job-titles-discovery.ts` — reference dedicated workflow (task + workflow structure, step execution, persistence tracking)
- `trigger/src/tasks/icp-job-titles-discovery.ts` — reference task file (minimal, delegates to workflow)

**Must read — internal endpoint patterns:**
- `app/routers/internal.py` — internal endpoint pattern (require_internal_key, _require_internal_org_id, request models, DataEnvelope responses)
- `app/services/company_customers.py` — array-capable upsert pattern (iterate list, skip invalid, upsert with on_conflict)
- `app/services/icp_job_titles.py` — single-row upsert pattern

**Must read — blueprint format:**
- `docs/blueprints/revenue_activation_tam_building_v1.json` — blueprint JSON format reference
- `CLAUDE.md` — Live Orgs section for Substrate org ID (`7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19`)

---

## Deliverable 1: New Provider Adapter — Aggregate Market Sizing

Add to `app/providers/enigma.py`:

### GraphQL Query Constant: `AGGREGATE_LOCATIONS_QUERY`

The Enigma `aggregate` query counts operating locations and associated brands for a geographic area. The executor should build the exact query by studying `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/03-get-aggregate-location-counts.md` and the GraphQL schema reference.

Key facts from the API docs:
- The `aggregate` query only supports `entityType: OPERATING_LOCATION`
- It returns `count(field: "brand")`, `count(field: "operatingLocation")`, and `count(field: "legalEntity")`
- Filtering is supported via `SearchInput.address` for geographic scoping (city, state) and via `conditions.filter` for operating status
- The `prompt` field on SearchInput is also supported here — it semantically filters by business type

**The query must request:** `brandsCount`, `operatingLocationsCount` at minimum. Filter to only `Open` operating locations.

### Function: `aggregate_locations()`

```
async def aggregate_locations(
    *,
    api_key: str | None,
    prompt: str | None,
    state: str | None,
    city: str | None,
) -> ProviderAdapterResult:
```

- If no `api_key`: return skipped with `missing_provider_api_key`
- If no `prompt` and no `state` and no `city`: return skipped with `missing_required_inputs` (at least one of prompt or geography is needed)
- Build `SearchInput` with `entityType: "OPERATING_LOCATION"`, optional `prompt`, optional `address: {state, city}`
- Add condition to filter `operatingStatuses.operatingStatus = "Open"`
- Call `_graphql_post()` — **but note:** `_graphql_post()` currently uses `_first_brand()` which looks for `data.search[]`. The `aggregate` query returns data at `data.aggregate`, not `data.search`. The executor should either:
  - (a) Create a new `_graphql_aggregate_post()` helper that extracts from `data.aggregate`, OR
  - (b) Generalize `_graphql_post()` to accept a response extractor function
  - Use judgment; keep it simple.
- Return mapped output: `{ brand_count, location_count, prompt, state, city }`

Follow the existing adapter pattern (api_key guard, input guards, attempt dict, mapped output).

Commit standalone.

---

## Deliverable 2: New Provider Adapter — Brand Discovery via Semantic Search

Add to `app/providers/enigma.py`:

### GraphQL Query Constant: `SEARCH_BRANDS_DISCOVERY_QUERY`

This is the core discovery query. It uses the `prompt` field on `SearchInput` for semantic business-type filtering. The executor should build this query by studying the `search` query patterns in the API docs.

**Key API facts:**
- `search(searchInput: { prompt: "...", entityType: BRAND, address: { state, city }, conditions: { limit, pageToken } })` — prompt enables semantic vertical discovery (e.g., "pizza restaurant", "auto repair shop", "dental clinic")
- Pagination uses `conditions.limit` (how many results) and `conditions.pageToken` (offset as string, e.g., "10" starts at the 11th result)
- `pageToken` is NOT cursor-based — it's a numeric offset string

**The query must request per brand:**
- `id` (Enigma brand ID)
- `names(first: 1)` → brand name
- `websites(first: 1)` → brand website/domain
- `count(field: "operatingLocations")` → total location count
- `industries(first: 3)` → industry names (Core tier, useful for classification)

### Function: `search_brands()`

```
async def search_brands(
    *,
    api_key: str | None,
    prompt: str | None,
    state: str | None,
    city: str | None,
    limit: int = 10,
    page_token: str | None = None,
) -> ProviderAdapterResult:
```

- If no `api_key`: return skipped
- If no `prompt`: return failed with `missing_required_inputs` (prompt is required for semantic discovery)
- Clamp `limit` to 1–50 (Enigma returns up to ~100 but we cap for credit control)
- Build `SearchInput` with `entityType: "BRAND"`, `prompt`, optional `address: {state, city}`, `conditions: { limit, pageToken }`
- **Response extraction:** The `search` query returns `data.search[]` — the existing `_first_brand()` only extracts the first result. For discovery, we need ALL results. The executor should create a `_all_brands()` helper (or similar) that extracts the full `data.search[]` array.
- Map each brand to: `{ enigma_brand_id, brand_name, website, location_count, industries }`
- Return mapped output: `{ brands: [...], brand_count, has_more: bool (true if results.length == limit, heuristic for more pages), next_page_token: str | None }`

Commit standalone.

---

## Deliverable 3: Canonical Contracts for New Operations

Add to `app/contracts/company_enrich.py`:

### `EnigmaAggregateOutput`

```python
class EnigmaAggregateOutput(BaseModel):
    brand_count: int | None = None
    location_count: int | None = None
    prompt: str | None = None
    state: str | None = None
    city: str | None = None
    source_provider: str = "enigma"
```

### `EnigmaBrandDiscoveryItem`

```python
class EnigmaBrandDiscoveryItem(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    industries: list[str] | None = None
```

### `EnigmaBrandDiscoveryOutput`

```python
class EnigmaBrandDiscoveryOutput(BaseModel):
    brands: list[EnigmaBrandDiscoveryItem] | None = None
    brand_count: int | None = None
    has_more: bool | None = None
    next_page_token: str | None = None
    prompt: str | None = None
    state: str | None = None
    city: str | None = None
    source_provider: str = "enigma"
```

### `EnigmaExtendedLocationItem`

Extends the existing `EnigmaLocationItem` concept with optional enrichment fields:

```python
class EnigmaExtendedLocationItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None
    # Extended attributes (populated when requested via options)
    card_revenue_annual: float | None = None
    card_revenue_yoy_growth: float | None = None
    card_transactions_count: float | None = None
    competitive_rank_position: int | None = None
    competitive_rank_cohort_size: int | None = None
    review_count: int | None = None
    review_score_avg: float | None = None
    # Contact data (from roles connection)
    primary_contact_name: str | None = None
    primary_contact_title: str | None = None
    primary_contact_email: str | None = None
    primary_contact_phone: str | None = None
    primary_contact_linkedin: str | None = None
```

### `EnigmaExtendedLocationsOutput`

```python
class EnigmaExtendedLocationsOutput(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    total_location_count: int | None = None
    locations: list[EnigmaExtendedLocationItem] | None = None
    location_count: int | None = None
    open_count: int | None = None
    closed_count: int | None = None
    has_next_page: bool | None = None
    end_cursor: str | None = None
    # Track which optional attributes were requested
    include_card_revenue: bool = False
    include_ranks: bool = False
    include_reviews: bool = False
    include_contacts: bool = False
    source_provider: str = "enigma"
```

Commit standalone.

---

## Deliverable 4: Service Functions for New Operations

Add to `app/services/company_operations.py`:

### `execute_company_search_enigma_aggregate()`

Follow the exact pattern of `execute_company_enrich_card_revenue()`:

- Extract `prompt`, `state`, `city` from `input_data`
- Call `enigma.aggregate_locations()`
- Validate with `EnigmaAggregateOutput`
- Return standard operation result dict

### `execute_company_search_enigma_brands()`

Follow the same pattern:

- Extract `prompt`, `state`, `city`, `limit`, `page_token` from `input_data` (and from `step_config` for pipeline use)
- Call `enigma.search_brands()`
- Validate with `EnigmaBrandDiscoveryOutput`
- Return standard operation result dict

Commit standalone.

---

## Deliverable 5: Wire New Operations into Execute Router

In `app/routers/execute_v1.py`:

1. Add `"company.search.enigma.aggregate"` and `"company.search.enigma.brands"` to `SUPPORTED_OPERATION_IDS`
2. Add dispatch branches following the existing pattern (see the `company.enrich.card_revenue` dispatch at line 615-624 as reference)
3. Each branch calls the corresponding service function and `persist_operation_execution()`

Commit standalone.

---

## Deliverable 6: Extend `company.enrich.locations` — Extended Location Attributes

### 6a: New GraphQL Query — `GET_BRAND_LOCATIONS_EXTENDED_QUERY`

Add to `app/providers/enigma.py`. This query extends `GET_BRAND_LOCATIONS_QUERY` with optional attribute connections. The executor should study the attribute reference docs to build the exact GraphQL.

**Per-location attributes to add (all optional — controlled by variables):**

1. **Card Transactions** (Plus tier, ~3 credits/location): Request `cardTransactions` connection with `period: "12m"` conditions for `card_revenue_amount` and `card_revenue_yoy_growth` and `card_transactions_count`. Use the same `ConnectionConditions` pattern as `GET_BRAND_ANALYTICS_QUERY`.

2. **Competitive Ranks** (Plus tier): Request `ranks` connection with `period: "12m"` and `quantityType: "card_revenue_amount"`. Extract `position` and `cohortSize`.

3. **Review Summary** (Plus tier): Request `reviewSummaries(first: 1)` connection. Extract `reviewCount` and `reviewScoreAvg`.

4. **Contacts/Roles** (Plus tier, ~3 credits/location): Request `roles(first: 1)` connection. Extract the first role's `jobTitle`, `jobFunction`, `managementLevel`. Then from the role node, request `person` → `names(first: 1)` → `name`, `emailAddresses(first: 1)` → `emailAddress`, `phoneNumbers(first: 1)` → `phoneNumber`, `linkedInUrl`.

**The query should use GraphQL `@include(if: $includeCardRevenue)` directives** (or similar conditional inclusion) if the API supports them. If Enigma's GraphQL does not support `@include`, build the query as a full query and let the caller always send it — the adapter function can simply skip extracting unused fields. The executor should check `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/05-directives.md` for directive support.

**If the Enigma API does not support `@include` directives or if the credit model charges for all requested attributes regardless:** Build separate query variants or a single comprehensive query, and document the credit implications. Use the most cost-effective approach.

### 6b: New Adapter Function — `get_brand_locations_extended()`

Add to `app/providers/enigma.py`:

```
async def get_brand_locations_extended(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 25,
    operating_status_filter: str | None = None,
    include_card_revenue: bool = False,
    include_ranks: bool = False,
    include_reviews: bool = False,
    include_contacts: bool = False,
    after_cursor: str | None = None,
) -> ProviderAdapterResult:
```

- Same guards as existing `get_brand_locations()`
- Use the extended query
- Map each location to the `EnigmaExtendedLocationItem` shape (existing fields + optional extended fields)
- Return mapped output matching `EnigmaExtendedLocationsOutput` shape

### 6c: Update `execute_company_enrich_locations()`

In `app/services/company_operations.py`, update the existing service function:

- Read `options` from `input_data.get("options")` or `step_config`
- If any extended options are requested (`include_card_revenue`, `include_ranks`, `include_reviews`, `include_contacts`), call the new `get_brand_locations_extended()` instead of the existing `get_brand_locations()`
- If no extended options, continue using the existing adapter (backward compatible)
- Validate with `EnigmaExtendedLocationsOutput` when extended, `EnigmaLocationsOutput` when basic

**Do NOT change the operation ID.** It remains `company.enrich.locations`. The extended behavior is opt-in via `options`.

Commit standalone.

---

## Deliverable 7: Verify `company.enrich.card_revenue`

Confirm the existing operation works correctly:

1. Read the full call chain: `execute_v1.py` dispatch → `company_operations.execute_company_enrich_card_revenue()` → `enigma.match_business()` → `enigma.get_card_analytics()`
2. Verify the contract (`CardRevenueOutput`) matches the provider adapter output
3. Run existing tests: `pytest tests/test_card_revenue.py -v`
4. Document any issues found

No code changes expected. If issues are found, document them in the report but do NOT fix them — they are out of scope.

Commit standalone (work log only if no changes needed; if tests fail, document in report).

---

## Deliverable 8: Schema Migration — Enigma SMB Discovery Tables

Create `supabase/migrations/041_enigma_smb_discovery.sql`.

### Table Design Decision

The executor should design the schema based on what the operations return. The recommended approach is **two tables** — one for brand-level discovery results and one for location-level enrichment results — because brands and locations have different natural keys, different update frequencies, and different query patterns.

### Table 1: `entities.enigma_brand_discoveries`

This stores brand-level results from `company.search.enigma.brands` and optional card revenue enrichment.

**Columns:**
- `id` UUID PRIMARY KEY DEFAULT gen_random_uuid()
- `org_id` UUID NOT NULL — tenant scope (Substrate)
- `company_id` UUID — optional FK to ops.companies
- `enigma_brand_id` TEXT NOT NULL — Enigma's brand ID
- `brand_name` TEXT
- `website` TEXT — brand domain/website
- `location_count` INTEGER — total locations reported by Enigma
- `industries` JSONB — array of industry names
- `discovery_prompt` TEXT — the semantic prompt that found this brand
- `discovery_state` TEXT — the state filter used in discovery
- `discovery_city` TEXT — the city filter used in discovery
- `annual_card_revenue` FLOAT — from card_revenue enrichment (null if not enriched)
- `annual_card_revenue_yoy_growth` FLOAT
- `annual_avg_daily_customers` FLOAT
- `annual_transaction_count` FLOAT
- `annual_avg_transaction_size` FLOAT
- `card_revenue_enriched_at` TIMESTAMPTZ — when card revenue was fetched
- `source_submission_id` UUID
- `source_pipeline_run_id` UUID
- `source_provider` TEXT NOT NULL DEFAULT 'enigma'
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()

**Constraints:**
- `UNIQUE(org_id, enigma_brand_id)` — one row per brand per org

**Indexes:**
- `(org_id, discovery_prompt)` — query by org + vertical
- `(org_id, discovery_state)` — query by org + geography
- `(org_id, website)` — lookup by domain
- `(enigma_brand_id)` — cross-reference
- `(org_id, annual_card_revenue DESC NULLS LAST)` — sort by revenue

### Table 2: `entities.enigma_location_details`

This stores location-level results from `company.enrich.locations` (extended).

**Columns:**
- `id` UUID PRIMARY KEY DEFAULT gen_random_uuid()
- `org_id` UUID NOT NULL
- `company_id` UUID
- `enigma_brand_id` TEXT NOT NULL — FK to parent brand
- `enigma_location_id` TEXT NOT NULL — Enigma's location ID
- `location_name` TEXT
- `full_address` TEXT
- `street` TEXT
- `city` TEXT
- `state` TEXT
- `postal_code` TEXT
- `operating_status` TEXT
- `card_revenue_annual` FLOAT
- `card_revenue_yoy_growth` FLOAT
- `card_transactions_count` FLOAT
- `competitive_rank_position` INTEGER
- `competitive_rank_cohort_size` INTEGER
- `review_count` INTEGER
- `review_score_avg` FLOAT
- `primary_contact_name` TEXT
- `primary_contact_title` TEXT
- `primary_contact_email` TEXT
- `primary_contact_phone` TEXT
- `primary_contact_linkedin` TEXT
- `source_submission_id` UUID
- `source_pipeline_run_id` UUID
- `source_provider` TEXT NOT NULL DEFAULT 'enigma'
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT NOW()

**Constraints:**
- `UNIQUE(org_id, enigma_location_id)` — one row per location per org

**Indexes:**
- `(org_id, enigma_brand_id)` — all locations for a brand
- `(org_id, state)` — geographic queries
- `(org_id, card_revenue_annual DESC NULLS LAST)` — sort by revenue
- `(enigma_location_id)` — cross-reference

**Both tables:**
- Enable Row Level Security (follow existing FMCSA table pattern)
- Add `updated_at` trigger using the same trigger function pattern as other entity tables (check migration 007 or 015 for the trigger pattern)

Commit standalone.

---

## Deliverable 9: Upsert Services — Array-Capable with Schema-Qualified Queries

### 9a: Create `app/services/enigma_smb_discovery.py`

**Important:** All Supabase queries must use `client.schema("entities").from_("table_name")` — not bare `client.table()`. See feedback memory: bare `client.table()` targets `public` schema and is always a bug.

#### Function: `upsert_enigma_brand_discoveries()`

```python
def upsert_enigma_brand_discoveries(
    *,
    org_id: str,
    company_id: str | None,
    brands: list[dict[str, Any]],
    discovery_prompt: str | None = None,
    discovery_state: str | None = None,
    discovery_city: str | None = None,
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

Follow the `upsert_company_customers()` array pattern:
1. Iterate `brands` list
2. Skip items missing `enigma_brand_id`
3. Build row dict with all columns
4. Upsert with `on_conflict="org_id,enigma_brand_id"`
5. Return upserted rows

#### Function: `upsert_enigma_location_details()`

```python
def upsert_enigma_location_details(
    *,
    org_id: str,
    company_id: str | None,
    enigma_brand_id: str,
    locations: list[dict[str, Any]],
    source_submission_id: str | None = None,
    source_pipeline_run_id: str | None = None,
) -> list[dict[str, Any]]:
```

Same array pattern:
1. Iterate `locations` list
2. Skip items missing `enigma_location_id`
3. Build row dict with all columns including parent `enigma_brand_id`
4. Upsert with `on_conflict="org_id,enigma_location_id"`
5. Return upserted rows

### 9b: Internal Endpoints

Add to `app/routers/internal.py`:

#### `POST /api/internal/enigma-brand-discoveries/upsert`

Request model:
```python
class InternalUpsertEnigmaBrandDiscoveriesRequest(BaseModel):
    brands: list[dict[str, Any]]
    discovery_prompt: str | None = None
    discovery_state: str | None = None
    discovery_city: str | None = None
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

- Auth: `require_internal_key`
- Extract `org_id` from `_require_internal_org_id(request)`
- Extract `company_id` from `x-internal-company-id` header (optional)
- Call `upsert_enigma_brand_discoveries()`
- Return `DataEnvelope(data=result)`

#### `POST /api/internal/enigma-location-details/upsert`

Request model:
```python
class InternalUpsertEnigmaLocationDetailsRequest(BaseModel):
    enigma_brand_id: str
    locations: list[dict[str, Any]]
    source_submission_id: str | None = None
    source_pipeline_run_id: str | None = None
```

Same pattern. Call `upsert_enigma_location_details()`.

Commit standalone.

---

## Deliverable 10: Dedicated Trigger.dev Workflow

### 10a: Task File — `trigger/src/tasks/enigma-smb-discovery.ts`

Minimal task file that delegates to the workflow function. Follow the exact pattern of `trigger/src/tasks/icp-job-titles-discovery.ts`.

```typescript
import { task } from "@trigger.dev/sdk/v3";
import {
  EnigmaSmBDiscoveryWorkflowPayload,
  runEnigmaSmBDiscoveryWorkflow,
} from "../workflows/enigma-smb-discovery.js";

export const enigmaSmBDiscovery = task({
  id: "enigma-smb-discovery",
  retry: { maxAttempts: 1 },
  run: async (payload: EnigmaSmBDiscoveryWorkflowPayload) => {
    return runEnigmaSmBDiscoveryWorkflow(payload);
  },
});
```

### 10b: Workflow File — `trigger/src/workflows/enigma-smb-discovery.ts`

Follow the structure of `trigger/src/workflows/icp-job-titles-discovery.ts`.

#### Payload Interface

```typescript
export interface EnigmaSmBDiscoveryWorkflowPayload {
  pipelineRunId: string;
  submissionId: string;
  orgId: string;
  companyId?: string;
  // Operation-specific inputs
  prompt: string;
  state?: string;
  city?: string;
  limit?: number;          // How many brands to discover (default 10)
  // Enrichment toggle flags
  enrichCardRevenue?: boolean;     // default false
  enrichLocations?: boolean;       // default false
  includeCardRevenue?: boolean;    // per-location card revenue (requires enrichLocations)
  includeRanks?: boolean;          // per-location competitive ranks
  includeReviews?: boolean;        // per-location review summaries
  includeContacts?: boolean;       // per-location contact data
  locationLimit?: number;          // locations per brand (default 5)
  // Step references from blueprint
  stepResultIds: {
    aggregate?: string;            // step 1 (optional)
    brandDiscovery: string;        // step 2
    cardRevenue?: string;          // step 3 (optional, per brand)
    locations?: string;            // step 4 (optional, per brand)
  };
}
```

#### Workflow Execution Flow

```
1. Initialize InternalApiClient
2. Mark pipeline run as running

3. Step 1 (optional): Aggregate Market Sizing
   → POST /api/v1/execute { operation_id: "company.search.enigma.aggregate", input: { prompt, state, city } }
   → Mark step succeeded/failed
   → Log brand_count + location_count for reference

4. Step 2: Brand Discovery
   → POST /api/v1/execute { operation_id: "company.search.enigma.brands", input: { prompt, state, city, limit } }
   → Mark step succeeded/failed
   → Extract brands array from result.output.brands

5. Step 3 (optional, per brand): Card Revenue Enrichment
   → For each discovered brand (in sequence, to control credit spend):
     → POST /api/v1/execute { operation_id: "company.enrich.card_revenue", input: { enigma_brand_id: brand.enigma_brand_id } }
     → Merge card revenue data into the brand's accumulated context
   → Mark step succeeded if ALL brands enriched, failed if ANY fails
   → Note: Card revenue enrichment calls match_business again internally using brand_id — this is fine

6. Step 4 (optional, per brand): Location Enrichment
   → For each discovered brand (in sequence):
     → POST /api/v1/execute { operation_id: "company.enrich.locations", input: { enigma_brand_id: brand.enigma_brand_id, step_config: { limit: locationLimit }, options: { include_card_revenue, include_ranks, include_reviews, include_contacts } } }
     → Collect locations per brand
   → Mark step succeeded/failed

7. Persistence — CONFIRMED WRITES ONLY
   → Brand discoveries:
     → Call writeDedicatedTableConfirmed() → POST /api/internal/enigma-brand-discoveries/upsert
       { brands: [brand objects with optional card revenue fields], discovery_prompt, discovery_state, discovery_city, source_submission_id, source_pipeline_run_id }
     → Validate response has persisted_count > 0
   → Location details (if enrichLocations was enabled):
     → For each brand with locations:
       → Call writeDedicatedTableConfirmed() → POST /api/internal/enigma-location-details/upsert
         { enigma_brand_id, locations: [...], source_submission_id, source_pipeline_run_id }
       → Validate response
   → Entity state upsert:
     → Call upsertEntityStateConfirmed() with cumulative context including all discovered brands

8. Track persistence outcome
   → If any confirmed write throws PersistenceConfirmationError:
     → Mark pipeline run as FAILED
     → Include which writes succeeded and which failed in the result

9. Mark pipeline run as succeeded (only if all writes confirmed)
10. Return structured result with persistence flags
```

**Important implementation notes:**
- The per-brand enrichment loop (steps 3 and 4) must be **sequential**, not parallel, to control Enigma API credit spend and avoid rate limiting
- Each `/api/v1/execute` call goes through the full operation path (including `persist_operation_execution` which writes to `operation_runs` — this is the audit trail)
- The Trigger workflow's job is orchestration + confirmed persistence. Individual step execution happens via internal HTTP to FastAPI.
- For card revenue enrichment (step 3), the operation already accepts `enigma_brand_id` directly — check `execute_company_enrich_card_revenue()` input extraction. If it does NOT accept `enigma_brand_id` directly (it currently extracts `company_name`/`company_domain`), the executor should add `enigma_brand_id` as an accepted input that bypasses the match_business step.

Commit standalone.

---

## Deliverable 11: Blueprint Definition

Create `docs/blueprints/enigma_smb_discovery_v1.json`:

```json
{
  "name": "Enigma SMB Discovery v1",
  "description": "Discover SMBs in a vertical/geography via Enigma semantic search, optionally enrich with card revenue analytics and per-location data including competitive ranks, reviews, and contacts.",
  "entity_type": "company",
  "org_id": "7612fd45-8fda-4b6b-af7f-c8b0ebaa3a19",
  "steps": [
    {
      "position": 1,
      "operation_id": "company.search.enigma.aggregate",
      "step_config": {}
    },
    {
      "position": 2,
      "operation_id": "company.search.enigma.brands",
      "step_config": {
        "limit": 10
      }
    },
    {
      "position": 3,
      "operation_id": "company.enrich.card_revenue",
      "step_config": {
        "months_back": 12
      }
    },
    {
      "position": 4,
      "operation_id": "company.enrich.locations",
      "step_config": {
        "limit": 5,
        "operating_status_filter": "Open"
      }
    }
  ]
}
```

Also create `docs/blueprints/enigma_smb_discovery_v1.batch-submit.example.json` showing an example batch submit payload:

```json
{
  "blueprint_id": "<UUID — will be assigned when blueprint is created>",
  "entities": [
    {
      "input": {
        "prompt": "pizza restaurant",
        "state": "NY",
        "city": "New York",
        "enrich_card_revenue": true,
        "enrich_locations": true,
        "include_card_revenue": true,
        "include_ranks": true,
        "include_reviews": true,
        "include_contacts": false,
        "location_limit": 5
      }
    }
  ]
}
```

**Note:** The blueprint defines the step sequence. The entity input controls what enrichments to run and the geographic/vertical parameters. The dedicated workflow reads these flags from the entity input to decide which steps to execute.

Commit standalone.

---

## Deliverable 12: Tests

### 12a: `tests/test_enigma_aggregate.py`

- Test `aggregate_locations()` adapter: happy path returns brand_count + location_count, missing API key returns skipped, missing all inputs returns skipped, HTTP error returns failed, no results returns not_found
- Test `execute_company_search_enigma_aggregate()` service function: happy path, missing inputs
- Mock all HTTP calls

### 12b: `tests/test_enigma_brand_discovery.py`

- Test `search_brands()` adapter: happy path returns brands array, pagination with page_token, missing prompt returns failed, empty results returns not_found, limit clamping
- Test `execute_company_search_enigma_brands()` service function
- Mock all HTTP calls

### 12c: `tests/test_enigma_locations_extended.py`

- Test `get_brand_locations_extended()` adapter: happy path with all options enabled, happy path with no options (basic only), contact data extraction, review summary extraction, card revenue extraction, rank extraction
- Test backward compatibility: calling with no extended options produces same output as existing adapter
- Mock all HTTP calls

### 12d: `tests/test_enigma_smb_upsert.py`

- Test `upsert_enigma_brand_discoveries()`: happy path with array of brands, skip items without enigma_brand_id, empty array returns empty list, upsert on conflict updates existing rows
- Test `upsert_enigma_location_details()`: happy path with array of locations, skip items without enigma_location_id
- Mock Supabase client

### 12e: Update `tests/test_enigma_locations.py`

- Add tests for the extended options parameter path in `execute_company_enrich_locations()`
- Confirm backward compatibility (no options = existing behavior)

All tests mock HTTP calls and database operations. Use `pytest`.

Commit standalone.

---

## Deliverable 13: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file. This is your final commit.

---

## Credit Cost Estimates

Based on Enigma pricing from `docs/ENIGMA_API_REFERENCE.md` Section 4:

| Tier | Cost per Entity |
|---|---|
| Core | 1 credit (names, websites, addresses, operating status, email, phone) |
| Plus | 3 credits (card transactions, ranks, review summaries, roles/contacts) |
| Premium | 5 credits (technologies, registrations, watchlist) |

### Scenario 1: Discover 10 brands only (aggregate + discovery)

| Step | Entities | Tier | Credits |
|---|---|---|---|
| Aggregate | 1 query | Core | ~1 |
| Brand discovery (10 brands) | 10 brands | Core (names, websites, industries) | ~10 |
| **Total** | | | **~11 credits** |

### Scenario 2: Discover 10 brands + card revenue

| Step | Entities | Tier | Credits |
|---|---|---|---|
| Aggregate | 1 | Core | ~1 |
| Brand discovery (10) | 10 | Core | ~10 |
| Card revenue (10 brands × match + analytics) | 10 brands, 2 queries each | Plus (card transactions) | ~30 |
| **Total** | | | **~41 credits** |

### Scenario 3: Discover 10 brands + card revenue + locations (avg 2 locations/brand, basic)

| Step | Entities | Tier | Credits |
|---|---|---|---|
| Aggregate | 1 | Core | ~1 |
| Brand discovery (10) | 10 | Core | ~10 |
| Card revenue (10) | 10 | Plus | ~30 |
| Locations (10 brands × ~2 locations) | 20 locations | Core (addresses only) | ~20 |
| **Total** | | | **~61 credits** |

### Scenario 4: Discover 10 brands + card revenue + extended locations (avg 2 locations/brand)

| Step | Entities | Tier | Credits |
|---|---|---|---|
| Aggregate | 1 | Core | ~1 |
| Brand discovery (10) | 10 | Core | ~10 |
| Card revenue (10) | 10 | Plus | ~30 |
| Extended locations (20 locations with card revenue + ranks + reviews + contacts) | 20 locations | Plus | ~60 |
| **Total** | | | **~101 credits** |

### Scenario 5: Discover 50 brands full enrichment (avg 3 locations/brand)

| Step | Entities | Tier | Credits |
|---|---|---|---|
| Aggregate | 1 | Core | ~1 |
| Brand discovery (50) | 50 | Core | ~50 |
| Card revenue (50) | 50 | Plus | ~150 |
| Extended locations (150 locations) | 150 | Plus | ~450 |
| **Total** | | | **~651 credits** |

**Credit control lever:** The `limit` parameter on brand discovery and `locationLimit` per brand are the primary cost controls. The enrichment toggle flags (`enrichCardRevenue`, `enrichLocations`, etc.) are the secondary controls.

---

## What is NOT in scope

- **No changes to `trigger/src/tasks/run-pipeline.ts`.** The dedicated workflow is independent.
- **No auto-persist branches.** All persistence uses confirmed writes.
- **No changes to existing Enigma operations' behavior** when called without extended options (backward compatible).
- **No deploy commands.** Do not push. Do not deploy Trigger.dev or Railway.
- **No database migrations beyond 041.** One migration file covers both tables.
- **No fan-out implementation.** The workflow handles brand iteration internally in a sequential loop, not via the fan-out mechanism.
- **No changes to `app/main.py`.**
- **No KYB, screening, or other non-GTM Enigma capabilities.**
- **No rate limiting or retry logic in the adapter.** If the API returns 429, it fails the step. Rate limiting is a future concern.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Adapter functions: list new/modified functions in `app/providers/enigma.py` with line counts
(b) Contracts: list all new Pydantic models
(c) Service functions: list new/modified functions in `app/services/company_operations.py`
(d) Router wiring: confirm both new operations in SUPPORTED_OPERATION_IDS, confirm dispatch branches
(e) Migration: table names, column counts, unique constraints, index counts
(f) Upsert service: function signatures, array handling approach, on_conflict keys
(g) Internal endpoints: paths, request models, auth approach
(h) Workflow: task ID, payload fields, execution flow (which steps are sequential vs parallel), persistence approach (confirm: confirmed writes only)
(i) Blueprint: name, org_id, step count, step operation_ids
(j) Tests: total test count per file, all passing
(k) Card revenue verification: confirm existing operation works, any issues found
(l) Credit cost: confirm the estimates above or provide corrected estimates based on actual API doc findings
(m) Anything to flag — especially: any API capability that didn't work as documented, any query shape that required a different approach than expected, any concern about credit spend at scale, whether `@include` directives are supported by Enigma's GraphQL
