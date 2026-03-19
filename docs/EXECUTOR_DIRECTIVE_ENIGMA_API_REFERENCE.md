# Executor Directive: Enigma API Consolidated Reference

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The Enigma API documentation is spread across 61 markdown files in 9 subdirectories under `docs/api-reference-docs/enigma/`. Nobody reads 61 files. We need a single consolidated reference that a future executor can read and know exactly what Enigma offers, how each endpoint works, what request/response shapes look like, what Enigma's data model is, and which capabilities are relevant to our use cases. This document turns a sprawling reference library into an actionable engineering reference.

---

## Existing code to read

Before writing anything, read these files carefully. The consolidated reference must be faithful to the source material — do not invent capabilities or hallucinate API shapes.

### Enigma API reference docs (source material — read ALL of these)

Read every file under `docs/api-reference-docs/enigma/`. The full structure is:

**01-getting-started/** (2 files)
- `01-overview.md` — Enigma platform overview, what it offers
- `02-the-enigma-data-model.md` — **Critical.** Entity hierarchy: businesses, brands, locations, people, and how they relate. This is the foundation of the entire API.

**02-verification-and-kyb/** (4 files)
- `01-kyb-packages.md` — KYB package tiers and what each includes
- `02-kyb-api-quickstart.md` — KYB API endpoint, request/response shapes
- `03-kyb-response-task-results.md` — Task result structure
- `04-kyb-response-matched-data.md` — Matched data response structure

**03-growth-and-gtm-solutions/** (5 files)
- `01-search-for-a-specific-business.md` — Business search queries
- `02-enrich-customer-and-prospect-lists.md` — Batch enrichment patterns
- `03-qualify-an-inbound-lead.md` — Lead qualification via enrichment
- `04-build-targeted-lead-lists.md` — Aggregate queries for list building
- `05-assess-market-position.md` — Market assessment via location/revenue data

**04-resources/** (5 files)
- `01-how-enigma-searches-and-matches.md` — Matching algorithm explanation
- `02-rate-limits.md` — Rate limit details
- `03-pricing-and-credit-use.md` — **Important.** Credit model, per-entity billing
- `04-evaluate-card-revenue-data.md` — Card revenue data quality and interpretation
- `05-upgrade-from-kyb-v1-to-v2.md` — Migration guide (historical, but shows API evolution)

**05-screening/** (6 files)
- `01-customer-and-transaction-screening.md` — Screening overview
- `02-screening-api-overview.md` — API surface for screening
- `03-core-screening-endpoints.md` — Endpoint details
- `04-decision-management.md` — Decision management workflows
- `05-batch-processing.md` — Batch screening
- `06-screening-console-guide.md` — Console UI guide (less relevant for API reference)

**06-query-enigma-with-graphql/** (7 files)
- `01-graphql-api-quickstart.md` — **Critical.** Base URL, authentication, first query
- `02-search-and-get-data-via-api.md` — **Critical.** Search patterns, query structures, field selection
- `03-get-aggregate-location-counts.md` — Aggregate queries for analytics
- `04-use-case-examples.md` — Worked examples of common query patterns
- `05-directives.md` — GraphQL directives (caching, pagination, etc.)
- `06-response-status-codes.md` — Error handling
- `07-graphql-api-rate-limits.md` — GraphQL-specific rate limits

**07-use-enigma-with-ai-via-mcp/** (10 files)
- MCP integration guides for various AI tools. **Skim only** — these are consumer-facing guides, not API reference. Extract the MCP tool names/descriptions if they reveal undocumented capabilities, but don't spend time on setup instructions.

**08-reference/** (2 files)
- `01-data-attribute-reference.md` — **Critical.** Full attribute catalog for all entity types (business, brand, location, person). Every field name, type, and description.
- `02-graphql-api-reference.md` — **Critical.** Full GraphQL schema reference (types, queries, mutations, connections).

**09-operating-location/** (20 files)
- `01-address.md` through `20-website-content.md` — Per-attribute data model documentation for operating locations. Each file covers a specific data domain (address, contact info, revenue, foot traffic, business hours, etc.). **Read all 20** — these contain the field-level detail needed for the reference.

### Existing integration code

- `app/providers/enigma.py` — current adapter. Read every function to understand how we call Enigma today (GraphQL queries used, field selection, response parsing). Note what the adapter does and doesn't cover relative to the full API surface.
- `app/contracts/company_enrich.py` — find `CardRevenueOutput` and any other Enigma-related Pydantic models.
- `app/services/company_operations.py` — the `execute_company_enrich_card_revenue` function. Understand the two-step flow (match → analytics).

### Integration audit

- `docs/ENIGMA_INTEGRATION_AUDIT.md` — the audit showing what's built, wired, and called. Cross-reference this for the "What we've built vs what's available" section.

---

## Deliverable 1: Consolidated Enigma API Reference

Create `docs/ENIGMA_API_REFERENCE.md`.

Add a last-updated timestamp at the top:

```markdown
# Enigma API Reference

**Last updated:** 2026-03-18T[HH:MM:SS]Z

Consolidated reference for the Enigma API surface. Source material: 61 files across `docs/api-reference-docs/enigma/`.
```

Use the actual UTC time when you finish writing.

### Required sections

---

#### Section 1: Platform Overview

Brief (1-2 paragraphs) overview of what Enigma is and what data it provides. Synthesize from `01-getting-started/01-overview.md`.

Key facts to extract:
- What types of data Enigma offers (business identity, revenue, foot traffic, locations, KYB verification, screening)
- Base URL for the GraphQL API
- Authentication method (API key header format, header name)

---

#### Section 2: Data Model

**This is a high-priority section.** Synthesize from `01-getting-started/02-the-enigma-data-model.md` and the `09-operating-location/` files.

Document Enigma's entity hierarchy:

```
Business (top-level legal entity)
  └── Brand (consumer-facing identity)
       └── Operating Location (physical address)
            ├── Revenue data (card analytics)
            ├── Foot traffic data
            ├── Contact info
            ├── Business hours
            └── ... (other attributes)
  └── People (associated individuals)
```

For each entity type:
- What it represents
- What ID type it uses (Enigma brand ID, location ID, etc.)
- How it connects to parent/child entities
- Key fields available

**Include the relationship diagram** — how to navigate from a business name/domain → brand → locations → per-location analytics. This chain is fundamental to using the API.

---

#### Section 3: Authentication & Rate Limits

Synthesize from `06-query-enigma-with-graphql/01-graphql-api-quickstart.md`, `04-resources/02-rate-limits.md`, and `06-query-enigma-with-graphql/07-graphql-api-rate-limits.md`.

Cover:
- Authentication header format (`x-api-key: <key>`)
- Rate limits (requests per second, per minute, per day — whatever tiers exist)
- Error codes for rate limiting
- Any throttling behavior

---

#### Section 4: Credit & Billing Model

Synthesize from `04-resources/03-pricing-and-credit-use.md`.

This is critical for cost planning. Cover:
- How credits are consumed (per-entity? per-query? per-field?)
- Different credit costs for different query types
- Any free/included operations
- How to estimate credit usage for batch operations

If the audit (`docs/ENIGMA_INTEGRATION_AUDIT.md`) flagged per-entity billing concerns, make sure those are reflected here.

---

#### Section 5: GraphQL API — Endpoint Inventory

This is the core reference section. For each distinct GraphQL query/mutation capability, document:

1. **What it does** (one sentence)
2. **GraphQL query/mutation signature** (the operation name, input types, return type)
3. **Key input parameters** (table format: parameter name, type, required/optional, description)
4. **Key response fields** (table format: field name, type, description)
5. **Practical example** (a complete GraphQL query with variables, and the key parts of the response)

Organize by capability domain:

##### 5.1 Business Search & Matching

Synthesize from `03-growth-and-gtm-solutions/01-search-for-a-specific-business.md`, `04-resources/01-how-enigma-searches-and-matches.md`, and `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md`.

- `search(searchInput: SearchInput!)` — the primary search query
- How `SearchInput` works (name, address, phone, EIN, domain, etc.)
- Match confidence scoring
- How to interpret multiple results

##### 5.2 Brand Data Retrieval

Synthesize from `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md` and `08-reference/02-graphql-api-reference.md`.

- Querying brand details by ID
- `namesConnection`, `locationsConnection`, `analyticsConnection`
- Navigation from brand → locations → analytics

##### 5.3 Operating Location Data

Synthesize from `09-operating-location/` (all 20 files) and `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md`.

For each data domain in `09-operating-location/`, document:
- What data is available (field names and types)
- How to query it (which connection/field on the Location type)
- Data freshness/update frequency if documented

The 20 location data domains to cover:
1. Address
2. Contact information
3. Business hours
4. Revenue / card analytics
5. Foot traffic
6. Website content
7. Social media
8. Reviews/ratings
9. ... (extract the full list from the 20 files)

Present this as a summary table with one row per domain, then detailed subsections for the most important domains (revenue, foot traffic, address at minimum).

##### 5.4 Analytics & Aggregates

Synthesize from `06-query-enigma-with-graphql/03-get-aggregate-location-counts.md` and `03-growth-and-gtm-solutions/05-assess-market-position.md`.

- Aggregate queries (location counts by geography, industry, revenue range)
- How to use aggregates for market sizing and lead list building
- The `aggregate` directive or query pattern

##### 5.5 Card Revenue Analytics

Synthesize from `04-resources/04-evaluate-card-revenue-data.md` and the existing adapter in `app/providers/enigma.py`.

- What card revenue data includes (transactions, customers, growth rates, refunds)
- Time series granularity (monthly? quarterly?)
- Data coverage and quality caveats
- How the existing adapter queries this data (include the actual GraphQL query from `app/providers/enigma.py` as a reference)

##### 5.6 Person Data

Synthesize from whatever person-related content exists in the reference docs.

- What person data is available through Enigma
- How persons relate to businesses/brands
- Query patterns for person lookup

##### 5.7 KYB Verification

Synthesize from `02-verification-and-kyb/` (all 4 files).

- What KYB packages are available (tiers)
- REST vs GraphQL — which API is used for KYB
- Request/response shapes for verification
- Task result structure

##### 5.8 Screening

Synthesize from `05-screening/` (all 6 files).

- What screening capabilities exist
- REST endpoints (not GraphQL)
- Core endpoints (create screen, check status, get results)
- Batch processing
- Decision management workflow

---

#### Section 6: What We've Built vs What's Available

Cross-reference against `docs/ENIGMA_INTEGRATION_AUDIT.md`.

Present as a coverage matrix:

| Capability | Enigma API | Our Adapter | Our Operation | Production Status |
|---|---|---|---|---|
| Business search/match | `search(searchInput)` | `enigma.search_brand()` / `match_business()` | Used internally by `card_revenue` | Called in production (indirectly) |
| Card revenue analytics | `analyticsConnection` on Brand | `enigma.get_card_analytics()` | `company.enrich.card_revenue` | Wired, check if called |
| Operating locations | `locationsConnection` on Brand | Not built | `company.enrich.locations` (directive exists) | Not started |
| Lead list building (aggregates) | Aggregate queries | Not built | Not scoped | — |
| KYB verification | REST `/verify` | Not built | Not scoped | — |
| Screening | REST screening endpoints | Not built | Not scoped | — |
| Foot traffic | Location foot traffic fields | Not built | Not scoped | — |
| Person data | Person type queries | Not built | Not scoped | — |
| ... | ... | ... | ... | ... |

Fill in from the audit. The goal is to make the gap obvious at a glance.

---

#### Section 7: Use Case Query Chains

**This section is where the reference becomes actionable.** For each of our target use cases, map out the Enigma query chain — which queries to call in what order, what IDs connect them, and what data you get at each step.

##### Use Case 1: SMB List Building for PE Firms

Goal: Find businesses in a specific geography + vertical + revenue range.

Query chain:
1. **Aggregate query** — get location counts by state/metro + NAICS + revenue range to size the market
2. **Search query** — find matching businesses by geography + industry filters
3. **Brand detail query** — for each match, get brand-level revenue and location count
4. **Location queries** — get per-location details (address, hours, revenue)

Show the actual GraphQL queries (or query shapes) for each step.

##### Use Case 2: Location-Level Revenue & Traffic Analysis

Goal: For a known company, get per-location revenue and foot traffic data.

Query chain:
1. **Search** — match company by name/domain to Enigma brand ID
2. **Brand → Locations** — get all operating locations for the brand
3. **Location → Analytics** — for each location, get card revenue and foot traffic time series

Show how to page through locations (connection pagination pattern).

##### Use Case 3: Business Discovery by Vertical/Geography

Goal: Build a targeted lead list of businesses in a specific NAICS + geography.

Query chain:
1. **Aggregate** — size the market (how many locations match the criteria?)
2. **Paginated search** — retrieve matching businesses in batches
3. **Enrichment** — for each business, get key fields (revenue, location count, years in business)

##### Use Case 4: Competitive Intelligence / Market Position

Goal: Assess a company's market position relative to peers.

Query chain:
1. **Search** — match the target company
2. **Peer identification** — use aggregate queries on the same NAICS + geography to identify peer set
3. **Comparative analytics** — compare card revenue trends across target + peers

For each use case, note:
- Estimated credit cost per entity processed (based on Section 4)
- Which steps we have adapters for and which we'd need to build
- Any rate limit concerns for batch processing

---

#### Section 8: GraphQL Schema Quick Reference

Synthesize from `08-reference/02-graphql-api-reference.md`.

A condensed version of the full schema reference:

- **Types:** list all major types (Brand, Location, Business, Person, Analytics, etc.) with their key fields
- **Connections:** list all connection types (locationsConnection, analyticsConnection, etc.) with their pagination pattern
- **Input types:** list all input types (SearchInput, etc.) with their fields
- **Directives:** list any custom directives and what they do

This should be a quick-reference, not the full schema dump. Focus on types and fields that are actually useful for our use cases.

---

#### Section 9: Error Handling & Status Codes

Synthesize from `06-query-enigma-with-graphql/06-response-status-codes.md`.

- GraphQL error shapes
- HTTP status codes
- Common error scenarios (invalid API key, rate limited, no results found, malformed query)
- How our adapter handles errors (reference `app/providers/enigma.py` error handling)

---

### Evidence standard

- Every API capability claim must reference a specific source file from `docs/api-reference-docs/enigma/`.
- Every query/mutation shape must come from the GraphQL reference docs or the existing adapter code, not from inference.
- Every field name and type must come from the data attribute reference or the GraphQL schema reference.
- If a capability is mentioned in the source docs but the details are unclear or insufficient, note it as "documented but detail insufficient — verify against live API" rather than guessing.
- The "What we've built" section must cross-reference against `docs/ENIGMA_INTEGRATION_AUDIT.md` and the actual code, not against other docs.

Commit standalone.

---

## Deliverable 2: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: created `docs/ENIGMA_API_REFERENCE.md` consolidating 61 source files into a single reference covering data model, 8+ endpoint domains, credit model, 4 use case query chains, and coverage gap matrix against our current integration. Note the section count and any source files that were empty or uninformative.

Add a last-updated timestamp at the top of each file you create or modify, in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive.
- **No new adapters, operations, or services.** Document the API, do not implement against it.
- **No API calls to Enigma.** This is a documentation consolidation exercise based on the reference files, not a live API exploration.
- **No deploy commands.** Do not push.
- **No changes to existing documentation files.** Only create the new reference doc and append to the work log.
- **No changes to `CLAUDE.md`.** The chief agent will decide if/when to reference the new doc.
- **No changes to `docs/ENIGMA_INTEGRATION_AUDIT.md`.** The audit is a separate deliverable. If you find discrepancies between the audit and the source docs, note them in the reference but do not modify the audit.
- **Do not delete or reorganize the source files** in `docs/api-reference-docs/enigma/`. The consolidated reference supplements them, it does not replace them.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Reference doc: full path, section count, total word count (approximate)
(b) Source coverage: how many of the 61 source files were read and incorporated, any that were empty or irrelevant
(c) Endpoint inventory: total distinct API capabilities documented, grouped by domain
(d) Data model: number of entity types documented, key relationship chains identified
(e) Use case chains: number of use cases mapped, estimated query steps per chain
(f) Coverage matrix: number of capabilities with existing adapters vs not built
(g) Anything to flag — especially: capabilities in the source docs that seem highly relevant but are completely undocumented in the audit, source files that contradict each other, or API features that appear deprecated or unavailable
