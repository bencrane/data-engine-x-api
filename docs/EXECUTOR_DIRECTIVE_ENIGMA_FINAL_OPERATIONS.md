# Executor Directive: Enigma Final Operations Batch

**Last updated:** 2026-03-18T00:00:00Z

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** This directive completes Enigma API coverage. After this batch, every documented, buildable Enigma operation is wired into `/api/v1/execute`. The batch covers brand affiliation networks, marketability flags, compliance activity indicators, bankruptcy records, sanctions screening, role/contact data, officer profiles, KYB verification, and a batch enrichment query to investigate. Two prior directives (async brand discovery, and the additional operations set) are already committed — this is the third and final Enigma batch.

---

## Existing code to read (required, in this order)

**Pattern reference — read every Enigma function before writing anything:**

- `app/providers/enigma.py` — the full file. Focus on:
  - `_graphql_post()` — the shared synchronous GraphQL helper returning `(attempt_dict, brand_dict, is_terminal)`. Extracts `data.search[0]` via `_first_brand()`. All new brand-ID-based operations use this helper.
  - `_graphql_post_async()` — for reference only. The new operations in this batch are synchronous. Do not use for the new adapters.
  - `get_brand_legal_entities()` — the reference pattern for nested traversal (`Brand → legalEntities → ...`). Study carefully — bankruptcy and watchlist follow the same multi-level traversal structure.
  - `get_brand_technologies()` — reference pattern for `Brand → operatingLocations → ...` nested traversal.
  - `_first_edge_node()`, `_as_str()`, `_as_int()`, `_as_list()`, `_as_dict()` — all shared extraction utilities. Use these, do not reinvent.
  - `ProviderAdapterResult` type.
  - `ENIGMA_GRAPHQL_URL` and `_make_headers()` — used directly for the KYB REST helper.

- `app/contracts/company_enrich.py` — all existing Enigma contracts. New contracts append to the end of this file without overwriting anything.

- `app/services/company_operations.py` — all existing Enigma service functions. Study `execute_company_enrich_card_revenue()` and `execute_company_enrich_locations()` as the reference service patterns (context extraction fallback chain, result dict shape, output validation via `ModelClass(**mapped).model_dump()`).

- `app/routers/execute_v1.py` — the existing Enigma dispatch blocks (~lines 617–680). New operations follow the identical dispatch pattern. Check `SUPPORTED_OPERATION_IDS`.

**Enigma API documentation — read before writing any query:**

- `docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md` — the GraphQL SDL. Authoritative for exact field names, connection names, and type definitions. Key types for this batch:
  - `Brand` type (~line 479) — `affiliatedBrands`, `isMarketables`, `activities`, `legalEntities` connections. **Note: Brand has NO `watchlistEntries` connection** — watchlist is accessed via `legalEntities`.
  - `BrandBrandEdge` (~line 627) — `affiliationType: String`, `rank: Int` are on the **EDGE**, not the node. Access as `edges[i].affiliationType`, not `edges[i].node.affiliationType`.
  - `BrandActivity` (~line 573) — `activityType: String`, `firstObservedDate`, `lastObservedDate`.
  - `BrandIsMarketable` (~line 793) — `isMarketable: Boolean`, `firstObservedDate`, `lastObservedDate`.
  - `LegalEntity` (~line 1472) — `bankruptcies`, `isFlaggedByWatchlistEntries`, `appearsOnWatchlistEntries`, `persons` connections. **Two separate watchlist connections** — query both.
  - `LegalEntityBankruptcy` (~line 1557) — `debtorName`, `trustee`, `judge`, `filingDate`, `chapterType`, `caseNumber`, `petition`, `entryDate`, `dateTerminated`, `debtorDischargedDate`, `planConfirmedDate`.
  - `Role` (~line 3685) — `jobTitle`, `jobFunction`, `managementLevel`, `externalUrls: JSON` (LinkedIn), `externalId: JSON`, plus connections `phoneNumbers` (→ `RolePhoneNumberConnection`), `emailAddresses` (→ `RoleEmailAddressConnection`). **Person contact details are on Role, not on Person.**
  - `Person` (~line 3089) — `firstName`, `lastName`, `fullName`, `dateOfBirth`, plus `legalEntities` connection. **Person has NO emailAddresses or phoneNumbers connections** — only SoS data (name, DOB, legal entity associations).
  - `EnrichmentInput` (~line 1256) — `entityType: EntityType`, `output: OutputSpec!`, `sourceId: String!`, `provider: EnrichmentProvider`, `scoreThreshold: Float`. `provider` enum values: `ZOOMINFO`, `SEARCH`.

- `docs/api-reference-docs/enigma/04-resources/03-pricing-and-credit-use.md` — credit tier table. Key tiers for this batch:
  - Core (1 credit): `BrandIsMarketable`, `BrandName`, `OperatingLocationName`, `Address`, `Person`
  - Plus (3 credits per entity): `BrandActivity`, `Role`
  - Premium (5 credits per entity): `WatchlistEntry`, `LegalEntityBankruptcy`, `RegisteredEntity`, `Registration`

- `docs/api-reference-docs/enigma/02-verification-and-kyb/` — KYB REST endpoint documentation. Read all four files:
  - `01-kyb-packages.md` — packages `identify` vs `verify`, add-on attrs
  - `02-kyb-api-quickstart.md` — quickstart and endpoint structure
  - `03-kyb-response-task-results.md` — task result values (name_verification, address_verification, person_verification, domestic_registration, etc.)
  - `04-kyb-response-matched-data.md` — matched data structure (registered_entities, brands, etc.)

- `docs/ENIGMA_API_REFERENCE.md` — Section 5.7 (KYB) and Section 5.9 (Enrichment). The Section 5.9 note is critical: "Documentation detail is insufficient for the exact `EnrichmentInput` shape."

**Persistence registry (check existence, do not create):**
- `app/services/persistence_routing.py` — if this file exists, check `DEDICATED_TABLE_REGISTRY` and add entries for any new operations that write to dedicated tables. If it does not exist, skip and note.

---

## Credit cost reference for this batch

| Operation | Tier | Estimate per call |
|-----------|------|-------------------|
| `company.enrich.enigma.affiliated_brands` | Core | 1 (brand search) + 1 per affiliated brand returned |
| `company.enrich.enigma.marketability` | Core | ~2 (1 brand search + 1 isMarketable entity) |
| `company.enrich.enigma.activity_flags` | Plus | ~4 (1 brand + 3 activity entities at Plus) |
| `company.enrich.enigma.bankruptcy` | Premium | 1 (brand) + 5 per LegalEntity traversed + 5 per bankruptcy node |
| `company.enrich.enigma.watchlist` | Premium | 1 (brand) + 5 per LegalEntity with watchlist hits |
| `person.search.enigma.roles` | Plus | 1 (brand) + 3 per OperatingLocation returned + 3 per Role with contact data |
| `person.enrich.enigma.profile` | Core | 1 (brand) + 1 per LegalEntity + 1 per Person node |
| `company.verify.enigma.kyb` | REST billing | Separate from GraphQL credits — see KYB pricing docs |
| `company.enrich.enigma.batch` | N/A | Investigate — see Deliverable 1i |

**Important warning for `person.search.enigma.roles`:** If called with a high `location_limit`, credit cost scales multiplicatively. A brand with 50 locations × 5 roles each × plus tier = hundreds of credits per call. The executor must document this prominently in the adapter docstring.

---

## Deliverable 1: Provider adapter functions

Add nine new functions to `app/providers/enigma.py`. Add them after the existing `get_brand_industries()` function. Update the `# Last updated:` timestamp at the top of the file.

---

### Adapter 1a: `get_affiliated_brands()`

**Purpose:** Retrieve affiliated brands — franchise networks, multi-brand corporations, sister brands. Returns the Brand-to-Brand relationship graph with `affiliationType` on each edge.

**Important SDL quirk:** `affiliationType` and `rank` are on the **edge** (`BrandBrandEdge`), not on the nested `node`. The GraphQL query must request these fields at the edge level, not inside the `node { ... }` fragment.

**GraphQL query constant:** Define `GET_AFFILIATED_BRANDS_QUERY`:

```graphql
query GetAffiliatedBrands($searchInput: SearchInput!, $limit: Int!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      affiliatedBrands(first: $limit) {
        edges {
          affiliationType
          rank
          firstObservedDate
          lastObservedDate
          node {
            id
            enigmaId
            names(first: 1) {
              edges { node { name } }
            }
            websites(first: 1) {
              edges { node { website } }
            }
            count(field: "operatingLocations")
          }
        }
      }
    }
  }
}
```

**Function signature:**

```python
async def get_affiliated_brands(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 50,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed with `missing_required_inputs`.

**SearchInput:** `{ id: brand_id, entityType: "BRAND" }`. Variables: `{ searchInput: ..., limit: max(1, min(limit, 100)) }`.

**Call:** Use `_graphql_post()`.

**Response mapping:** `brand.get("affiliatedBrands", {}).get("edges", [])`. For each edge:
- `affiliation_type`: `edge.get("affiliationType")`
- `rank`: `edge.get("rank")`
- `first_observed_date`: `edge.get("firstObservedDate")`
- From `edge.get("node", {})`:
  - `enigma_brand_id`: `node.id` or `node.enigmaId`
  - `brand_name`: from `names` first edge
  - `website`: from `websites` first edge
  - `location_count`: `node.get("count")` (the `count(field: "operatingLocations")` scalar)

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "affiliated_brand_count": int,
    "affiliated_brands": [
        {
            "enigma_brand_id": str | None,
            "brand_name": str | None,
            "website": str | None,
            "location_count": int | None,
            "affiliation_type": str | None,
            "rank": int | None,
            "first_observed_date": str | None,
        },
        ...
    ],
}
```

If `affiliatedBrands.edges` is empty, return `status: "not_found"`.

---

### Adapter 1b: `get_brand_marketability()`

**Purpose:** Check if a brand is marketable — actively operating, generating revenue, and accumulating reviews in the last 12 months. Single boolean flag, Core tier.

**GraphQL query constant:** Define `GET_BRAND_MARKETABILITY_QUERY`:

```graphql
query GetBrandMarketability($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      isMarketables(first: 1) {
        edges {
          node {
            isMarketable
            firstObservedDate
            lastObservedDate
          }
        }
      }
    }
  }
}
```

**Function signature:**

```python
async def get_brand_marketability(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed.

**Call:** Use `_graphql_post()`.

**Response mapping:** Extract first edge of `isMarketables` connection. `isMarketable` is a `Boolean` type in the SDL — may come back as Python `bool` or as the string `"true"`/`"false"`. Normalize to Python bool.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "is_marketable": bool | None,
    "first_observed_date": str | None,
    "last_observed_date": str | None,
}
```

If `isMarketables.edges` is empty, return `status: "not_found"`. Do not return `"not_found"` just because `isMarketable` is `False` — absence of data vs `False` are different.

---

### Adapter 1c: `get_brand_activity_flags()`

**Purpose:** Retrieve high-risk business activity indicators. Enigma flags ~13 compliance-sensitive categories including cannabis, firearms, gambling, cryptocurrency, adult entertainment, and payment processors. Useful for compliance screening before onboarding. Plus tier — 3 credits per call.

**GraphQL query constant:** Define `GET_BRAND_ACTIVITY_FLAGS_QUERY`:

```graphql
query GetBrandActivityFlags($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      activities(first: 20) {
        edges {
          node {
            activityType
            firstObservedDate
            lastObservedDate
          }
        }
      }
    }
  }
}
```

**Function signature:**

```python
async def get_brand_activity_flags(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Call:** Use `_graphql_post()`.

**Response mapping:** `brand.get("activities", {}).get("edges", [])`. Each edge node has `activityType`.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "activity_count": int,
    "activity_flags": [
        {
            "activity_type": str | None,
            "first_observed_date": str | None,
            "last_observed_date": str | None,
        },
        ...
    ],
    "has_flags": bool,  # True if activity_count > 0
    "activity_types": [str, ...],  # Flat list of activityType strings for quick scanning
}
```

An empty `activities` list is not `"not_found"` — it means no flags exist for this brand, which is a valid positive result. Return `status: "found"` with `activity_count: 0` in that case.

---

### Adapter 1d: `get_brand_bankruptcy()`

**Purpose:** Retrieve bankruptcy filings for all legal entities associated with a brand. Traverses `Brand → legalEntities → bankruptcies`. Premium tier — use deliberately. Source: PACER (Public Access to Court Electronic Records). Covers cases dating back to the 1980s.

**GraphQL query constant:** Define `GET_BRAND_BANKRUPTCY_QUERY`:

```graphql
query GetBrandBankruptcy($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      legalEntities(first: 10) {
        edges {
          node {
            id
            enigmaId
            legalEntityType
            names(first: 1) {
              edges { node { name } }
            }
            bankruptcies(first: 10) {
              edges {
                node {
                  id
                  debtorName
                  trustee
                  judge
                  filingDate
                  chapterType
                  caseNumber
                  petition
                  entryDate
                  dateTerminated
                  debtorDischargedDate
                  planConfirmedDate
                  firstObservedDate
                  lastObservedDate
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

**Function signature:**

```python
async def get_brand_bankruptcy(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed.

**Call:** Use `_graphql_post()`.

**Response mapping:** Iterate `brand.get("legalEntities", {}).get("edges", [])`. For each legal entity, extract its `bankruptcies` edges. Flatten all bankruptcy records across all legal entities into a single list, tagging each with `enigma_legal_entity_id` and `legal_entity_name` for context.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "legal_entity_count": int,
    "total_bankruptcy_count": int,
    "legal_entities_with_bankruptcies": [
        {
            "enigma_legal_entity_id": str | None,
            "legal_entity_name": str | None,
            "legal_entity_type": str | None,
            "bankruptcy_count": int,
            "bankruptcies": [
                {
                    "case_number": str | None,
                    "chapter_type": str | None,
                    "petition": str | None,
                    "debtor_name": str | None,
                    "filing_date": str | None,
                    "entry_date": str | None,
                    "date_terminated": str | None,
                    "debtor_discharged_date": str | None,
                    "plan_confirmed_date": str | None,
                    "judge": str | None,
                    "trustee": str | None,
                    "first_observed_date": str | None,
                    "last_observed_date": str | None,
                },
                ...
            ],
        },
        ...
    ],
    "has_active_bankruptcy": bool,  # True if any bankruptcy with no dateTerminated
}
```

If no legal entities found, return `status: "not_found"`. If legal entities found but no bankruptcies on any of them, return `status: "found"` with `total_bankruptcy_count: 0` — no bankruptcy is a meaningful result, not an absence of data.

`has_active_bankruptcy`: set to `True` if any bankruptcy record has `dateTerminated` as `None` or empty.

---

### Adapter 1e: `get_brand_watchlist()`

**Purpose:** Check whether a brand's associated legal entities appear on sanctions or watchlist databases. Traverses `Brand → legalEntities → {isFlaggedByWatchlistEntries, appearsOnWatchlistEntries}`. Premium tier. Covers OFAC SDN, FSE, SSI, PLC, CAPTA, NS-MBS, NS-CMIC, and other US sanctions lists.

**Important SDL detail:** The `LegalEntity` type has **two** watchlist connections:
- `isFlaggedByWatchlistEntries` — legal entity is the flagged party
- `appearsOnWatchlistEntries` — legal entity appears on the watchlist directly

Query both. Use a `connection_type` field to distinguish them in the output.

**GraphQL query constant:** Define `GET_BRAND_WATCHLIST_QUERY`:

```graphql
query GetBrandWatchlist($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      legalEntities(first: 10) {
        edges {
          node {
            id
            enigmaId
            legalEntityType
            names(first: 1) {
              edges { node { name } }
            }
            isFlaggedByWatchlistEntries(first: 20) {
              edges {
                node {
                  id
                  watchlistName
                  firstObservedDate
                  lastObservedDate
                }
              }
            }
            appearsOnWatchlistEntries(first: 20) {
              edges {
                node {
                  id
                  watchlistName
                  firstObservedDate
                  lastObservedDate
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

**Function signature:**

```python
async def get_brand_watchlist(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Call:** Use `_graphql_post()`.

**Response mapping:** Iterate legal entity edges. For each legal entity, collect entries from both `isFlaggedByWatchlistEntries` and `appearsOnWatchlistEntries`, adding a `connection_type` field (`"is_flagged_by"` or `"appears_on"`) to each entry.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "legal_entity_count": int,
    "total_watchlist_hit_count": int,
    "has_watchlist_hits": bool,
    "legal_entities_with_hits": [
        {
            "enigma_legal_entity_id": str | None,
            "legal_entity_name": str | None,
            "legal_entity_type": str | None,
            "watchlist_hit_count": int,
            "watchlist_entries": [
                {
                    "watchlist_name": str | None,
                    "connection_type": str,  # "is_flagged_by" or "appears_on"
                    "first_observed_date": str | None,
                    "last_observed_date": str | None,
                },
                ...
            ],
        },
        ...
    ],
}
```

An empty result (no hits on any legal entity) returns `status: "found"` with `total_watchlist_hit_count: 0` and `has_watchlist_hits: False` — a clean screening result is meaningful.

---

### Adapter 1f: `get_brand_roles()`

**Purpose:** Retrieve people/contacts associated with a brand's operating locations — full name (via `Role.externalUrls` for LinkedIn, or `Role.emailAddresses`/`Role.phoneNumbers` connections), job title, job function, management level, email, and phone. This is the dedicated "get me the people at this business" operation. Plus tier — 3 credits per Role entity returned.

**Credit warning:** This query is expensive at scale. A brand with 20 locations × 5 roles each = 100 Role entities × Plus tier = 300 credits per call. The `location_limit` and `role_limit` parameters must be documented and used conservatively.

**Important SDL pattern:** Contact details (`phoneNumbers`, `emailAddresses`) are on the `Role` type, NOT on `Person`. The Role itself is the contact record. `externalUrls: JSON` on Role may contain LinkedIn profile URLs (value is a JSON object — extract carefully).

**GraphQL query constant:** Define `GET_BRAND_ROLES_QUERY`:

```graphql
query GetBrandRoles($searchInput: SearchInput!, $locationLimit: Int!, $roleLimit: Int!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      operatingLocations(first: $locationLimit) {
        edges {
          node {
            id
            enigmaId
            names(first: 1) {
              edges { node { name } }
            }
            addresses(first: 1) {
              edges {
                node {
                  fullAddress
                  city
                  state
                }
              }
            }
            operatingStatuses(first: 1) {
              edges { node { operatingStatus } }
            }
            roles(first: $roleLimit) {
              edges {
                node {
                  id
                  jobTitle
                  jobFunction
                  managementLevel
                  externalUrls
                  externalId
                  firstObservedDate
                  lastObservedDate
                  phoneNumbers(first: 3) {
                    edges { node { phoneNumber } }
                  }
                  emailAddresses(first: 3) {
                    edges { node { emailAddress } }
                  }
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

**Function signature:**

```python
async def get_brand_roles(
    *,
    api_key: str | None,
    brand_id: str | None,
    location_limit: int = 10,
    role_limit: int = 5,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed.

**Safe limits:** `safe_location_limit = max(1, min(location_limit, 50))`. `safe_role_limit = max(1, min(role_limit, 20))`.

**Call:** Use `_graphql_post()`.

**Response mapping:** Iterate `brand.get("operatingLocations", {}).get("edges", [])`. For each location, iterate its `roles` edges. For each role, extract contact data:
- `phone_numbers`: list of phoneNumber strings from `phoneNumbers` connection
- `email_addresses`: list of emailAddress strings from `emailAddresses` connection
- `external_urls`: extract the raw JSON value of `externalUrls` — store as `dict | None`
- `linkedin_url`: attempt to extract a LinkedIn URL from `externalUrls` (look for a key containing "linkedin" case-insensitive, or a value starting with "https://www.linkedin.com")

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "location_count": int,
    "total_role_count": int,
    "locations": [
        {
            "enigma_location_id": str | None,
            "location_name": str | None,
            "full_address": str | None,
            "city": str | None,
            "state": str | None,
            "operating_status": str | None,
            "role_count": int,
            "roles": [
                {
                    "job_title": str | None,
                    "job_function": str | None,
                    "management_level": str | None,
                    "phone_numbers": list[str],
                    "email_addresses": list[str],
                    "linkedin_url": str | None,
                    "first_observed_date": str | None,
                    "last_observed_date": str | None,
                },
                ...
            ],
        },
        ...
    ],
}
```

If no roles found across all locations, return `status: "not_found"`.

---

### Adapter 1g: `get_brand_officer_persons()`

**Purpose:** Retrieve person records (officers, owners, registered agents) associated with a brand via its legal entities. Source: Secretary of State filings. Returns name and date of birth as filed. **Contact details (email, phone) are NOT available on Person in the Enigma schema** — for contact data, use `get_brand_roles()` instead. This operation is for identity/compliance use: who is the registered officer? Do they have a DOB match? Core tier.

**GraphQL query constant:** Define `GET_BRAND_OFFICER_PERSONS_QUERY`:

```graphql
query GetBrandOfficerPersons($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      legalEntities(first: 10) {
        edges {
          node {
            id
            enigmaId
            legalEntityType
            names(first: 1) {
              edges { node { name } }
            }
            registeredEntities(first: 3) {
              edges {
                node {
                  name
                  registeredEntityType
                  formationDate
                  formationYear
                }
              }
            }
            persons(first: 20) {
              edges {
                node {
                  id
                  firstName
                  lastName
                  fullName
                  dateOfBirth
                }
              }
            }
            roles(first: 10) {
              edges {
                node {
                  jobTitle
                  jobFunction
                  managementLevel
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

**Function signature:**

```python
async def get_brand_officer_persons(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Call:** Use `_graphql_post()`.

**Response mapping:** Iterate `brand.get("legalEntities", {}).get("edges", [])`. For each legal entity, extract its `persons` edges and `roles` edges. Build a list of person records. The `roles` connection on LegalEntity provides the officer title context (e.g., "Registered Agent", "Director").

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "legal_entity_count": int,
    "total_person_count": int,
    "legal_entities": [
        {
            "enigma_legal_entity_id": str | None,
            "legal_entity_name": str | None,
            "legal_entity_type": str | None,
            "registered_entity_name": str | None,
            "registered_entity_type": str | None,
            "formation_date": str | None,
            "person_count": int,
            "persons": [
                {
                    "enigma_person_id": str | None,
                    "first_name": str | None,
                    "last_name": str | None,
                    "full_name": str | None,
                    "date_of_birth": str | None,
                },
                ...
            ],
            "officer_roles": [
                {
                    "job_title": str | None,
                    "job_function": str | None,
                    "management_level": str | None,
                },
                ...
            ],
        },
        ...
    ],
}
```

If no legal entities found or no persons on any legal entity, return `status: "not_found"`.

---

### Adapter 1h: `verify_business_kyb()`

**Purpose:** Verify a business identity against Secretary of State records, IRS data, and sanctions lists via Enigma's KYB REST API. This is a **REST call, not GraphQL** — requires a separate HTTP helper function.

**KYB REST endpoint:**
```
POST https://api.enigma.com/v2/kyb/verify
Headers: x-api-key: {api_key}
Content-Type: application/json
```

**KYB URL constant:** Define at module level:
```python
ENIGMA_KYB_URL = "https://api.enigma.com/v2/kyb/verify"
```

**KYB helper function:** Define `_kyb_post()` (private, not exported):

```python
async def _kyb_post(
    *,
    api_key: str,
    payload: dict[str, Any],
    action: str = "kyb_verify",
) -> tuple[dict, dict | None, bool]:
    """
    POST to the Enigma KYB REST endpoint.
    Returns (attempt_dict, response_dict | None, is_terminal).
    response_dict is None if the call failed or should be skipped.
    """
```

Pattern mirrors `_graphql_post()` but:
- Uses `ENIGMA_KYB_URL`, not `ENIGMA_GRAPHQL_URL`
- Request body is `payload` directly (not a `{"query": ..., "variables": ...}` wrapper)
- Response is parsed as JSON directly — no `data.search` extraction needed
- On 429 → return (attempt, None, False) with `rate_limited` skip
- On 402 → return (attempt, None, True) with `insufficient_credits` skip
- On non-2xx → return (attempt, None, True) with `http_error`
- On success → return (attempt, response_json, True)

**Function signature:**

```python
async def verify_business_kyb(
    *,
    api_key: str | None,
    business_name: str | None,
    street_address: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postal_code: str | None = None,
    person_first_name: str | None = None,
    person_last_name: str | None = None,
    registration_state: str | None = None,
    package: str = "verify",
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `business_name` → failed with `missing_required_inputs`.

**KYB request body construction:**
```python
payload: dict[str, Any] = {
    "package": package if package in ("identify", "verify") else "verify",
    "top_n": 1,
}

if business_name:
    payload["names"] = [{"name": business_name.strip()}]

address: dict[str, Any] = {}
if street_address: address["street_address1"] = street_address
if city: address["city"] = city
if state: address["state"] = state.upper()
if postal_code: address["postal_code"] = postal_code
if address:
    payload["addresses"] = [address]

if person_first_name and person_last_name:
    payload["persons"] = [{
        "first_name": person_first_name.strip(),
        "last_name": person_last_name.strip(),
    }]

if registration_state:
    payload["state"] = registration_state.upper()
```

**Call:** `_kyb_post(api_key=api_key, payload=payload)`.

**Response mapping:** The KYB response has two top-level keys: `data` (matched entity data) and `tasks` (verification task results).

From `response.get("data", {})`:
- `registered_entities`: list of matched registered entities with `id`, `names`, `registrations`, `brand_ids`
- `brands`: list of matched brands with `id`, `names`, `industries`, `operating_locations`

From `response.get("tasks", {})`:
- `name_verification`: `{status, result}` — result values: `name_exact_match`, `name_match`, `name_not_verified`
- `sos_name_verification`: `{status, result}` — same values from SoS records
- `address_verification`: `{status, result}` — `address_exact_match`, `address_match`, `address_not_verified`
- `person_verification`: `{status, result}` — `person_match`, `person_not_verified` (`verify` package only)
- `domestic_registration`: `{status, result}` — `domestic_active`, `domestic_unknown`, `domestic_inactive`, `domestic_not_found` (`verify` package only)

**Return shape (`mapped`):**
```python
{
    "business_name_queried": business_name,
    "enigma_brand_id": str | None,  # First brand match ID from data.brands[0].id
    "enigma_registered_entity_id": str | None,  # First from data.registered_entities[0].id
    "name_verification": str | None,
    "sos_name_verification": str | None,
    "address_verification": str | None,
    "person_verification": str | None,  # None if package="identify"
    "domestic_registration": str | None,  # None if package="identify"
    "name_match": bool,  # True if name_verification ends in "_exact_match" or "_match"
    "address_match": bool,
    "person_match": bool,
    "domestic_active": bool,  # True if domestic_registration == "domestic_active"
    "registered_entity_count": int,
    "brand_count": int,
    "raw_tasks": dict,  # Full tasks dict for any task not explicitly mapped
}
```

If `data.registered_entities` is empty and `data.brands` is empty, return `status: "not_found"`. Otherwise `status: "found"`.

---

### Adapter 1i: `investigate_batch_enrich()`

**Purpose:** Investigation stub. The Enigma GraphQL schema includes an `enrich(enrichmentInput: EnrichmentInput!)` query but documentation is insufficient to implement it correctly.

**What is known from the SDL:**
```graphql
input EnrichmentInput {
  entityType: EntityType     # BRAND | OPERATING_LOCATION | LEGAL_ENTITY
  output: OutputSpec!        # Required async output spec (same as prompt search)
  sourceId: String!          # Unknown: what format? Enigma UUID? External ID?
  provider: EnrichmentProvider  # ZOOMINFO | SEARCH
  scoreThreshold: Float
}

enrich(enrichmentInput: EnrichmentInput!): [SearchUnion]
```

**What is unknown:**
- What `sourceId` should contain (Enigma UUID? External business identifier?)
- What data is returned in the `[SearchUnion]` response for this query type
- Whether `output: OutputSpec!` means this is always async (like prompt search) or can return inline
- What `provider: ZOOMINFO` vs `provider: SEARCH` changes about the returned data
- Credit cost

**Task:** This adapter is NOT to be implemented. Instead:

1. Read `docs/ENIGMA_API_REFERENCE.md` Section 5.9 fully.
2. Search `docs/api-reference-docs/enigma/` for any file that documents `enrich`, `EnrichmentInput`, `sourceId`, or `EnrichmentProvider`.
3. If you find documentation that makes `sourceId` semantics clear and confirms the response shape → implement it following the standard async adapter pattern (similar to `search_brands_by_prompt`). Add to this commit.
4. If documentation is insufficient → do NOT implement. Record the finding in the work log entry. The operation is not wired into the router. Flag for chief agent to investigate with Enigma support.

**Do not call the live Enigma API to discover the endpoint shape.**

---

**Commit standalone:** "Add Enigma final batch adapter functions: affiliated brands, marketability, activity flags, bankruptcy, watchlist, roles, officer persons, KYB verify (batch enrich: investigate)"

---

## Deliverable 2: Pydantic contracts

Append to `app/contracts/company_enrich.py` (append to end — do NOT overwrite existing contracts):

```python
# --- Enigma affiliated brands ---

class EnigmaAffiliatedBrandItem(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None
    affiliation_type: str | None = None
    rank: int | None = None
    first_observed_date: str | None = None


class EnigmaAffiliatedBrandsOutput(BaseModel):
    enigma_brand_id: str | None = None
    affiliated_brand_count: int | None = None
    affiliated_brands: list[EnigmaAffiliatedBrandItem] | None = None
    source_provider: str = "enigma"


# --- Enigma marketability ---

class EnigmaMarketabilityOutput(BaseModel):
    enigma_brand_id: str | None = None
    is_marketable: bool | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None
    source_provider: str = "enigma"


# --- Enigma activity flags ---

class EnigmaActivityFlagItem(BaseModel):
    activity_type: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaActivityFlagsOutput(BaseModel):
    enigma_brand_id: str | None = None
    activity_count: int | None = None
    activity_flags: list[EnigmaActivityFlagItem] | None = None
    has_flags: bool | None = None
    activity_types: list[str] | None = None
    source_provider: str = "enigma"


# --- Enigma bankruptcy ---

class EnigmaBankruptcyRecord(BaseModel):
    case_number: str | None = None
    chapter_type: str | None = None
    petition: str | None = None
    debtor_name: str | None = None
    filing_date: str | None = None
    entry_date: str | None = None
    date_terminated: str | None = None
    debtor_discharged_date: str | None = None
    plan_confirmed_date: str | None = None
    judge: str | None = None
    trustee: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaBankruptcyLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    bankruptcy_count: int | None = None
    bankruptcies: list[EnigmaBankruptcyRecord] | None = None


class EnigmaBankruptcyOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_bankruptcy_count: int | None = None
    has_active_bankruptcy: bool | None = None
    legal_entities_with_bankruptcies: list[EnigmaBankruptcyLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma watchlist ---

class EnigmaWatchlistEntry(BaseModel):
    watchlist_name: str | None = None
    connection_type: str | None = None  # "is_flagged_by" or "appears_on"
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaWatchlistLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    watchlist_hit_count: int | None = None
    watchlist_entries: list[EnigmaWatchlistEntry] | None = None


class EnigmaWatchlistOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_watchlist_hit_count: int | None = None
    has_watchlist_hits: bool | None = None
    legal_entities_with_hits: list[EnigmaWatchlistLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma brand roles ---

class EnigmaRoleItem(BaseModel):
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None
    phone_numbers: list[str] | None = None
    email_addresses: list[str] | None = None
    linkedin_url: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaLocationRolesItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    city: str | None = None
    state: str | None = None
    operating_status: str | None = None
    role_count: int | None = None
    roles: list[EnigmaRoleItem] | None = None


class EnigmaBrandRolesOutput(BaseModel):
    enigma_brand_id: str | None = None
    location_count: int | None = None
    total_role_count: int | None = None
    locations: list[EnigmaLocationRolesItem] | None = None
    source_provider: str = "enigma"


# --- Enigma officer persons ---

class EnigmaOfficerPersonItem(BaseModel):
    enigma_person_id: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    full_name: str | None = None
    date_of_birth: str | None = None


class EnigmaOfficerRoleItem(BaseModel):
    job_title: str | None = None
    job_function: str | None = None
    management_level: str | None = None


class EnigmaOfficerLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_name: str | None = None
    legal_entity_type: str | None = None
    registered_entity_name: str | None = None
    registered_entity_type: str | None = None
    formation_date: str | None = None
    person_count: int | None = None
    persons: list[EnigmaOfficerPersonItem] | None = None
    officer_roles: list[EnigmaOfficerRoleItem] | None = None


class EnigmaOfficerPersonsOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    total_person_count: int | None = None
    legal_entities: list[EnigmaOfficerLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma KYB verification ---

class EnigmaKYBOutput(BaseModel):
    business_name_queried: str | None = None
    enigma_brand_id: str | None = None
    enigma_registered_entity_id: str | None = None
    name_verification: str | None = None
    sos_name_verification: str | None = None
    address_verification: str | None = None
    person_verification: str | None = None
    domestic_registration: str | None = None
    name_match: bool | None = None
    address_match: bool | None = None
    person_match: bool | None = None
    domestic_active: bool | None = None
    registered_entity_count: int | None = None
    brand_count: int | None = None
    raw_tasks: dict[str, Any] | None = None
    source_provider: str = "enigma"
```

**Commit standalone:** "Add Enigma Pydantic contracts: affiliated brands, marketability, activity flags, bankruptcy, watchlist, roles, officer persons, KYB"

---

## Deliverable 3: Service functions

Add eight service functions to `app/services/company_operations.py`. Follow the exact pattern of `execute_company_enrich_card_revenue()` and `execute_company_enrich_locations()`.

---

### Service 3a: `execute_company_enrich_enigma_affiliated_brands()`

```python
async def execute_company_enrich_enigma_affiliated_brands(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required), `limit` (optional, default 50, clamped 1–100).

**Operation ID:** `"company.enrich.enigma.affiliated_brands"`

**Output validation:** `EnigmaAffiliatedBrandsOutput(**mapped).model_dump()`

---

### Service 3b: `execute_company_enrich_enigma_marketability()`

```python
async def execute_company_enrich_enigma_marketability(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required).

**Operation ID:** `"company.enrich.enigma.marketability"`

**Output validation:** `EnigmaMarketabilityOutput(**mapped).model_dump()`

---

### Service 3c: `execute_company_enrich_enigma_activity_flags()`

```python
async def execute_company_enrich_enigma_activity_flags(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required).

**Operation ID:** `"company.enrich.enigma.activity_flags"`

**Output validation:** `EnigmaActivityFlagsOutput(**mapped).model_dump()`

---

### Service 3d: `execute_company_enrich_enigma_bankruptcy()`

```python
async def execute_company_enrich_enigma_bankruptcy(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required).

**Operation ID:** `"company.enrich.enigma.bankruptcy"`

**Output validation:** `EnigmaBankruptcyOutput(**mapped).model_dump()`

---

### Service 3e: `execute_company_enrich_enigma_watchlist()`

```python
async def execute_company_enrich_enigma_watchlist(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required).

**Operation ID:** `"company.enrich.enigma.watchlist"`

**Output validation:** `EnigmaWatchlistOutput(**mapped).model_dump()`

---

### Service 3f: `execute_person_search_enigma_roles()`

```python
async def execute_person_search_enigma_roles(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `enigma_brand_id` (required)
- `location_limit` (optional, default 10, clamped 1–50)
- `role_limit` (optional, default 5, clamped 1–20)

**Operation ID:** `"person.search.enigma.roles"`

**Output validation:** `EnigmaBrandRolesOutput(**mapped).model_dump()`

---

### Service 3g: `execute_person_enrich_enigma_profile()`

```python
async def execute_person_enrich_enigma_profile(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:** `enigma_brand_id` (required).

**Note on overlap with `company.search.enigma.person`:** `company.search.enigma.person` does a reverse person lookup (given a name, find associated businesses). This operation does the forward lookup (given a brand, find its officers/persons from SoS filings). Different use case; no deduplication needed.

**Operation ID:** `"person.enrich.enigma.profile"`

**Output validation:** `EnigmaOfficerPersonsOutput(**mapped).model_dump()`

---

### Service 3h: `execute_company_verify_enigma_kyb()`

```python
async def execute_company_verify_enigma_kyb(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `business_name` (required — from `input_data` first, then cumulative context `company_name`)
- `street_address` (optional — try `input_data.address_street`, then context)
- `city` (optional)
- `state` (optional)
- `postal_code` (optional)
- `person_first_name` (optional)
- `person_last_name` (optional)
- `registration_state` (optional)
- `package` (optional, default `"verify"`)

**Operation ID:** `"company.verify.enigma.kyb"`

**Output validation:** `EnigmaKYBOutput(**mapped).model_dump()`

---

**Commit standalone:** "Add Enigma service functions: affiliated brands, marketability, activity flags, bankruptcy, watchlist, roles, officer persons, KYB"

---

## Deliverable 4: Wire into execute router

In `app/routers/execute_v1.py`:

**Step 1:** Import all new service functions (add to the existing Enigma service function import block):

```python
from app.services.company_operations import (
    # ... existing imports ...
    execute_company_enrich_enigma_activity_flags,
    execute_company_enrich_enigma_affiliated_brands,
    execute_company_enrich_enigma_bankruptcy,
    execute_company_enrich_enigma_marketability,
    execute_company_enrich_enigma_watchlist,
    execute_company_verify_enigma_kyb,
    execute_person_enrich_enigma_profile,
    execute_person_search_enigma_roles,
)
```

**Step 2:** Add all eight to `SUPPORTED_OPERATION_IDS`:

```python
"company.enrich.enigma.affiliated_brands",
"company.enrich.enigma.marketability",
"company.enrich.enigma.activity_flags",
"company.enrich.enigma.bankruptcy",
"company.enrich.enigma.watchlist",
"person.search.enigma.roles",
"person.enrich.enigma.profile",
"company.verify.enigma.kyb",
```

If `company.enrich.enigma.batch` was implemented in Deliverable 1i, add it here too.

**Step 3:** Add dispatch branches following the existing pattern:

```python
if payload.operation_id == "company.enrich.enigma.affiliated_brands":
    result = await execute_company_enrich_enigma_affiliated_brands(input_data=payload.input)
    await persist_operation_execution(result, db=db, api_token=api_token)
    return DataEnvelope(data=result)
```

One block per operation. Follow the exact same dispatch shape as existing Enigma blocks.

**Step 4:** If `_finalize_execute_response()` helper exists in `execute_v1.py` (from the EXECUTOR_DIRECTIVE_STANDALONE_EXECUTE_PERSISTENCE directive), use it instead of the manual `persist_operation_execution + return DataEnvelope` pattern. Follow whatever pattern is already established in the file — match what's there, don't invent a new pattern.

**Commit standalone:** "Wire eight new Enigma final-batch operations into execute router"

---

## Deliverable 5: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary: completed the final Enigma batch — 8 new operations callable via `/api/v1/execute`: `company.enrich.enigma.affiliated_brands` (franchise network discovery, Core tier), `company.enrich.enigma.marketability` (brand active-status flag, Core tier), `company.enrich.enigma.activity_flags` (compliance risk indicators, Plus tier), `company.enrich.enigma.bankruptcy` (PACER bankruptcy records via legal entities, Premium tier), `company.enrich.enigma.watchlist` (OFAC sanctions via legal entities, Premium tier), `person.search.enigma.roles` (contacts/people at locations, Plus tier with credit scaling warning), `person.enrich.enigma.profile` (SoS officers from legal entity filings, Core tier), `company.verify.enigma.kyb` (KYB REST verification endpoint). Include finding on `company.enrich.enigma.batch` — whether implemented or flagged.

This is your final commit.

---

## What is NOT in scope

- **No changes to `trigger/src/`** — these are standalone execute operations, no dedicated Trigger.dev workflows needed.
- **No new database migrations** — no new tables. These operations return data in the operation output only.
- **No changes to `run-pipeline.ts`** — never.
- **No deploy commands.** Do not push.
- **No blueprint definitions** — router wiring only.
- **No modifications to existing Enigma operations.** The operations from prior directives are complete and working — do not touch them.
- **No persistence registry changes** — if `app/services/persistence_routing.py` does not exist, skip entirely. If it does exist, check whether any of the new operations produce data worth registering and add entries at your discretion.
- **No test files** — tests are out of scope for this directive.
- **No production API calls to Enigma** — do not call the live API to test or discover endpoint shapes.

---

## Commit convention

Each deliverable is one commit. Do not push.

---

## When done

Report back with:

(a) **Adapters:** for each of the 8 adapter functions, confirm the GraphQL query used (or REST call for KYB) and any deviation from the spec above. Flag any field name that differed from the SDL.

(b) **SDL edge-vs-node quirk for `affiliated_brands`:** Confirm that `affiliationType` and `rank` were extracted from the edge object, not from `edge.node`.

(c) **`_kyb_post()` helper:** Confirm it was created as a separate REST helper (not reusing `_graphql_post()`). Confirm it uses `ENIGMA_KYB_URL`.

(d) **`person.search.enigma.roles` credit warning:** Confirm the adapter docstring documents the credit scaling risk.

(e) **`company.enrich.enigma.activity_flags` empty result handling:** Confirm that an empty activity list returns `status: "found"` with `activity_count: 0` (not `"not_found"`).

(f) **`company.enrich.enigma.watchlist` two connections:** Confirm both `isFlaggedByWatchlistEntries` and `appearsOnWatchlistEntries` were queried and that `connection_type` distinguishes them in the output.

(g) **`company.enrich.enigma.batch` investigation:** State what documentation was found (or not found) for `EnrichmentInput.sourceId` and whether the operation was implemented or flagged.

(h) **Contracts:** Count of new Pydantic models added. Confirm appended without overwriting existing models.

(i) **Router:** Confirm all 8 operation IDs (plus batch if implemented) are in `SUPPORTED_OPERATION_IDS`. Confirm all dispatch branches match the existing pattern in the file (whether that's the old manual pattern or the `_finalize_execute_response` helper).

(j) **Persistence routing:** State whether `app/services/persistence_routing.py` existed, and if so, whether any new operations were added to the registry.

(k) **Anything to flag:** SDL field names that differed from the spec, unexpected type shapes, any adapter where the extraction failed silently during implementation, or any operation where the credit cost estimate was significantly wrong.
