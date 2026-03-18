# Enigma API Reference

**Last updated:** 2026-03-18T19:42:00Z

Consolidated reference for the Enigma API surface. Source material: 61 files across `docs/api-reference-docs/enigma/`.

> **Note:** All 20 files in `09-operating-location/` are empty (0 bytes). Operating location attribute details in this reference are derived from `08-reference/01-data-attribute-reference.md`, `08-reference/02-graphql-api-reference.md` (the full SDL), and `02-verification-and-kyb/04-kyb-response-matched-data.md`.

---

## 1. Platform Overview

**Source:** `01-getting-started/01-overview.md`

Enigma is the most reliable source of data on U.S. businesses, powered by its `graph-model-1` engine. It provides structured data across business identity, card revenue analytics, foot traffic, operating locations, KYB verification, and sanctions screening. Data is accessible via a GraphQL API (programmatic) and the Enigma Console (interactive exploration).

**GraphQL API Base URL:** `https://api.enigma.com/graphql`

**Authentication:** Include your API key in the `x-api-key` header on every request:

```
x-api-key: YOUR_API_KEY
Content-Type: application/json
```

**Source:** `06-query-enigma-with-graphql/01-graphql-api-quickstart.md`, `08-reference/02-graphql-api-reference.md`

---

## 2. Data Model

**Source:** `01-getting-started/02-the-enigma-data-model.md`, `08-reference/02-graphql-api-reference.md`

### Entity Hierarchy

Enigma's data model has three core entity types, not the typical "business > brand > location" hierarchy suggested by some guides. The three entities are peers connected by observed relationships:

```
Brand (consumer-facing identity)
  ├── names, websites, industries
  ├── operatingLocations → OperatingLocation[]
  ├── legalEntities → LegalEntity[]
  ├── affiliatedBrands → Brand[]
  ├── cardTransactions (brand-level aggregate revenue)
  └── activities (high-risk compliance flags)

Operating Location (physical/virtual business site)
  ├── names, addresses, phoneNumbers
  ├── brands → Brand[]
  ├── legalEntities → LegalEntity[]
  ├── cardTransactions (location-level revenue)
  ├── ranks (competitive position vs local peers)
  ├── operatingStatuses (Open/Closed/Temporarily Closed/Unknown)
  ├── reviewSummaries (customer review aggregates)
  ├── technologiesUsed
  ├── websites → Website[]
  └── roles → Role[] (people with contact info)

Legal Entity (government-recognized entity)
  ├── names, types (LLC, Corporation, Sole Proprietorship, etc.)
  ├── brands → Brand[]
  ├── operatingLocations → OperatingLocation[]
  ├── registeredEntities → RegisteredEntity[]
  ├── registrations → Registration[] (SoS filings)
  ├── persons → Person[] (officers, contacts)
  ├── tins → TIN[]
  ├── bankruptcies
  ├── roles → Role[]
  └── watchlistEntries
```

### Entity Types & IDs

| Entity | GraphQL Type | ID Type | Description |
|---|---|---|---|
| Brand | `Brand` | UUID (`id`, also `enigmaId`) | Consumer-facing identity — trade names, logos, marketing identity. Operates across multiple locations. |
| Operating Location | `OperatingLocation` | UUID (`id`) | Physical or virtual site where business is conducted. Bridges brands and legal entities. |
| Legal Entity | `LegalEntity` | UUID (`id`, also `enigmaId`) | Government-recognized entity — taxation, compliance, legal accountability. |
| Person | `Person` | UUID (`id`) | Individual associated with a legal entity (officer, contact). Fields: `firstName`, `lastName`, `fullName`, `dateOfBirth`. |
| Registered Entity | `RegisteredEntity` | UUID (`id`) | SoS registration record. Fields: `name`, `registeredEntityType`, `formationDate`. |
| Registration | `Registration` | UUID (`id`) | State-level filing. Fields: `registrationState`, `status`, `subStatus`, `fileNumber`, `issueDate`. |
| Role | `Role` | UUID (`id`) | Person's role at a business. Fields: `jobTitle`, `jobFunction`, `managementLevel`, plus connections to `emailAddresses`, `phoneNumbers`. |

### Relationship Navigation Chain

The fundamental query chain for going from "company name" to actionable analytics:

```
Company Name/Domain
  → search(name/website) → Brand (id)
    → Brand.operatingLocations → OperatingLocation[] (per-location)
      → OperatingLocation.cardTransactions (location-level revenue time series)
      → OperatingLocation.ranks (competitive position)
      → OperatingLocation.addresses (physical address)
      → OperatingLocation.reviewSummaries (customer reviews)
    → Brand.cardTransactions (brand-level aggregate revenue)
    → Brand.legalEntities → LegalEntity[]
      → LegalEntity.registeredEntities → RegisteredEntity[]
        → RegisteredEntity.registrations → Registration[] (SoS status)
      → LegalEntity.persons → Person[]
```

### Complex Real-World Structures

Enigma's model handles: franchises (McDonald's: 300+ legal entities), multi-brand corporations (different brands under one legal entity), affiliated brands, agents/professionals, people-as-brands, and legal-entities-as-brands.

**Source:** `01-getting-started/02-the-enigma-data-model.md`

---

## 3. Authentication & Rate Limits

### Authentication

**Source:** `06-query-enigma-with-graphql/01-graphql-api-quickstart.md`, `08-reference/02-graphql-api-reference.md`

All GraphQL API requests require the `x-api-key` header. The Screening API additionally requires an `Account-Name` header.

### GraphQL API Rate Limits

**Source:** `06-query-enigma-with-graphql/07-graphql-api-rate-limits.md`, `04-resources/02-rate-limits.md`

| Plan | RPS | Burst Limit | Daily Request Quota |
|---|---|---|---|
| Trial | 10 | 20 | 100,000 |
| Pro | 50 | 100 | 500,000 |
| Max | 50 | 100 | 500,000 |
| Enterprise | 100 | 200 | No limit |

Returns `429 Slow Down` when limits are exceeded.

### MCP Tool Rate Limits (Pro/Max plans)

**Source:** `04-resources/02-rate-limits.md`

| Tool | Daily | Monthly |
|---|---|---|
| `search_business` | 500 | 8,000 |
| `get_brand_locations` | 500 | 8,000 |
| `get_brand_legal_entities` | 500 | 8,000 |
| `get_brand_card_analytics` | 500 | 8,000 |
| `search_gov_archive` | 500 | 6,000 |
| `generate_brands_segment` | 100 | 1,000 |
| `generate_locations_segment` | 100 | 1,000 |
| `search_kyb` | 100 | 2,000 |
| `search_negative_news` | 100 | 2,000 |

GraphQL API rate limits are independent of MCP tool rate limits and KYB API rate limits.

### Large Responses

**Source:** `06-query-enigma-with-graphql/06-response-status-codes.md`

Responses over 6 MB are delivered via HTTP `302` redirect to a pre-signed AWS S3 URL (in the `Location` header). Most HTTP clients follow redirects automatically.

---

## 4. Credit & Billing Model

**Source:** `04-resources/03-pricing-and-credit-use.md`

### Core Billing Rule

Credits are charged **per entity returned**, not per attribute requested. If you request multiple attributes for the same entity in a single query, you pay **once per entity at the tier of the most expensive attribute** returned.

### Pricing Tiers

| Tier | Credit Cost | Attributes |
|---|---|---|
| **Free** | 0 | `LegalEntityName`, `LegalEntityType` |
| **Core** | 1 | `Address`, `BrandIsMarketable`, `BrandLocationDescription`, `BrandName`, `EmailAddress`, `Industry`, `OperatingLocationIsMarketable`, `OperatingLocationLocationType`, `OperatingLocationName`, `OperatingLocationOperatingStatus`, `Person`, `PhoneNumber`, `Website`, `WebsiteOnlinePresence` |
| **Plus** | 3 | `AddressDeliverability`, `BrandActivity`, `BrandCardTransaction`, `BrandRevenueQuality`, `OperatingLocationCardTransaction`, `OperatingLocationRank`, `OperatingLocationRevenueQuality`, `ReviewSummary`, `Role`, `TxnMerchant`, `WebsiteContent` |
| **Premium** | 5* | `LegalEntityBankruptcy`, `OperatingLocationTechnologiesUsed`, `RegisteredEntity`, `Registration`, `Tin`, `WatchlistEntry`, `WebsiteTechnologiesUsed` |

*Premium credit cost is documented but exact per-credit value is not specified in source docs — verify via `_schemaExtended` introspection query or account dashboard.*

### Credit Calculation Examples

| Scenario | Credits Used |
|---|---|
| 1 core attribute, 1 entity | 1 |
| 1 core attribute, 10 entities | 10 |
| 2 core attributes, 1 entity | 1 (same tier, same entity) |
| 1 core + 1 plus attribute, 2 entities | 6 (2 × 3 credits for plus tier) |
| Brand (core) + 10 nested OperatingLocations with cardTransactions (plus) | 31 (1 core + 10 × 3 plus) |

### Cost Planning Implications

- **Nested queries are expensive.** Querying a brand + all its locations + per-location analytics charges per entity at each level.
- **Our current `card_revenue` operation** makes 2 GraphQL calls: search (~1 credit) + analytics (~3 credits for plus-tier card transactions) = ~4 credits per company.
- **Our `locations` operation** queries brand + N locations: ~1 + N credits (core tier for addresses/status) or ~1 + 3N credits if requesting card transactions per location.
- **Batch operations** should be carefully estimated. 1,000 companies × full enrichment (search + analytics + locations) could consume 10,000+ credits.

**Source:** `04-resources/03-pricing-and-credit-use.md`, `docs/ENIGMA_INTEGRATION_AUDIT.md` (Section 7)

---

## 5. GraphQL API — Endpoint Inventory

### 5.1 Business Search & Matching

**Source:** `03-growth-and-gtm-solutions/01-search-for-a-specific-business.md`, `04-resources/01-how-enigma-searches-and-matches.md`, `06-query-enigma-with-graphql/01-graphql-api-quickstart.md`, `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md`

#### `search(searchInput: SearchInput!)` — Primary Search Query

Returns `[SearchUnion]` where `SearchUnion = Brand | OperatingLocation | LegalEntity`.

**SearchInput Fields:**

| Field | Type | Required | Description |
|---|---|---|---|
| `entityType` | `EntityType` | No (default: `BRAND`) | `BRAND`, `OPERATING_LOCATION`, or `LEGAL_ENTITY` |
| `id` | `String` | No | Entity ID — takes precedence over all other fields |
| `name` | `String` | No | Business name (customer-facing, not legal). Typo-tolerant. |
| `website` | `String` | No | Primary domain (e.g., `enigma.com`). Characters after `/` excluded. |
| `address` | `AddressInput` | No | `{street1, street2, city, state, postalCode}` |
| `phoneNumber` | `String` | No | 10-digit US phone (`1234567890` or `123-456-7890`) |
| `person` | `PersonInput` | No | `{firstName, lastName, dateOfBirth, address, tin}` |
| `tin` | `TinInput` | No | `{tin: "123456789", tinType: TIN}` — requires `name` also provided |
| `prompt` | `String` | No | Semantic business description (e.g., "pizza restaurant in new york"). Only for `BRAND` entity type. |
| `matchThreshold` | `Float` | No | Confidence threshold 0.0–1.0 |
| `conditions` | `Conditions` | No | `{filter, orderBy, limit, pageToken}` for result filtering/pagination |
| `output` | `OutputSpec` | No | Background task output config (`{filename, format, s3Path}`) |

**Minimum required:** At least one of `name`, `website`, or `person.firstName` + `person.lastName`.

**Matching Algorithm:** Two-stage process — Retrieval (fast index to surface candidates) + Ranking (ML model scoring match probability). Precision: ~94% for all entity types.

**Example — Search by name and website:**

```graphql
query SearchBrand($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      names(first: 1) { edges { node { name } } }
      count(field: "operatingLocations")
    }
  }
}
```

Variables:
```json
{
  "searchInput": {
    "entityType": "BRAND",
    "name": "Starbucks",
    "website": "starbucks.com"
  }
}
```

**Our adapter implementation:** `enigma.match_business()` in `app/providers/enigma.py` uses `SEARCH_BRAND_QUERY` which searches by `entityType: "BRAND"` with name and optional website, returning `id`, `enigmaId`, first brand name, and `count(field: "operatingLocations")`.

### 5.2 Brand Data Retrieval

**Source:** `06-query-enigma-with-graphql/01-graphql-api-quickstart.md`, `06-query-enigma-with-graphql/02-search-and-get-data-via-api.md`, `08-reference/02-graphql-api-reference.md`

Once you have a Brand ID from search, you can retrieve detailed data through the Brand type's connections:

| Connection | Returns | Pagination | Description |
|---|---|---|---|
| `names(first: N)` | `BrandNameConnection` | Cursor-based | All names for the brand |
| `websites(first: N)` | `BrandWebsiteConnection` | Cursor-based | Associated websites |
| `operatingLocations(first: N, conditions)` | `BrandOperatingLocationConnection` | Cursor-based | Physical locations |
| `legalEntities(first: N)` | `BrandLegalEntityConnection` | Cursor-based | Legal entity associations |
| `affiliatedBrands(first: N)` | `BrandBrandConnection` | Cursor-based | Related brands |
| `cardTransactions(first: N, conditions)` | `BrandCardTransactionConnection` | Cursor-based | Revenue analytics |
| `industries(first: N)` | `BrandIndustryConnection` | Cursor-based | NAICS/SIC/Enigma industry codes |
| `revenueQualities(first: N)` | `BrandRevenueQualityConnection` | Cursor-based | Revenue data quality warnings |
| `locationDescriptions(first: N)` | `BrandLocationDescriptionConnection` | Cursor-based | Geographic summary |
| `isMarketables(first: N)` | `BrandIsMarketableConnection` | Cursor-based | Marketability flag |
| `activities(first: N)` | `BrandActivityConnection` | Cursor-based | High-risk activity flags |

**Aggregation functions** available on Brand: `count(field)`, `sum(field)`, `min(field)`, `max(field)`, `avg(field)`, `collect(field, separator)`, `minDateTime(field)`, `maxDateTime(field)`.

**Example — Brand by ID with locations and legal entities:**

```graphql
query AnalyzeBrand($searchInput: SearchInput!, $cardTransactionConditions: ConnectionConditions!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      names(first: 1) { edges { node { name } } }
      operatingLocations(first: 50) {
        edges {
          node {
            id
            addresses(first: 1) { edges { node { fullAddress } } }
            cardTransactions(first: 1, conditions: $cardTransactionConditions) {
              edges { node { projectedQuantity } }
            }
          }
        }
      }
      legalEntities(first: 10) {
        edges {
          node {
            registeredEntities {
              edges {
                node {
                  registeredEntityType
                  formationDate
                  name
                }
              }
            }
          }
        }
      }
    }
  }
}
```

### 5.3 Operating Location Data

**Source:** `08-reference/01-data-attribute-reference.md`, `08-reference/02-graphql-api-reference.md`

> **Note:** All 20 files in `09-operating-location/` are empty (0 bytes). The data domains below are derived from the GraphQL SDL and attribute reference.

#### Operating Location Data Domains

| # | Domain | GraphQL Connection/Field | Key Fields | Tier |
|---|---|---|---|---|
| 1 | Name | `names` | `name` | Core |
| 2 | Address | `addresses` | `fullAddress`, `streetAddress1`, `streetAddress2`, `city`, `state`, `zip`, `latitude`, `longitude`, `county`, `msa`, `h3Index` | Core |
| 3 | Address Deliverability | `addresses → deliverabilities` | `rdi`, `deliveryType`, `deliverable`, `virtual` | Plus |
| 4 | Card Transactions | `cardTransactions` | `quantityType`, `period`, `projectedQuantity`, `rawQuantity`, `periodStartDate`, `periodEndDate` | Plus |
| 5 | Email Address | Via `roles → emailAddresses` | `emailAddress` | Core |
| 6 | Is Marketable | `isMarketables` | `isMarketable: Boolean` | Core |
| 7 | Location Type | `locationTypes` | `locationType` (retail, office, etc.) | Core |
| 8 | Online Presence | Via `websites → onlinePresences` | `hasOnlineSales` | Core |
| 9 | Operating Status | `operatingStatuses` | `operatingStatus` (Open/Closed/Temporarily Closed/Unknown) | Core |
| 10 | Phone Number | `phoneNumbers` | `phoneNumber` (12-digit string) | Core |
| 11 | Rank | `ranks` | `position`, `cohortSize`, `quantityType`, `period`, `periodStartDate` | Plus |
| 12 | Registered Entity | Via `legalEntities → registeredEntities` | `name`, `registeredEntityType`, `formationDate` | Premium |
| 13 | Registration | Via `legalEntities → registeredEntities → registrations` | `registrationState`, `status`, `fileNumber`, `issueDate` | Premium |
| 14 | Revenue Quality | `revenueQualities` | `issueReason`, `issueSeverity`, `issueDescription` | Plus |
| 15 | Review Summary | `reviewSummaries` | `reviewCount`, `reviewScoreAvg`, `firstReviewDate`, `lastReviewDate` | Plus |
| 16 | Role (People/Contacts) | `roles` | `jobTitle`, `jobFunction`, `managementLevel`, plus `emailAddresses`, `phoneNumbers` connections | Plus |
| 17 | Technologies Used | `technologiesUseds` | `technology`, `category` | Premium |
| 18 | Watchlist Entry | Via `legalEntities → watchlistEntries` | `watchlistName` | Premium |
| 19 | Website | `websites` | `website`, `subdomain`, `domain`, `topLevelDomain` | Core |
| 20 | Website Content | Via `websites → websiteContents` | `httpStatusCode`, `faviconUrl`, `websiteAvailability` | Plus |

#### Key Domain Details

**Card Transactions (Location-Level)**

The `OperatingLocationCardTransaction` type includes both `rawQuantity` (observed card data) and `projectedQuantity` (extrapolated full revenue estimate). Filter by `quantityType` and `period` using `ConnectionConditions`:

- `quantityType` values: `card_revenue_amount`, `card_revenue_yoy_growth`, `card_customers_average_daily_count`, `card_transactions_count`, `avg_transaction_size`, `refunds_amount`
- `period` values: `1m` (monthly), `12m` (trailing 12 months)

**Ranks (Competitive Position)**

`OperatingLocationRank` shows how a location ranks against local peers in the same Enigma industry and geographic area. Percentile formula: `((cohortSize - position + 1) / cohortSize) * 100`. Example: Position 1 of 565 = 100th percentile = market leader.

**Source:** `03-growth-and-gtm-solutions/05-assess-market-position.md`

**Review Summaries**

`ReviewSummary` provides aggregated customer review data: `reviewCount`, `reviewScoreAvg` (e.g., 4.4 stars), date range of reviews.

**OperatingLocationCache**

The SDL also defines `OperatingLocationCache` — a denormalized cache type with pre-joined fields: `name`, `fullAddress`, `operatingStatus`, `website`, `phoneNumber`, `latitude`, `longitude`, `latest12mCardRevenueProjected`, `latest12mYoyGrowthProjected`, `rankPosition`, `rankCohortSize`, `primaryBrandNaicsIndustry`, `primaryBrandEnigmaIndustry`, `hasRolePhoneNumber`, `hasRoleEmailAddress`. This may offer a more efficient query path for bulk data retrieval — documented but detail insufficient for query patterns; verify against live API.

### 5.4 Analytics & Aggregates

**Source:** `06-query-enigma-with-graphql/03-get-aggregate-location-counts.md`

#### `aggregate(searchInput: SearchInput!)` — Aggregate Query

Returns `AggregateResult` with `count(field)` function. Only supports `entityType: OPERATING_LOCATION`.

**Supported count fields:** `brand`, `operatingLocation`, `legalEntity`

**Supported conditions filter:** Only `operatingStatuses.operatingStatus` EQ filter (e.g., filter for "Open" locations).

**Example — Count brands and locations in a city:**

```graphql
query Aggregate {
  aggregate(
    searchInput: {
      entityType: OPERATING_LOCATION
      address: { city: "NEW YORK", state: "NY" }
    }
  ) {
    brandsCount: count(field: "brand")
    locationsCount: count(field: "operatingLocation")
  }
}
```

**Common use cases:**
- Count total brands/locations in a geographic area
- Count open vs all operating locations
- Count legal entities behind locations matching criteria
- Market sizing before running expensive per-entity searches

**Limitations:** The `aggregate` query is more constrained than `search` — it only works with `OPERATING_LOCATION` entity type, only supports address-based filtering, and the only additional condition filter is operating status.

### 5.5 Card Revenue Analytics

**Source:** `04-resources/04-evaluate-card-revenue-data.md`, `app/providers/enigma.py`

#### Data Description

Card revenue data represents **card-only transaction revenue** — not total business revenue. Enigma extrapolates from observed card panel data to produce `projectedQuantity` estimates.

**Available metrics (via `quantityType`):**

| quantityType | Description |
|---|---|
| `card_revenue_amount` | Total card revenue in dollars |
| `card_revenue_yoy_growth` | Ratio of current period to same period prior year |
| `card_customers_average_daily_count` | Average unique daily customers |
| `card_transactions_count` | Total number of card transactions |
| `avg_transaction_size` | Average transaction amount in dollars |
| `refunds_amount` | Total refunds in dollars |

**Time periods:** `1m` (monthly granularity) and `12m` (trailing 12-month aggregate).

#### Data Quality Caveats

- 51% of brands within ±20% error vs ground truth
- 67% within ±30% error
- High precision (>80%) for: $0–$100k and $1M+ revenue ranges
- Moderate precision (>60%) for: $100k–$1M range
- **Best for:** Retail, restaurants, personal services (high card adoption)
- **Use as revenue floor:** Professional services, healthcare (mixed card adoption)
- **Not reliable for:** B2B software, wholesale (low card adoption) — use alternative metrics

#### Our Adapter's Query

`enigma.get_card_analytics()` in `app/providers/enigma.py` uses `GET_BRAND_ANALYTICS_QUERY` which fetches 12 aliased `cardTransactions` connections in a single query — 6 metric types × 2 periods (1m time series + 12m annual aggregate):

```graphql
query GetBrandAnalytics(
  $searchInput: SearchInput!
  $monthsBack: Int!
  $cardRevenueAmountConditions1m: ConnectionConditions!
  $cardRevenueAmountConditions12m: ConnectionConditions!
  $cardRevenueYoyGrowthConditions1m: ConnectionConditions!
  $cardRevenueYoyGrowthConditions12m: ConnectionConditions!
  $cardCustomersAvgDailyCountConditions1m: ConnectionConditions!
  $cardCustomersAvgDailyCountConditions12m: ConnectionConditions!
  $cardTransactionsCountConditions1m: ConnectionConditions!
  $cardTransactionsCountConditions12m: ConnectionConditions!
  $avgTransactionSizeConditions1m: ConnectionConditions!
  $avgTransactionSizeConditions12m: ConnectionConditions!
  $refundsAmountConditions1m: ConnectionConditions!
  $refundsAmountConditions12m: ConnectionConditions!
) {
  search(searchInput: $searchInput) {
    ... on Brand {
      cardRevenueAmount1m: cardTransactions(first: $monthsBack, conditions: $cardRevenueAmountConditions1m) {
        edges { node { projectedQuantity periodStartDate } }
      }
      cardRevenueAmount12m: cardTransactions(first: 1, conditions: $cardRevenueAmountConditions12m) {
        edges { node { projectedQuantity } }
      }
      # ... (10 more aliased connections for the other 5 metrics × 2 periods)
    }
  }
}
```

Each `ConnectionConditions` uses `filter: { AND: [{EQ: ["period", "1m"]}, {EQ: ["quantityType", "card_revenue_amount"]}] }` pattern.

**Output (`CardRevenueOutput`):** Returns 6 annual scalars + 6 monthly time series arrays, plus `enigma_brand_id`, `brand_name`, `location_count`.

### 5.6 Person Data

**Source:** `08-reference/02-graphql-api-reference.md`, `01-getting-started/02-the-enigma-data-model.md`

Person data in Enigma is accessed through the **Legal Entity → Person** and **Role** paths, not as a standalone searchable entity type.

**Person type fields:** `firstName`, `lastName`, `fullName`, `dateOfBirth`, plus connection to `legalEntities`.

**Role type fields:** `jobTitle`, `jobFunction`, `managementLevel`, plus connections to `emailAddresses`, `phoneNumbers`, `operatingLocations`, `legalEntities`, `registrations`.

**Access patterns:**
1. `LegalEntity.persons` — officers and contacts from SoS filings
2. `OperatingLocation.roles` — people with roles at a specific location (with email/phone)
3. `Brand.operatingLocations → roles` — people associated with a brand through its locations
4. `SearchInput.person` — search for entities by a person's name (cross-entity linking)

**Note:** The `SearchInput.person` field enables searching for brands, locations, or legal entities by a person's name — you're not searching for the person directly, but for business entities associated with that person.

Person data at the Role level (with `emailAddresses` and `phoneNumbers`) is **Plus tier** pricing. Person names via SoS filings (through `LegalEntity.persons`) are **Core tier**.

### 5.7 KYB Verification

**Source:** `02-verification-and-kyb/01-kyb-packages.md`, `02-verification-and-kyb/03-kyb-response-task-results.md`, `02-verification-and-kyb/04-kyb-response-matched-data.md`

KYB is a **REST API** (not GraphQL). It verifies business identity against Secretary of State records, IRS data, and sanctions lists.

#### API Endpoint

```
POST https://api.enigma.com/v2/kyb/verify
```

Authentication: `x-api-key` header (same key as GraphQL).

#### Packages

| Package | Default In | Key Capabilities |
|---|---|---|
| **`identify`** | v1 | Name matching, address matching, entity enrichment, industry classification |
| **`verify`** | v2 | Everything in `identify` + person verification, domestic registration check, registration status/sub-status |

Both respond in under 2 seconds.

#### Standard Verification Tasks

| Task | Result Values | Package |
|---|---|---|
| `name_verification` | `name_exact_match`, `name_match`, `name_not_verified` | Both |
| `sos_name_verification` | Same values, SoS records only | Both |
| `address_verification` | `address_exact_match`, `address_match`, `address_not_verified` | Both |
| `sos_address_verification` | Same values, SoS records only | Both |
| `person_verification` | `person_match`, `person_not_verified` | `verify` only |
| `domestic_registration` | `domestic_active`, `domestic_unknown`, `domestic_inactive`, `domestic_not_found` | `verify` only |

#### Add-On Tasks (plan-level add-on, requested via `attrs` parameter)

| Add-On | Description | Result Values |
|---|---|---|
| **TIN Verification** | Verifies EIN + business name against IRS | `tin_verified`, `tin_invalid`, `not_completed`, `tin_not_verified` |
| **SSN Verification** | Verifies SSN + last name against IRS | `ssn_verified`, `ssn_invalid`, `not_completed`, `ssn_not_verified` |
| **Watchlist Screening** | OFAC + all US sanctions lists | `watchlist_no_hits`, `watchlist_hits` |

#### KYB Response Data Structure

The `data` object returns:
- `registered_entities[]` → `registrations[]` → `persons[]` + `addresses[]`
- `brands[]` → `industries[]` + `operating_locations[]` → `addresses[]`

Add-on attributes available in KYB responses: `bankruptcies`, `card_transactions` (avg_transaction_size, count, revenue, YoY growth, prior period growth, avg daily customers, refunds, revenue_quality), `operating_status`, `phone_numbers`.

### 5.8 Screening

**Source:** `05-screening/01-customer-and-transaction-screening.md`, `05-screening/02-screening-api-overview.md`, `05-screening/03-core-screening-endpoints.md`

Screening is a **REST API** for sanctions and watchlist screening. Enigma processes over 1 billion screening requests per month.

#### API Endpoint

```
POST https://api.enigma.com/evaluation/sanctions/screen
```

Authentication: `x-api-key` + `Account-Name` headers.

#### Search Types

| Type | Description |
|---|---|
| `ENTITY` | Structured entity screening (person or organization) against sanctions lists |
| `TEXT` | Unstructured text screening (not yet publicly available) |
| `LLM_ENTITY` | AI-enhanced entity screening with live web search |
| `LLM_TEXT` | AI-enhanced text screening with live web search |

#### Entity Description Fields

| Field | Description |
|---|---|
| `person_name` | Full name of the individual |
| `org_name` | Organization name |
| `dob` | Date of birth (`yyyymmdd`) |
| `address` | Street address, city, state, postal code |
| `country_of_affiliation` | Country affiliation |

#### Configuration

Requests support `configuration_overrides` with:
- `alert_threshold` (0.0–1.0) — score above which a hit generates an alert
- `hit_threshold` (0.0–1.0) — minimum score to be included as a hit
- `max_results` — maximum hits returned
- `weights` — per-attribute weights (person_name, dob, country_of_affiliation, address, org_name)
- `list_groups` — which sanctions lists to screen against (e.g., `pos/sdn/all`, `pos/non_sdn/all`)

#### Response Structure

```json
{
  "alert": true,
  "request_id": "uuid",
  "search_results": [{
    "alert": true,
    "hits": [{
      "score": 0.8354,
      "alert": true,
      "attributes": {
        "person_name": { "value": "JOHN DESMOND HANAFIN", "score": 0.6708 },
        "dob": { "value": "19740710", "score": 1.0 }
      },
      "entity": { "id": "ofac/sdn/43085" }
    }]
  }]
}
```

#### Entity Lookup

```
POST https://api.enigma.com/evaluation/sanctions/entity/{provider}/{collection}/{record_id}/{format}
```

Format options: `raw`, `display`, `structured`, `attributes`.

#### Key Advantages

- Reduces false positive alerts by ≥80% vs conventional solutions
- Sub-100ms P95 response time
- Supports custom watchlists and case managers

### 5.9 Enrichment Query

**Source:** `08-reference/02-graphql-api-reference.md`

The GraphQL schema includes an `enrich` query:

```graphql
enrich(enrichmentInput: EnrichmentInput!): [SearchUnion]
```

This appears to be the programmatic equivalent of the Console's batch enrichment feature. Documentation detail is insufficient for the exact `EnrichmentInput` shape — verify against live API or `_schemaExtended` introspection.

**Console-based enrichment** (documented in `03-growth-and-gtm-solutions/02-enrich-customer-and-prospect-lists.md`) supports CSV/Parquet input with entity type selection (Brands, Operating Locations, People/Contacts, Legal Entities). Processing time: 5–20 min typical, >1M rows may take longer.

### 5.10 GraphQL Directives

**Source:** `06-query-enigma-with-graphql/05-directives.md`

Custom directives for transforming field values within queries, applied to the special `_fn` field:

| Directive | Description | Arguments |
|---|---|---|
| `@coalesce` | First non-null value from referenced fields | `ref` or `refs` |
| `@compact` | Remove nulls from array | `ref` or `refs` |
| `@slice` | Subset of array/string by index | `start`, `end` |
| `@trim` | Strip whitespace | `ref` or `refs` |
| `@upper` | Convert to uppercase | `ref` or `refs` |
| `@lower` | Convert to lowercase | `ref` or `refs` |
| `@map` | Extract nested field from each array element | `ref`/`refs`, `field` |
| `@join` | Join array elements into string | `ref`/`refs`, `sep` |
| `@include` | Conditionally include field (standard GraphQL) | `if: Boolean!` |
| `@skip` | Conditionally skip field (standard GraphQL) | `if: Boolean!` |

Directives can be **chained** left-to-right. The first directive uses `ref`/`refs` to read data; subsequent directives operate on the previous output. Use `@skip(if: true)` on source fields to keep responses clean.

---

## 6. What We've Built vs What's Available

**Source:** `docs/ENIGMA_INTEGRATION_AUDIT.md`, `app/providers/enigma.py`, `app/services/company_operations.py`

### Coverage Matrix

| Capability | Enigma API | Our Adapter | Our Operation | Production Status |
|---|---|---|---|---|
| **Business search/match** | `search(searchInput)` on Brand | `enigma.match_business()` — `SEARCH_BRAND_QUERY` | Used internally by `card_revenue` and `locations` | Called in production (indirectly) |
| **Card revenue analytics** | `cardTransactions` on Brand (12 aliased connections) | `enigma.get_card_analytics()` — `GET_BRAND_ANALYTICS_QUERY` | `company.enrich.card_revenue` | Wired at `execute_v1.py:158`, has been called in production |
| **Operating locations** | `operatingLocations` on Brand | `enigma.get_brand_locations()` — `GET_BRAND_LOCATIONS_QUERY` | `company.enrich.locations` | Wired at `execute_v1.py:159`, **never called in production** |
| **Location-level card transactions** | `cardTransactions` on OperatingLocation | Not built | Not scoped | — |
| **Location competitive ranks** | `ranks` on OperatingLocation | Not built | Not scoped | — |
| **Location reviews** | `reviewSummaries` on OperatingLocation | Not built | Not scoped | — |
| **Legal entities** | `legalEntities` on Brand | Not built | Not scoped | — |
| **Registered entities/registrations** | `registeredEntities` on LegalEntity | Not built | Not scoped | — |
| **Person/Role data** | `persons` on LegalEntity, `roles` on OperatingLocation | Not built | Not scoped | — |
| **Technologies used** | `technologiesUseds` on OperatingLocation/Website | Not built | Not scoped | — |
| **Semantic prompt search** | `search(prompt: "...")` on Brand | Not built | Not scoped | — |
| **Aggregate counts** | `aggregate(searchInput)` | Not built | Not scoped | — |
| **Batch enrichment** | `enrich(enrichmentInput)` / Console CSV | Not built | Not scoped | — |
| **KYB verification** | REST `POST /v2/kyb/verify` | Not built | Not scoped | — |
| **Screening** | REST `POST /evaluation/sanctions/screen` | Not built | Not scoped | — |
| **Affiliated brands** | `affiliatedBrands` on Brand | Not built | Not scoped | — |
| **Industry classification** | `industries` on Brand | Not built | Not scoped | — |
| **Watchlist entries** | `watchlistEntries` via LegalEntity | Not built | Not scoped | — |
| **Bankruptcy data** | `bankruptcies` on LegalEntity | Not built | Not scoped | — |

### Adapter Function Summary

| Function | GraphQL Query | Returns | Status |
|---|---|---|---|
| `match_business(api_key, company_name, company_domain)` | `SEARCH_BRAND_QUERY` | `{enigma_brand_id, brand_name, location_count}` | Production |
| `get_card_analytics(api_key, brand_id, months_back)` | `GET_BRAND_ANALYTICS_QUERY` | 6 annual scalars + 6 monthly series | Production |
| `get_brand_locations(api_key, brand_id, limit, operating_status_filter)` | `GET_BRAND_LOCATIONS_QUERY` | Location list with addresses + status | Wired, never called |

### Integration Gaps (High-Value per Audit)

Per `docs/ENIGMA_INTEGRATION_AUDIT.md` Section 8:

1. **High-value, low-effort:** Per-location card transactions and reviews — just extend existing location queries
2. **Medium-effort:** General business enrichment (aggregate NAICS/geo/revenue), semantic lead lists (`prompt` search), legal entities, market rank
3. **Low-priority:** KYB verification, screening — different use case from our GTM/enrichment focus

### Discrepancy Note

The audit states Trigger.dev has zero Enigma references — no blueprints include Enigma operations. This means Enigma enrichment can only be triggered via direct `/api/v1/execute` calls, not through the pipeline orchestration system.

---

## 7. Use Case Query Chains

### Use Case 1: SMB List Building for PE Firms

**Goal:** Find businesses in a specific geography + vertical + revenue range.

| Step | Query | Input | Output | Credits (est.) |
|---|---|---|---|---|
| 1. Market sizing | `aggregate` | `address: {state: "TX"}` + operating status filter | Brand count, location count | 0 (aggregate is free or low-cost — verify) |
| 2. Discover brands | `search` with `prompt` + `address` + `conditions.filter` on revenue | `prompt: "mexican restaurant"`, `address: {state: "TX"}`, revenue GT filter | Brand IDs, names, location counts | 1 credit per brand returned |
| 3. Brand detail | `search` by brand ID → `cardTransactions`, `industries` | Brand ID from step 2 | Revenue, YoY growth, industry codes | 3 credits per brand (plus tier for card transactions) |
| 4. Location detail | Brand → `operatingLocations` → `addresses`, `cardTransactions`, `ranks` | Brand ID | Per-location address, revenue, rank | 3 credits per location (plus tier) |

**What we have:** Steps 2 and 3 are partially covered by `match_business` + `get_card_analytics`. Steps 1 and 4 require new adapter functions.

```graphql
# Step 1: Market sizing
query Aggregate {
  aggregate(
    searchInput: {
      entityType: OPERATING_LOCATION
      address: { state: "TX" }
    }
  ) {
    brandsCount: count(field: "brand")
    locationsCount: count(field: "operatingLocation")
  }
}

# Step 2: Discover brands (semantic search)
query DiscoverBrands($searchInput: SearchInput!, $revenueConditions: ConnectionConditions!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      names(first: 1) { edges { node { name } } }
      count(field: "operatingLocations")
      cardTransactions(first: 1, conditions: $revenueConditions) {
        edges { node { projectedQuantity } }
      }
    }
  }
}
# Variables: { searchInput: { prompt: "mexican restaurant", entityType: BRAND, address: { state: "TX" } }, revenueConditions: { filter: { AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_revenue_amount"]}] } } }
```

### Use Case 2: Location-Level Revenue & Traffic Analysis

**Goal:** For a known company, get per-location revenue and competitive ranking.

| Step | Query | Input | Output | Credits (est.) |
|---|---|---|---|---|
| 1. Match company | `search` by name/domain | Company name + domain | Brand ID | 1 |
| 2. Get locations | Brand → `operatingLocations` with addresses | Brand ID, `first: 100` | Location IDs, addresses, status | 1 per location (core) |
| 3. Location analytics | Per-location `cardTransactions` + `ranks` | Location ID or nested query | Revenue time series, competitive rank | 3 per location (plus) |

**Pagination pattern for locations:**

```graphql
query GetBrandLocations($searchInput: SearchInput!, $after: String) {
  search(searchInput: $searchInput) {
    ... on Brand {
      operatingLocations(first: 100, after: $after) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            names(first: 1) { edges { node { name } } }
            addresses(first: 1) {
              edges {
                node { fullAddress city state zip latitude longitude }
              }
            }
            operatingStatuses(first: 1) { edges { node { operatingStatus } } }
            cardTransactions(
              conditions: { filter: { AND: [{EQ: ["period", "12m"]}, {EQ: ["quantityType", "card_revenue_amount"]}] } }
              first: 1
            ) { edges { node { projectedQuantity } } }
            ranks(first: 1) {
              edges { node { position cohortSize quantityType period } }
            }
          }
        }
      }
    }
  }
}
```

**What we have:** Steps 1-2 are covered by `match_business` + `get_brand_locations`. Step 3 (per-location card transactions and ranks) is not built.

**Rate limit concern:** A brand with 1,000+ locations requires 10+ paginated requests. At Pro tier (50 RPS), this is feasible. Credit cost: ~3,000 credits for 1,000 locations at plus tier.

### Use Case 3: Business Discovery by Vertical/Geography

**Goal:** Build a targeted lead list of businesses in a specific NAICS + geography.

| Step | Query | Input | Output | Credits (est.) |
|---|---|---|---|---|
| 1. Size market | `aggregate` | Address + operating status | Count of matching brands/locations | Low/free |
| 2. Paginated search | `search` with `conditions.pageToken` | Name/prompt + address + conditions | Brand IDs, names | 1 per brand |
| 3. Enrich each | `search` by brand ID → card transactions | Brand IDs from step 2 | Revenue, growth, location count | 3 per brand (plus) |

**Pagination with pageToken:**

```graphql
query SearchBrands($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      names(first: 1) { edges { node { name } } }
      count(field: "operatingLocations")
    }
  }
}
# Variables: { searchInput: { prompt: "auto repair", entityType: BRAND, address: { state: "FL" }, conditions: { limit: 50, pageToken: "0" } } }
# Next page: pageToken: "50", then "100", etc.
```

**What we have:** Nothing built for this use case. Requires `aggregate` adapter + paginated search + batch enrichment pipeline.

### Use Case 4: Competitive Intelligence / Market Position

**Goal:** Assess a company's market position relative to local peers.

| Step | Query | Input | Output | Credits (est.) |
|---|---|---|---|---|
| 1. Match target | `search` by name/domain | Company name | Brand ID | 1 |
| 2. Get locations + ranks | Brand → locations → `ranks` + `cardTransactions` | Brand ID | Per-location rank, revenue | 3 per location |
| 3. Peer identification | `aggregate` on same NAICS + geography | Address from target's locations | Total competitors in market | Low/free |
| 4. Peer sampling | `search` with same criteria | NAICS + geography | Peer brand IDs | 1 per peer |

**Market rank query (from existing docs):**

```graphql
query LocationRanks($searchInput: SearchInput!, $cardTransactionConditions: ConnectionConditions!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      operatingLocations(first: 50) {
        edges {
          node {
            names(first: 1) { edges { node { name } } }
            addresses(first: 1) { edges { node { fullAddress city state } } }
            ranks(first: 1) {
              edges { node { position cohortSize quantityType period } }
            }
            cardTransactions(first: 1, conditions: $cardTransactionConditions) {
              edges { node { projectedQuantity } }
            }
          }
        }
      }
    }
  }
}
```

**What we have:** Step 1 is covered by `match_business`. Steps 2-4 require new adapter functions for ranks and aggregate queries.

---

## 8. GraphQL Schema Quick Reference

**Source:** `08-reference/02-graphql-api-reference.md`

### Root Query Type

```graphql
type Query {
  search(searchInput: SearchInput!): [SearchUnion]
  aggregate(searchInput: SearchInput!): AggregateResult
  enrich(enrichmentInput: EnrichmentInput!): [SearchUnion]
  account: Account
  backgroundTask(id: String!): BackgroundTask
  lists(input: SearchListsInput): ListConnection
  listMaterialization(input: GetListMaterializationInput!): ListMaterialization
  _schemaExtended: ExtendedSchema
}

union SearchUnion = LegalEntity | Brand | OperatingLocation
enum EntityType { BRAND, OPERATING_LOCATION, LEGAL_ENTITY }
```

### Key Types Summary

| Type | Key Fields | Key Connections |
|---|---|---|
| `Brand` | `id`, `enigmaId`, `searchMetadata` | `names`, `websites`, `operatingLocations`, `legalEntities`, `affiliatedBrands`, `cardTransactions`, `industries`, `revenueQualities`, `activities`, `isMarketables`, `locationDescriptions` |
| `OperatingLocation` | `id`, `enigmaId`, `searchMetadata` | `names`, `addresses`, `phoneNumbers`, `brands`, `roles`, `legalEntities`, `operatingStatuses`, `technologiesUseds`, `websites`, `reviewSummaries`, `isMarketables`, `locationTypes`, `ranks`, `revenueQualities`, `cardTransactions` |
| `LegalEntity` | `id`, `enigmaId`, `searchMetadata` | `brands`, `names`, `roles`, `persons`, `registeredEntities`, `tins`, `operatingLocations`, `addresses`, `types`, `bankruptcies`, `watchlistEntries` (2 connections) |
| `Person` | `firstName`, `lastName`, `fullName`, `dateOfBirth` | `legalEntities` |
| `RegisteredEntity` | `name`, `registeredEntityType`, `formationDate` | `registrations`, `legalEntities` |
| `Registration` | `registrationState`, `jurisdictionType`, `status`, `subStatus`, `fileNumber`, `issueDate` | `addresses`, `roles`, `registeredEntities` |
| `Role` | `jobTitle`, `jobFunction`, `managementLevel` | `operatingLocations`, `phoneNumbers`, `emailAddresses`, `legalEntities`, `registrations` |
| `Address` | `fullAddress`, `streetAddress1`, `city`, `state`, `zip`, `latitude`, `longitude`, `county`, `msa`, `h3Index` | `operatingLocations`, `registrations`, `deliverabilities`, `watchlistEntries`, `legalEntities` |
| `Industry` | `industryDesc`, `industryCode`, `industryType` | `brands` |
| `Website` | `website`, `domain`, `subdomain`, `topLevelDomain` | `brands`, `operatingLocations`, `websiteContents`, `technologiesUseds`, `onlinePresences` |

### Card Transaction Types

| Type | Extra Fields | Description |
|---|---|---|
| `BrandCardTransaction` | `projectedQuantity`, `quantityType`, `period`, `periodStartDate`, `periodEndDate`, `platformBrandId` | Brand-level aggregate |
| `OperatingLocationCardTransaction` | Same + `rawQuantity` | Location-level (includes raw observed data) |

### Input Types

| Input | Key Fields |
|---|---|
| `SearchInput` | `id`, `name`, `website`, `phoneNumber`, `address`, `person`, `tin`, `prompt`, `entityType`, `matchThreshold`, `conditions`, `output` |
| `AddressInput` | `id`, `street1`, `street2`, `city`, `state`, `postalCode` |
| `PersonInput` | `firstName`, `lastName`, `dateOfBirth`, `address`, `tin` |
| `TinInput` | `tin`, `tinType` (enum: `EIN`, `SSN`, `ITIN`, `TIN`) |
| `Conditions` | `filter` (JSON), `orderBy` ([String]), `limit` (Int), `pageToken` (String) |
| `ConnectionConditions` | `filter` (JSON), `orderBy` ([String]) |

### Filter Operators

| Operator | Args | Example |
|---|---|---|
| `EQ` | 2 | `{EQ: ["period", "12m"]}` |
| `NE` | 2 | `{NE: ["state", "NY"]}` |
| `GT` / `GTE` / `LT` / `LTE` | 2 | `{GT: ["projectedQuantity", 500000]}` |
| `IN` / `NOT_IN` | 2 | `{IN: ["operatingStatus", ["Open", "Closed"]]}` |
| `LIKE` / `ILIKE` | 2 | `{ILIKE: ["name", "%pizza%"]}` |
| `AND` / `OR` | ≥2 | `{AND: [{EQ: [...]}, {GT: [...]}]}` |
| `NOT` | 1 | `{NOT: [{EQ: [...]}]}` |
| `HAS` | 1 | `{HAS: ["roles.emailAddresses"]}` |
| `IS_NULL` / `IS_NOT_NULL` | 1 | `{IS_NOT_NULL: ["website"]}` |

### Pagination Pattern

All connections use cursor-based pagination:

```graphql
operatingLocations(first: 100, after: $cursor) {
  pageInfo {
    hasNextPage
    hasPreviousPage
    startCursor
    endCursor
  }
  edges {
    node { ... }
    cursor
  }
}
```

### Math Functions (available on most types)

All entity/attribute types implement `MathFunctions`: `count(field)`, `sum(field)`, `min(field)`, `max(field)`, `avg(field)`, `collect(field, separator)`, `minDateTime(field)`, `maxDateTime(field)`.

---

## 9. Error Handling & Status Codes

**Source:** `06-query-enigma-with-graphql/06-response-status-codes.md`, `app/providers/enigma.py`

### HTTP Status Codes

| Code | Meaning |
|---|---|
| `200 OK` | Successful request |
| `202 Accepted` | Asynchronous request accepted (background tasks/segmentation) |
| `302 Found` | Response >6MB, redirects to pre-signed S3 URL |
| `400 Bad Request` | Invalid/unsupported input; check `errors` in response body |
| `401 Unauthorized` | Missing or invalid `x-api-key` header |
| `402 Payment Required` | Insufficient credits |
| `429 Slow Down` | Rate limit exceeded |

### GraphQL Error Shape

Errors are returned in the standard GraphQL `errors` array:

```json
{
  "errors": [
    {
      "message": "Error description",
      "locations": [{"line": 1, "column": 1}],
      "path": ["search"]
    }
  ],
  "data": null
}
```

### Our Adapter Error Handling

`app/providers/enigma.py` — `_graphql_post()` (lines 387-429):

1. **HTTP errors (4xx+):** Returns `status: "failed"` with HTTP status code and response text in attempt dict.
2. **GraphQL errors:** Checks for `errors` key in response JSON → `status: "failed"`.
3. **Empty results:** Empty `data.search` array → `status: "not_found"`.
4. **Network errors:** 30-second timeout via `httpx.AsyncClient`. Timeout/connection errors propagate as exceptions.
5. **Missing API key:** All public functions guard for missing `api_key` → `status: "skipped"`, `reason: "missing_provider_api_key"`.
6. **Missing inputs:** Guards for missing required inputs → `status: "skipped"`, `reason: "missing_required_inputs"`.

---

## Appendix: MCP Tools Reference

**Source:** `07-use-enigma-with-ai-via-mcp/01-mcp-tools.md`

Enigma's MCP server (beta) exposes these tools, which map to underlying GraphQL/REST capabilities:

| MCP Tool | Inputs | Maps To |
|---|---|---|
| `search_business` | Business name (required), website/phone/address (optional) | `search(searchInput)` on Brand |
| `get_brand_locations` | Enigma Brand ID | Brand → `operatingLocations` |
| `get_brand_card_analytics` | Enigma Brand ID | Brand → `cardTransactions` (60 months) |
| `get_brand_legal_entities` | Enigma Brand ID | Brand → `legalEntities` → `registeredEntities` |
| `search_negative_news` | Business name + address | Separate capability — risk findings by category |
| `search_gov_archive` | Business name | Government records search |
| `generate_brands_segment` | Various filters | Console segment generation |
| `generate_locations_segment` | Various filters | Console segment generation |
| `search_kyb` | Business identity fields | KYB REST API |

**Notable:** `search_negative_news` and `search_gov_archive` expose capabilities not directly documented in the GraphQL API reference. These may be additional REST endpoints or Enigma-internal features surfaced only through MCP. Documented but detail insufficient for direct API integration — verify with Enigma support.
