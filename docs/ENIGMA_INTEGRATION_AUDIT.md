# Enigma Integration Audit

**Last updated:** 2026-03-18T18:45:00Z

---

## Section 1: Enigma API Surface (What's Documented)

The following capabilities are documented in `docs/api-reference-docs/enigma/`. The repo contains 60 reference files across 9 directories.

### Growth & GTM Solutions

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| Growth/GTM | Search for a specific business | `03-growth-and-gtm-solutions/01-search-for-a-specific-business.md` | GraphQL | `search(searchInput: {name, website, address})` — typo-tolerant name search, TLD-aware domain search, address search |
| Growth/GTM | Enrich customer and prospect lists | `03-growth-and-gtm-solutions/02-enrich-customer-and-prospect-lists.md` | Console/Bulk | CSV/Parquet bulk enrichment workflow — import, enrich by entity type (Brand, Operating Location, People, Legal Entity), download |
| Growth/GTM | Qualify an inbound lead | `03-growth-and-gtm-solutions/03-qualify-an-inbound-lead.md` | Console/GraphQL | Console-based: search → view brand profile (categories, reviews, ratings) → analyze locations (revenue, growth) → evaluate card revenue trends |
| Growth/GTM | Build targeted lead lists | `03-growth-and-gtm-solutions/04-build-targeted-lead-lists.md` | Console/GraphQL | Semantic business description filtering + filters by geography (states, cities, zip codes, MSAs), revenue thresholds, NAICS, industry, growth rates, contact availability, review counts |
| Growth/GTM | Assess market position | `03-growth-and-gtm-solutions/05-assess-market-position.md` | GraphQL | Market rank attributes: `position`, `cohortSize`, `rankType`, geographic context. Percentile calculations and competitive benchmarking |

### Verification & KYB

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| KYB | Identify package (basic identity & enrichment) | `02-verification-and-kyb/01-kyb-packages.md` | REST/GraphQL | Identity verification + enrichment |
| KYB | Verify package (compliance with registration) | `02-verification-and-kyb/01-kyb-packages.md` | REST/GraphQL | Registration status verification |
| KYB | KYB API quickstart | `02-verification-and-kyb/02-kyb-api-quickstart.md` | REST | KYB API integration patterns |
| KYB | KYB response — task results | `02-verification-and-kyb/03-kyb-response-task-results.md` | REST | Task result parsing |
| KYB | KYB response — matched data | `02-verification-and-kyb/04-kyb-response-matched-data.md` | REST | Matched entity data extraction |
| KYB | TIN/EIN/SSN verification add-on | `02-verification-and-kyb/01-kyb-packages.md` | REST | Tax ID verification |
| KYB | OFAC sanctions screening add-on | `02-verification-and-kyb/01-kyb-packages.md` | REST | Sanctions list screening |

### Screening

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| Screening | Customer and transaction screening | `05-screening/01-customer-and-transaction-screening.md` | REST | Sanctions/watchlist screening, fuzzy-match results |
| Screening | Screening API overview | `05-screening/02-screening-api-overview.md` | REST | Base URL: `https://api.enigma.com/evaluation/sanctions/`, auth via `x-api-key` + `Account-Name` headers |
| Screening | Core screening endpoints | `05-screening/03-core-screening-endpoints.md` | REST | Core screening request/response patterns |
| Screening | Decision management | `05-screening/04-decision-management.md` | REST | Decision workflow endpoints |
| Screening | Batch processing | `05-screening/05-batch-processing.md` | REST | Batch screening submission |
| Screening | Screening console guide | `05-screening/06-screening-console-guide.md` | Console | UI-based screening workflows |

### GraphQL API

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| GraphQL | API quickstart | `06-query-enigma-with-graphql/01-graphql-api-quickstart.md` | GraphQL | 4 core patterns: business search, brand locations, legal entities, discovery + analysis |
| GraphQL | Search and get data | `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md` | GraphQL | `SearchInput`: `prompt` (semantic), `id`, `name`, `address`, `addresses`. Entity types: `BRAND`, `OPERATING_LOCATION`, `LEGAL_ENTITY`, `PERSON` |
| GraphQL | Aggregate location counts | `06-query-enigma-with-graphql/03-get-aggregate-location-counts.md` | GraphQL | Aggregate queries: count operating locations, associated brands, legal entities. Filter for open locations |
| GraphQL | Use case examples | `06-query-enigma-with-graphql/04-use-case-examples.md` | GraphQL | Worked examples of common query patterns |
| GraphQL | Directives | `06-query-enigma-with-graphql/05-directives.md` | GraphQL | GraphQL directive usage |
| GraphQL | Response status codes | `06-query-enigma-with-graphql/06-response-status-codes.md` | GraphQL | Error handling patterns |
| GraphQL | GraphQL API rate limits | `06-query-enigma-with-graphql/07-graphql-api-rate-limits.md` | GraphQL | Per-plan rate limits |

### MCP (AI Integration)

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| MCP | MCP tools | `07-use-enigma-with-ai-via-mcp/01-mcp-tools.md` | MCP | `search_business`, `get_brand_locations`, `get_brand_legal_entities`, `get_brand_card_analytics`, `search_gov_archive`, `generate_brands_segment`, `generate_locations_segment`, `search_kyb`, `search_negative_news` |
| MCP | Claude, ChatGPT, Cursor, VS Code, etc. integrations | `07-use-enigma-with-ai-via-mcp/02-10` | MCP | Platform-specific MCP setup guides (9 files) |

### Data & Card Revenue

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| Data | Card revenue evaluation | `04-resources/04-evaluate-card-revenue-data.md` | GraphQL | Card revenue accuracy: 67% within +/-30% error, >80% precision for <$100k or >$1M revenue bands |
| Data | Search and match logic | `04-resources/01-how-enigma-searches-and-matches.md` | GraphQL | Match algorithm documentation |
| Data | KYB v1 to v2 upgrade | `04-resources/05-upgrade-from-kyb-v1-to-v2.md` | REST | Migration guide |

### Reference

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| Reference | Data attribute reference | `08-reference/01-data-attribute-reference.md` | GraphQL | 33 attributes across Brand, Legal Entity, Operating Location, Address, Email, Industry, Person, Phone, Registered Entity, Registration, Review Summary, Role, TIN, Watchlist, Website |
| Reference | GraphQL API reference | `08-reference/02-graphql-api-reference.md` | GraphQL | Full schema reference, endpoint: `https://api.enigma.com/graphql` |

### Operating Location Detail

| Category | Capability | Documented In | API Type | Key Queries/Endpoints |
|---|---|---|---|---|
| Operating Location | Address, deliverability, card transactions, email, marketability, name, online presence, operating status, location type, revenue quality, phone, rank, registered entity, registration, review summary, role, technologies, watchlist, website, website content | `09-operating-location/01-20` | GraphQL | 20 detailed attribute reference files for operating location sub-entities |

**Total documented API surface:** ~15 distinct functional capabilities (excluding reference docs, MCP setup guides, and console-only workflows).

---

## Section 2: What's Built (Provider Adapter Inventory)

**File:** `app/providers/enigma.py` (641 lines)

### GraphQL Query Constants

| Constant | Lines | Query Name | Purpose |
|---|---|---|---|
| `SEARCH_BRAND_QUERY` | 11-28 | `SearchBrand` | Search for a brand by name/domain, returns brand ID, name, location count |
| `GET_BRAND_ANALYTICS_QUERY` | 30-186 | `GetBrandAnalytics` | Get card transaction analytics (revenue, growth, customers, transactions, avg txn size, refunds) across 1-month and 12-month periods |
| `GET_BRAND_LOCATIONS_QUERY` | 188-241 | `GetBrandLocations` | Get operating locations with addresses, operating status, pagination |

### Adapter Functions

| Function | Lines | What It Does | Enigma Endpoint | GraphQL Query | Inputs | Returns |
|---|---|---|---|---|---|---|
| `match_business()` | 432-482 | Matches a company to an Enigma brand by name and/or domain | `POST /graphql` | `SEARCH_BRAND_QUERY` (`search(searchInput: {entityType: "BRAND", name, website})`) | `api_key`, `company_name`, `company_domain` | `enigma_brand_id`, `brand_name`, `location_count` |
| `get_card_analytics()` | 485-555 | Retrieves card transaction analytics for a known brand ID across 6 metric types x 2 periods | `POST /graphql` | `GET_BRAND_ANALYTICS_QUERY` with 12 condition variables for period/quantityType filtering | `api_key`, `brand_id`, `months_back` (clamped 1-24) | Annual aggregates (revenue, growth, customers, transactions, avg txn, refunds) + monthly time series for each |
| `get_brand_locations()` | 558-640 | Retrieves operating locations for a known brand ID with optional status filter | `POST /graphql` | `GET_BRAND_LOCATIONS_QUERY` with `locationLimit` and optional `locationConditions` | `api_key`, `brand_id`, `limit` (clamped 1-100), `operating_status_filter` | `brand_name`, `enigma_brand_id`, `total_location_count`, `locations[]` (id, name, address, status), `open_count`, `closed_count`, pagination info |

### Shared Internal Helpers

| Helper | Lines | Purpose |
|---|---|---|
| `_graphql_post()` | 387-429 | Shared HTTP client — sends GraphQL query to `https://api.enigma.com/graphql` with `x-api-key` header, 30s timeout, parses response, extracts first brand from `data.search[]` |
| `_match_search_input()` | 368-377 | Builds `SearchInput` for name/domain brand matching |
| `_analytics_search_input()` | 380-384 | Builds `SearchInput` for brand ID lookup |
| `_first_brand()` | 302-307 | Extracts first brand from GraphQL response `data.search[]` |
| `_extract_brand_name()` | 310-314 | Extracts brand name from `names` or `namesConnection` edges |
| `_conditions()` | 317-325 | Builds `ConnectionConditions` filter for period/quantityType |
| `_series()` | 328-345 | Extracts time series from card transaction connection edges |
| `_annual_metric()` | 348-350 | Extracts single annual metric from connection |
| `_map_operating_location()` | 353-365 | Maps a single location node to flat dict (id, name, address fields, operating_status) |
| `_first_edge_node()` | 293-299 | Extracts first `edges[0].node` from a GraphQL connection |
| `_as_str()`, `_as_dict()`, `_as_list()`, `_as_int()`, `_as_float()` | 244-290 | Type coercion/validation helpers |

### Completeness Assessment

| Function | Complete? | Tested? | Error Handling | Rate Limiting/Retry |
|---|---|---|---|---|
| `match_business()` | Yes — fully implemented | Yes — `tests/test_card_revenue.py` (indirectly via card_revenue tests) | Handles missing API key (skipped), missing inputs (skipped), HTTP 4xx+ (failed), GraphQL errors (failed), no brand found (not_found) | No retry logic. No rate limit handling. 30s timeout via httpx. |
| `get_card_analytics()` | Yes — fully implemented | Yes — `tests/test_card_revenue.py` (4 test cases) | Same pattern as `match_business()` | No retry logic. No rate limit handling. 30s timeout. |
| `get_brand_locations()` | Yes — fully implemented | Yes — `tests/test_enigma_locations.py` (5 provider-level + 3 service-level tests) | Same pattern as `match_business()` | No retry logic. No rate limit handling. 30s timeout. |

---

## Section 3: What's Wired (Operation Pipeline Integration)

### Operations in SUPPORTED_OPERATION_IDS

| Operation ID | In SUPPORTED_OPERATION_IDS? | Line | Service Function | Provider Function(s) | Callable via /execute? | Used in Blueprints? | Called in Production? |
|---|---|---|---|---|---|---|---|
| `company.enrich.card_revenue` | Yes | `execute_v1.py:158` | `execute_company_enrich_card_revenue` (`company_operations.py:662`) | `enigma.match_business()` + `enigma.get_card_analytics()` | Yes (dispatch at `execute_v1.py:615-624`) | No (not found in `docs/blueprints/`) | **Yes** — not in the never-called operations list in operational reality check |
| `company.enrich.locations` | Yes | `execute_v1.py:159` | `execute_company_enrich_locations` (`company_operations.py:761`) | `enigma.match_business()` (fallback) + `enigma.get_brand_locations()` | Yes (dispatch at `execute_v1.py:626-635`) | No (not found in `docs/blueprints/`) | **No** — listed in the 54 never-called operations in operational reality check |

### Call Chain Trace: `company.enrich.card_revenue`

```
POST /api/v1/execute {operation_id: "company.enrich.card_revenue", input: {...}}
  → execute_v1.py:615 dispatch
    → company_operations.execute_company_enrich_card_revenue(input_data=payload.input)
      → Extract company_name, company_domain from input_data
      → enigma.match_business(api_key=settings.enigma_api_key, company_name=..., company_domain=...)
        → _graphql_post(query=SEARCH_BRAND_QUERY, ...)
          → POST https://api.enigma.com/graphql
      → If brand found: enigma.get_card_analytics(api_key=..., brand_id=matched_id, months_back=step_config.months_back)
        → _graphql_post(query=GET_BRAND_ANALYTICS_QUERY, ...)
          → POST https://api.enigma.com/graphql
      → Validate with CardRevenueOutput contract
      → Return {run_id, operation_id, status, output, provider_attempts}
    → persist_operation_execution(...)
    → Return DataEnvelope(data=result)
```

### Call Chain Trace: `company.enrich.locations`

```
POST /api/v1/execute {operation_id: "company.enrich.locations", input: {...}}
  → execute_v1.py:626 dispatch
    → company_operations.execute_company_enrich_locations(input_data=payload.input)
      → Extract enigma_brand_id from input_data or cumulative_context
      → If no enigma_brand_id: extract company_name, company_domain
        → enigma.match_business(api_key=settings.enigma_api_key, ...)
          → POST https://api.enigma.com/graphql (SEARCH_BRAND_QUERY)
      → enigma.get_brand_locations(api_key=..., brand_id=..., limit=..., operating_status_filter=...)
        → POST https://api.enigma.com/graphql (GET_BRAND_LOCATIONS_QUERY)
      → Validate with EnigmaLocationsOutput contract
      → Return {run_id, operation_id, status, output, provider_attempts}
    → persist_operation_execution(...)
    → Return DataEnvelope(data=result)
```

### Pydantic Contracts

| Contract | File | Lines | Fields |
|---|---|---|---|
| `CardRevenueTimeSeriesPoint` | `app/contracts/company_enrich.py` | 139-141 | `period_start`, `value` |
| `CardRevenueOutput` | `app/contracts/company_enrich.py` | 144-160 | `enigma_brand_id`, `brand_name`, `location_count`, 6 annual metrics, 6 monthly time series, `source_provider` (16 fields) |
| `EnigmaLocationItem` | `app/contracts/company_enrich.py` | 163-171 | `enigma_location_id`, `location_name`, `full_address`, `street`, `city`, `state`, `postal_code`, `operating_status` (8 fields) |
| `EnigmaLocationsOutput` | `app/contracts/company_enrich.py` | 174-184 | `enigma_brand_id`, `brand_name`, `total_location_count`, `locations`, `location_count`, `open_count`, `closed_count`, `has_next_page`, `end_cursor`, `source_provider` (10 fields) |

---

## Section 4: Trigger.dev Integration

| Question | Answer | Evidence |
|---|---|---|
| Are any Enigma operations referenced in Trigger.dev task files? | **No** | `grep -r "enigma\|card_revenue\|company.enrich.card_revenue\|company.enrich.locations" trigger/src/` returned zero matches |
| Is Enigma used in any blueprint definitions? | **No** | `grep -r "enigma\|card_revenue\|locations" docs/blueprints/` returned zero matches |
| Is Enigma used in any dedicated workflow files? | **No** | No Trigger.dev task references Enigma operations |
| Is there any scheduled/automated Enigma data collection? | **No** | No cron, scheduled task, or ingestion pipeline references Enigma |

**Enigma is currently only reachable via ad-hoc `POST /api/v1/execute` calls.** It is not part of any automated pipeline, blueprint, or scheduled workflow. The `company.enrich.card_revenue` operation has been called in production (likely via manual/ad-hoc testing), but `company.enrich.locations` has never been called.

---

## Section 5: Gap Analysis

### 5.1 Documented but Not Built

| Capability | Enigma API | Status | Notes |
|---|---|---|---|
| General business search (by name/domain/address) | `search(searchInput: {name, website, address})` | **Partially built** | `match_business()` exists but is narrowly scoped to brand matching (returns only brand ID, name, location count). Does not expose full business profile data (categories, industries, legal entities, websites, emails, etc.) |
| Enrich customer/prospect lists (bulk) | Console bulk CSV/Parquet enrichment | **Not built** | This is a console/batch workflow, not a direct API capability. No adapter exists. |
| Qualify an inbound lead | Console-based lead qualification workflow | **Not built** | Console workflow — not directly API-automatable. The underlying data (brand profile, location revenue, card trends) could be assembled from existing queries. |
| Build targeted lead lists | Semantic `prompt` search + geographic/revenue/industry filters | **Not built** | No adapter for `prompt`-based semantic search or aggregate filtering queries. The `SearchInput.prompt` field and `conditions` filtering are not used anywhere in the codebase. |
| Assess market position (rank/benchmarking) | `OperatingLocationRank` attributes (position, cohortSize, rankType) | **Not built** | No adapter for market rank queries. The `rank` attribute on operating locations is not queried. |
| Legal entity retrieval | `search(searchInput: {entityType: "LEGAL_ENTITY"})`, brand → legal entities connection | **Not built** | No adapter. No GraphQL query for legal entities. |
| Person/contact data | `search(searchInput: {entityType: "PERSON"})`, person attributes (name, role, phone, email) | **Not built** | No adapter. No GraphQL query for person entities. |
| Operating location card transactions (per-location) | `OperatingLocationCardTransaction` attributes on individual locations | **Not built** | Brand-level card analytics exist via `get_card_analytics()`, but per-location card revenue is not queried. |
| Operating location technologies | `OperatingLocationTechnologiesUsed` attribute | **Not built** | No adapter queries location technology data. |
| Operating location reviews | `ReviewSummary` attributes (reviewCount, reviewScoreAvg, etc.) | **Not built** | No adapter queries review summary data. |
| KYB Identify package | KYB REST API — identity verification | **Not built** | No adapter, no operation, no GraphQL query. Different API surface (REST, not GraphQL). |
| KYB Verify package | KYB REST API — registration verification | **Not built** | No adapter, no operation. |
| TIN/EIN/SSN verification | KYB add-on | **Not built** | No adapter, no operation. |
| Customer/transaction screening | REST `https://api.enigma.com/evaluation/sanctions/` | **Not built** | Completely separate REST API with different auth pattern (`Account-Name` header). No adapter. |
| Aggregate location counts | `aggregate` queries for OPERATING_LOCATION entity type | **Not built** | No adapter for aggregate queries. |
| MCP integration | Enigma MCP tools | **Not applicable** | data-engine-x is a backend API, not an AI assistant. MCP integration is not relevant. |

### 5.2 Built but Not Wired

**None.** All 3 provider adapter functions (`match_business`, `get_card_analytics`, `get_brand_locations`) are reachable through operations wired in `execute_v1.py`. `match_business` is used as an internal helper by both operations, not as a standalone operation.

### 5.3 Wired but Never Called

| Operation ID | Wired Since | Called in Production? | Notes |
|---|---|---|---|
| `company.enrich.locations` | Present in current code | **Never called** | Listed in the 54 never-called operations in `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`. Fully built, tested, wired — just never invoked. |

`company.enrich.card_revenue` is **not** in the never-called list, indicating it has been called at least once in production.

### 5.4 Planned but Not Built

**`company.enrich.locations` — ALREADY BUILT**

The directive `docs/EXECUTOR_DIRECTIVE_ENIGMA_LOCATIONS.md` scoped the `company.enrich.locations` operation. This work has been **fully completed**:

- Provider adapter: `get_brand_locations()` in `app/providers/enigma.py:558-640` — complete
- GraphQL query: `GET_BRAND_LOCATIONS_QUERY` in `app/providers/enigma.py:188-241` — complete
- Contract: `EnigmaLocationsOutput` + `EnigmaLocationItem` in `app/contracts/company_enrich.py:163-184` — complete
- Service function: `execute_company_enrich_locations()` in `app/services/company_operations.py:761+` — complete
- Router wiring: dispatch at `app/routers/execute_v1.py:626-635` — complete
- Tests: `tests/test_enigma_locations.py` — 8 test cases covering provider adapter (5) and service operation (3)

The directive's deliverables 1-5 are all implemented. It just hasn't been called in production yet.

---

## Section 6: Credential & Configuration Status

| Setting | Env Var Name | Configured In | Present in Production? | Notes |
|---|---|---|---|---|
| `enigma_api_key` | `ENIGMA_API_KEY` | `app/config.py:43` | **Unknown — cannot verify Doppler** | Optional (`str | None = None`). No default/fallback value. If missing, all Enigma operations return `status: "skipped"` with `skip_reason: "missing_provider_api_key"`. |

### Additional configuration notes:

- **No Dockerfile references:** `ENIGMA_API_KEY` is not hardcoded in the Dockerfile. It would be injected via Doppler at runtime (`CMD ["doppler", "run", "--", ...]`).
- **No Railway-specific config:** The key is not referenced in any Railway config files.
- **Graceful degradation:** All 3 adapter functions check `if not api_key` as their first guard and return a skipped result. The API will not crash if the key is missing — operations simply return skipped status.
- **The fact that `company.enrich.card_revenue` has been called in production** (not in the never-called list) is strong evidence that `ENIGMA_API_KEY` is configured in Doppler/production. If it weren't, the operation would return `skipped`, not a success or failure that would register as "called."

---

## Section 7: Rate Limits & Credit Considerations

### GraphQL API Rate Limits

Source: `docs/api-reference-docs/enigma/04-resources/02-rate-limits.md`

| Plan | Rate Limit (RPS) | Burst Limit | Daily Limit (RPD) |
|---|---|---|---|
| Trial | 10 | 20 | 100,000 |
| Pro | 50 | 100 | 500,000 |
| Max | 50 | 100 | 500,000 |
| Enterprise | 100 | 200 | No limit |

Rate-limited responses return `429 Slow Down`. The adapter (`_graphql_post`) does **not** handle 429 responses specially — they would be treated as HTTP 4xx failures.

### Credit/Pricing Model

Source: `docs/api-reference-docs/enigma/04-resources/03-pricing-and-credit-use.md`

- Credits are deducted per entity returned, based on the **highest-tier attribute** requested in the query.
- **Pricing tiers:** Free → Core (1 credit) → Plus (3 credits) → Premium (5 credits)
- Requesting the same data multiple times incurs credits each time (no caching).

### Per-Query Cost Estimates for Current Operations

| Operation | Queries | Estimated Credits per Call | Tier | Notes |
|---|---|---|---|---|
| `company.enrich.card_revenue` | 2 (match + analytics) | **~4 credits** | Match: Core (1 credit for brand name). Analytics: Plus (3 credits for `cardTransactions` attributes) | Card transaction data is Plus tier |
| `company.enrich.locations` | 1-2 (optional match + locations) | **~2-4 credits** | Match: Core (1 credit). Locations: Core (1 credit per entity for names + addresses + operatingStatus — all Core tier) | Location addresses are Core tier; if querying 25 locations, cost would be ~26 credits (1 brand + 25 locations) |

**Important:** The locations operation queries up to 100 locations per call (configurable via `limit`). At 25 locations (default), cost could be ~26 credits. At 100 locations, cost could be ~101 credits per call due to per-entity billing.

---

## Section 8: Recommendations (Informational Only)

### 1. High-value, low-effort

| Capability | Rationale |
|---|---|
| **Per-location card transactions** | The adapter pattern, GraphQL client, and location retrieval already exist. Adding `cardTransactions` to the location query would enable location-level revenue analysis. Minimal new code — extend `GET_BRAND_LOCATIONS_QUERY` and `_map_operating_location()`. |
| **Operating location reviews** | Add `reviewSummary` to location query. Same pattern extension — adds review count and average score to location data. Core/Plus tier attributes. |

### 2. High-value, medium-effort

| Capability | Rationale |
|---|---|
| **General business search/enrichment** | The `match_business()` adapter already hits the search endpoint but discards most data. Expanding it to return full brand profile (industries, websites, legal entities) would unlock enrichment use cases. Requires new output contract and broader GraphQL query. |
| **Semantic lead list building** | Using `SearchInput.prompt` for semantic business description search + geographic/revenue filters. Requires new adapter function and operation, but the GraphQL patterns are well-documented. |
| **Legal entity retrieval** | New entity type query (`LEGAL_ENTITY`). Requires new adapter, contract, and operation. Useful for compliance/KYB-adjacent workflows. |
| **Market position/rank** | Operating location rank attributes. Requires extending location queries or adding new rank-specific query. Enables competitive benchmarking. |

### 3. Low-priority

| Capability | Rationale |
|---|---|
| **KYB verification packages** | Different REST API surface, different auth patterns. Not aligned with current enrichment-focused workstreams. Would require entirely new provider adapter. |
| **TIN/EIN verification** | KYB add-on. Same concerns as above. |
| **Aggregate location counts** | Narrow use case. The existing location query returns `totalLocationCount` which covers the most common need. |

### 4. Not applicable

| Capability | Rationale |
|---|---|
| **MCP integration** | data-engine-x is a backend API. MCP tools are for AI assistant integration. Not relevant to this architecture. |
| **Screening (sanctions/watchlist)** | Completely separate REST API with different auth model (`Account-Name` header). Different use case (compliance) vs. data-engine-x's enrichment focus. Would require separate provider adapter with different auth pattern. |
| **Console-only workflows** (bulk CSV enrichment, console-based lead qualification) | These are Enigma console features, not API capabilities that can be automated. |
