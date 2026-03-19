# Executor Directive: Enigma Additional Operations

**Last updated:** 2026-03-18T23:30:00Z

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The core Enigma discovery and enrichment operations are built and committed: `company.search.enigma.brands` (semantic brand discovery with async prompt search), `company.enrich.card_revenue` (brand-level card analytics), and `company.enrich.locations` (per-location enrichment with optional Plus-tier attributes). This directive adds the remaining high-value Enigma operations: market sizing (aggregate counts before spending credits on discovery), brand legal entity data (who owns the entity, SoS registrations), address deliverability (mailable vs. virtual vs. vacant — critical for Lob direct mail), payment technology stack (which POS system a location uses), person reverse lookup (what businesses is this person associated with), and industry classification. Two additional operations (negative news, government archive) are MCP-only tools with no documented GraphQL/REST endpoint — the executor must investigate and document their status but not implement them.

---

## Existing code to read (required, in this order)

**Pattern reference — read every Enigma function before writing anything:**

- `app/providers/enigma.py` — the full file. Pay close attention to:
  - `_graphql_post()` (~line 388) — the shared synchronous GraphQL helper. Returns `(attempt_dict, brand_dict, is_terminal)`. Uses `_first_brand()` internally which extracts `data.search[0]`. All brand-ID-based enrichment operations should use this helper.
  - `_graphql_post_async()` (~line 435) — the async helper for prompt-based searches. Do NOT use this for the new operations — these are synchronous `id`-based lookups.
  - `match_business()` — pattern for how brand-by-ID lookups work (used by card revenue and locations)
  - `get_card_analytics()` — pattern for brand-level connection traversal via `_graphql_post()`
  - `get_brand_locations()` and `get_locations_enriched()` — patterns for brand → operatingLocations traversal
  - `_first_edge_node()`, `_as_str()`, `_as_int()`, `_as_list()`, `_as_dict()` — the shared extraction utilities
  - `ProviderAdapterResult` type and the standard result dict shape: `{"attempt": {...}, "mapped": {...}}`

- `app/contracts/company_enrich.py` — all existing Enigma contracts. New contracts go at the bottom of this file.

- `app/services/company_operations.py` — functions `execute_company_enrich_card_revenue()` and `execute_company_enrich_locations()` are the reference service function patterns. All new service functions go in this file.

- `app/routers/execute_v1.py` — look at the Enigma dispatch blocks at lines ~617–640. New operations follow the same pattern: add to `SUPPORTED_OPERATION_IDS`, add dispatch branch, call `persist_operation_execution()`.

**Enigma API documentation — read before writing any query:**

- `docs/ENIGMA_API_REFERENCE.md` — consolidated reference. Read all of Section 4 (credit model), Section 5 (query types), and the Appendix (MCP tools table). The credit model is essential — several new operations use Premium tier (5 credits per entity).
- `docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md` — the full GraphQL SDL. This is the authoritative source for exact field names, connection names, and type definitions. Key sections:
  - `AggregateResult` type (~line 454) — `count(field: "brand")`, `count(field: "operatingLocation")`, `count(field: "legalEntity")`
  - `AddressDeliverability` type (~line 273) — `rdi`, `deliveryType`, `deliverable`, `virtual`
  - `LegalEntity` type (~line 1472) — `registeredEntities`, `persons`, `names`, `legalEntityType`
  - `RegisteredEntity` type (~line 3283) — `name`, `registeredEntityType`, `formationDate`, `formationYear`
  - `Registration` type (~line 3406) — `registrationState`, `jurisdictionType`, `status`, `subStatus`, `fileNumber`, `issueDate`
  - `OperatingLocationTechnologiesUsed` type (~line 2979) — `technology`, `category`, `firstObservedDate`, `lastObservedDate`
  - `Person` type (~line 3089) and `PersonInput` (~line 3130) — `firstName`, `lastName`, `fullName`, `dateOfBirth`, `legalEntities`
  - `Industry` type (~line 1382) — `industryDesc`, `industryCode`, `industryType`
  - `SearchInput` (~line 3851) — includes `person: PersonInput` field for person reverse lookup
  - `SearchUnion = LegalEntity | Brand | OperatingLocation` (~line 3896)
- `docs/api-reference-docs/enigma/06-query-enigma-with-graphql/03-get-aggregate-location-counts.md` — the aggregate query documentation. Read fully. The aggregate query only supports `entityType: OPERATING_LOCATION`, only supports address-based geographic filters (no `prompt`), and the only conditions filter is `operatingStatuses.operatingStatus = "Open"`.
- `docs/api-reference-docs/enigma/07-use-enigma-with-ai-via-mcp/01-mcp-tools.md` — MCP tools listing. Read for the `search_negative_news` and `search_gov_archive` tools. Note inputs/outputs but check whether any GraphQL query or REST endpoint is documented.

**Persistence registry:**
- `app/services/persistence_registry.py` — check if this file exists. If it does not exist, skip all persistence registry steps and note the skip in your report. Do not create the file.

---

## Credit costs for new operations (from `docs/ENIGMA_API_REFERENCE.md` Section 4)

| Tier | Cost per entity | Attribute types |
|------|----------------|-----------------|
| Core | 1 credit | Names, addresses, website, phone, industry, operating status |
| Plus | 3 credits | Card transactions, ranks, reviews, roles/contacts |
| Premium | 5 credits | `RegisteredEntity`, `Registration`, `OperatingLocationTechnologiesUsed`, TINs, watchlist |

| Operation | Credit estimate | Notes |
|-----------|----------------|-------|
| `company.search.enigma.aggregate` | ~0–1 per call | Aggregate is documented as low/free; verify via `docs/ENIGMA_API_REFERENCE.md` Section 9 chain table |
| `company.enrich.enigma.legal_entities` | ~5 per LegalEntity + 5 per RegisteredEntity | Premium tier; a brand with 3 legal entities each with 2 registered entities = 15+ credits |
| `company.enrich.enigma.address_deliverability` | ~3 per location (Plus tier) | N locations = 3N credits |
| `company.enrich.enigma.technologies` | ~5 per location (Premium tier) | N locations = 5N credits; currently covers only 6 payment processors |
| `company.search.enigma.person` | ~1 per result entity (Core tier) | Returns Brand/OperatingLocation/LegalEntity nodes |
| `company.enrich.enigma.industries` | ~1 per entity (Core tier) | Industry data is Core tier |

---

## Deliverable 1: Provider adapter functions

Add six new functions to `app/providers/enigma.py`. Add them after the existing `search_brands_by_prompt()` function. Update the `# Last updated:` timestamp at the top of the file.

---

### Adapter 1a: `aggregate_locations()`

**Purpose:** Count brands, operating locations, and legal entities in a geographic market. No `_graphql_post()` — the aggregate query returns `data.aggregate`, not `data.search`. Handle the HTTP call inline.

**GraphQL query constant:** Define `AGGREGATE_MARKET_QUERY`:

```graphql
query AggregateMarket($searchInput: SearchInput!) {
  aggregate(searchInput: $searchInput) {
    brandsCount: count(field: "brand")
    operatingLocationsCount: count(field: "operatingLocation")
    legalEntitiesCount: count(field: "legalEntity")
  }
}
```

**Function signature:**

```python
async def aggregate_locations(
    *,
    api_key: str | None,
    state: str | None = None,
    city: str | None = None,
    operating_status_filter: str | None = None,
) -> ProviderAdapterResult:
```

**Guards:**
- No `api_key` → return skipped with `missing_provider_api_key`
- No `state` and no `city` → return failed with `missing_required_inputs` (at least one of state or city is required — aggregate without geography is too broad to be useful)

**SearchInput construction:**
- Always set `entityType: "OPERATING_LOCATION"` (required by aggregate — only supported entity type)
- If `state` or `city` provided, set `address: {state, city}` (omit keys that are None)
- If `operating_status_filter` is `"Open"` (case-insensitive), add `conditions: {"filter": {"EQ": ["operatingStatuses.operatingStatus", "Open"]}}`. Only `"Open"` is supported per the aggregate docs — if any other value is passed, ignore it and log a warning.

**HTTP handling:** Do the POST inline (same pattern as the pre-`_graphql_post` code did). On 429 → skip with `rate_limited`. On 402 → skip with `insufficient_credits`. On HTTP error → fail. On GraphQL errors → fail.

**Response extraction:** `data.aggregate.brandsCount`, `data.aggregate.operatingLocationsCount`, `data.aggregate.legalEntitiesCount`. All are nullable integers.

**Return shape (`mapped`):**
```python
{
    "brands_count": int | None,
    "locations_count": int | None,
    "legal_entities_count": int | None,
    "geography_state": state,
    "geography_city": city,
    "operating_status_filter": operating_status_filter or None,
}
```

---

### Adapter 1b: `get_brand_legal_entities()`

**Purpose:** Retrieve legal entity data for a brand — who owns/operates it, SoS registration status per state, formation date, persons on record. Uses `_graphql_post()` via a brand-by-ID search.

**GraphQL query constant:** Define `GET_BRAND_LEGAL_ENTITIES_QUERY`:

```graphql
query GetBrandLegalEntities($searchInput: SearchInput!) {
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
            registeredEntities(first: 5) {
              edges {
                node {
                  name
                  registeredEntityType
                  formationDate
                  formationYear
                  registrations(first: 20) {
                    edges {
                      node {
                        registrationState
                        jurisdictionType
                        homeJurisdictionState
                        registeredName
                        fileNumber
                        issueDate
                        status
                        subStatus
                        statusDetail
                      }
                    }
                  }
                }
              }
            }
            persons(first: 10) {
              edges {
                node {
                  firstName
                  lastName
                  fullName
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
async def get_brand_legal_entities(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed with `missing_required_inputs`.

**SearchInput:** `{ id: brand_id, entityType: "BRAND" }` — same as how `get_card_analytics()` does a brand-by-ID lookup.

**Call:** Use `_graphql_post(api_key=api_key, action="get_brand_legal_entities", query=GET_BRAND_LEGAL_ENTITIES_QUERY, variables={"searchInput": search_input})`. The returned `brand` dict contains the `legalEntities` connection.

**Response mapping:** Extract `brand.get("legalEntities", {}).get("edges", [])`. For each LegalEntity edge node:
- `enigma_legal_entity_id`: `node.get("id")` or `node.get("enigmaId")`
- `legal_entity_type`: `node.get("legalEntityType")`
- `registered_entities`: list of registered entity dicts (see below)
- `persons`: list of person dicts (firstName, lastName, fullName)

For each RegisteredEntity edge node:
- `name`, `registered_entity_type` (from `registeredEntityType`), `formation_date` (from `formationDate`), `formation_year` (from `formationYear`)
- `registrations`: list of registration dicts (see fields above, mapped to snake_case)

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "legal_entity_count": int,
    "legal_entities": [
        {
            "enigma_legal_entity_id": str,
            "legal_entity_type": str | None,
            "registered_entities": [
                {
                    "name": str | None,
                    "registered_entity_type": str | None,
                    "formation_date": str | None,
                    "formation_year": int | None,
                    "registrations": [
                        {
                            "registration_state": str | None,
                            "jurisdiction_type": str | None,
                            "home_jurisdiction_state": str | None,
                            "registered_name": str | None,
                            "file_number": str | None,
                            "issue_date": str | None,
                            "status": str | None,
                            "sub_status": str | None,
                            "status_detail": str | None,
                        },
                        ...
                    ],
                },
                ...
            ],
            "persons": [
                {
                    "full_name": str | None,
                    "first_name": str | None,
                    "last_name": str | None,
                },
                ...
            ],
        },
        ...
    ],
}
```

If no legal entities found, return `status: "not_found"`.

---

### Adapter 1c: `get_brand_address_deliverability()`

**Purpose:** Check USPS deliverability for all locations under a brand. Critical for Lob direct mail — identifies vacant, virtual (CMRA), and undeliverable addresses before spending postage.

**GraphQL query constant:** Define `GET_BRAND_ADDRESS_DELIVERABILITY_QUERY`. This query traverses `Brand → operatingLocations → addresses → deliverabilities`:

```graphql
query GetBrandAddressDeliverability($searchInput: SearchInput!, $locationLimit: Int!) {
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
                  streetAddress1
                  city
                  state
                  zip
                  deliverabilities(first: 1) {
                    edges {
                      node {
                        rdi
                        deliveryType
                        deliverable
                        virtual
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
  }
}
```

**Function signature:**

```python
async def get_brand_address_deliverability(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 25,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `brand_id` → failed.

**SearchInput:** `{ id: brand_id, entityType: "BRAND" }`. Variables: `{ searchInput: ..., locationLimit: safe_limit }` where `safe_limit = max(1, min(limit, 100))`.

**Call:** Use `_graphql_post()`. The returned `brand` dict contains the `operatingLocations` connection.

**Response mapping:** Iterate `brand.get("operatingLocations", {}).get("edges", [])`. For each location, extract:
- `enigma_location_id`: location node `id` or `enigmaId`
- `location_name`: from `names` connection first edge
- From the `addresses` first edge:
  - `full_address`, `street`, `city`, `state`, `postal_code` (from `zip`)
  - From `deliverabilities` first edge: `rdi`, `delivery_type`, `deliverable`, `virtual`

`rdi` values: `"Residential"`, `"Commercial"`, or null. `deliverable` values: `"deliverable"`, `"vacant"`, `"not_deliverable"`, or null. `virtual` values: `"virtual_cmra"`, `"not_virtual"`, or null.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "location_count": int,
    "locations": [
        {
            "enigma_location_id": str,
            "location_name": str | None,
            "full_address": str | None,
            "street": str | None,
            "city": str | None,
            "state": str | None,
            "postal_code": str | None,
            "rdi": str | None,
            "delivery_type": str | None,
            "deliverable": str | None,
            "virtual": str | None,
        },
        ...
    ],
    "deliverable_count": int,
    "vacant_count": int,
    "not_deliverable_count": int,
    "virtual_count": int,
}
```

Compute the summary counts by iterating the locations list and counting by `deliverable` and `virtual` values.

If no locations found, return `status: "not_found"`.

---

### Adapter 1d: `get_brand_technologies()`

**Purpose:** Retrieve payment technology stack for all locations under a brand. Currently covers only 6 processors: Clover, Paypal, Shopify, Square, Stripe, Toast. Premium tier — use deliberately.

**GraphQL query constant:** Define `GET_BRAND_TECHNOLOGIES_QUERY`:

```graphql
query GetBrandTechnologies($searchInput: SearchInput!, $locationLimit: Int!) {
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
            technologiesUseds(first: 3) {
              edges {
                node {
                  technology
                  category
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

**Note on connection name:** The SDL uses `technologiesUseds` (plural with `s`, awkward but correct per the SDL at line ~2200). Use this exact name.

**Function signature:**

```python
async def get_brand_technologies(
    *,
    api_key: str | None,
    brand_id: str | None,
    limit: int = 25,
) -> ProviderAdapterResult:
```

**Guards and call:** Same pattern as `get_brand_address_deliverability()`.

**Response mapping:** For each location, extract technologies from `technologiesUseds` edges. Each technology node has `technology` (string name, e.g., `"Square"`), `category` (e.g., `"payments"`), `firstObservedDate`, `lastObservedDate`.

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "location_count": int,
    "locations_with_technology_count": int,
    "locations": [
        {
            "enigma_location_id": str,
            "location_name": str | None,
            "full_address": str | None,
            "city": str | None,
            "state": str | None,
            "technologies": [
                {
                    "technology": str | None,
                    "category": str | None,
                    "first_observed_date": str | None,
                    "last_observed_date": str | None,
                },
                ...
            ],
        },
        ...
    ],
    "technology_summary": {
        "Square": int,
        "Stripe": int,
        "Toast": int,
        "Clover": int,
        "Shopify": int,
        "Paypal": int,
        "other": int,
    },
}
```

Compute `technology_summary` by iterating all technologies across all locations and counting by `technology` string value. Locations with no technology data should still appear in `locations` (with `technologies: []`). `locations_with_technology_count` is the count of locations that have at least one technology entry.

---

### Adapter 1e: `search_by_person()`

**Purpose:** Find brands, operating locations, and legal entities associated with a person. Reverse lookup: "what businesses is John Smith associated with?" Uses `SearchInput.person` field.

**Important:** This query returns `SearchUnion = LegalEntity | Brand | OperatingLocation` — a mixed list of three different types. `_graphql_post()` uses `_first_brand()` internally which only extracts a single Brand. Do NOT use `_graphql_post()` here. Handle the HTTP call inline, like the pre-refactor code did, and extract the full `data.search` array.

**GraphQL query constant:** Define `SEARCH_BY_PERSON_QUERY`:

```graphql
query SearchByPerson($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
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
    ... on OperatingLocation {
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
            postalCode
          }
        }
      }
      operatingStatuses(first: 1) {
        edges { node { operatingStatus } }
      }
    }
    ... on LegalEntity {
      id
      enigmaId
      legalEntityType
      names(first: 1) {
        edges { node { name } }
      }
    }
  }
}
```

**Function signature:**

```python
async def search_by_person(
    *,
    api_key: str | None,
    first_name: str | None,
    last_name: str | None,
    date_of_birth: str | None = None,
    state: str | None = None,
    city: str | None = None,
    street: str | None = None,
    postal_code: str | None = None,
) -> ProviderAdapterResult:
```

**Guards:** No `api_key` → skipped. No `first_name` or no `last_name` → failed with `missing_required_inputs` (both are required).

**SearchInput construction:**
```python
person_input: dict[str, Any] = {
    "firstName": first_name.strip(),
    "lastName": last_name.strip(),
}
if date_of_birth:
    person_input["dateOfBirth"] = date_of_birth

search_input: dict[str, Any] = {"person": person_input}

address: dict[str, Any] = {}
if state: address["state"] = state.upper()
if city: address["city"] = city.upper()
if street: address["street1"] = street
if postal_code: address["postalCode"] = postal_code
if address: search_input["address"] = address
```

**HTTP handling:** Do the POST inline. On 429 → skip. On 402 → skip. On HTTP error or GraphQL errors → fail. On `data.search` being empty or None → `not_found`.

**Response mapping:** Iterate `data.search`. Determine type of each item by checking which inline fragment fields are present (e.g., if `"legalEntityType"` key is present it's a LegalEntity, if `count` is present it's likely a Brand — but be careful since all three types share `id` and `enigmaId`). A safer heuristic: Brand items have the `count` field (from `count(field: "operatingLocations")`); OperatingLocation items have `operatingStatuses`; LegalEntity items have `legalEntityType`. Map each to a typed dict.

**Return shape (`mapped`):**
```python
{
    "brands": [
        {
            "enigma_brand_id": str,
            "brand_name": str | None,
            "website": str | None,
            "location_count": int | None,
        },
        ...
    ],
    "operating_locations": [
        {
            "enigma_location_id": str,
            "location_name": str | None,
            "full_address": str | None,
            "city": str | None,
            "state": str | None,
            "postal_code": str | None,
            "operating_status": str | None,
        },
        ...
    ],
    "legal_entities": [
        {
            "enigma_legal_entity_id": str,
            "legal_entity_type": str | None,
            "name": str | None,
        },
        ...
    ],
    "total_returned": int,
}
```

---

### Adapter 1f: `get_brand_industries()`

**Purpose:** Retrieve industry classification for a brand. Returns NAICS, SIC, and Enigma-proprietary industry codes with descriptions.

**GraphQL query constant:** Define `GET_BRAND_INDUSTRIES_QUERY`:

```graphql
query GetBrandIndustries($searchInput: SearchInput!) {
  search(searchInput: $searchInput) {
    ... on Brand {
      id
      enigmaId
      industries(first: 20) {
        edges {
          node {
            industryDesc
            industryCode
            industryType
          }
        }
      }
    }
  }
}
```

**Function signature:**

```python
async def get_brand_industries(
    *,
    api_key: str | None,
    brand_id: str | None,
) -> ProviderAdapterResult:
```

**Guards and call:** Same as `get_brand_legal_entities()`. Use `_graphql_post()`.

**Response mapping:** Extract `brand.get("industries", {}).get("edges", [])`. Each edge node has `industryDesc`, `industryCode`, `industryType` (values include `"NAICS"`, `"SIC"`, and Enigma-proprietary types).

**Return shape (`mapped`):**
```python
{
    "enigma_brand_id": brand_id,
    "industry_count": int,
    "industries": [
        {
            "industry_desc": str | None,
            "industry_code": str | None,
            "industry_type": str | None,
        },
        ...
    ],
    "naics_codes": [str, ...],   # Filter where industryType == "NAICS", extract industryCode
    "sic_codes": [str, ...],     # Filter where industryType == "SIC", extract industryCode
}
```

If no industries found, return `status: "not_found"`.

---

**Commit standalone:** "Add Enigma adapter functions: aggregate, legal entities, address deliverability, technologies, person search, industries"

---

## Deliverable 2: Pydantic contracts

Add to `app/contracts/company_enrich.py` (append to end of file — do NOT overwrite existing contracts):

```python
# --- Enigma aggregate ---

class EnigmaAggregateOutput(BaseModel):
    brands_count: int | None = None
    locations_count: int | None = None
    legal_entities_count: int | None = None
    geography_state: str | None = None
    geography_city: str | None = None
    operating_status_filter: str | None = None
    source_provider: str = "enigma"


# --- Enigma legal entities ---

class EnigmaRegistrationItem(BaseModel):
    registration_state: str | None = None
    jurisdiction_type: str | None = None
    home_jurisdiction_state: str | None = None
    registered_name: str | None = None
    file_number: str | None = None
    issue_date: str | None = None
    status: str | None = None
    sub_status: str | None = None
    status_detail: str | None = None


class EnigmaRegisteredEntityItem(BaseModel):
    name: str | None = None
    registered_entity_type: str | None = None
    formation_date: str | None = None
    formation_year: int | None = None
    registrations: list[EnigmaRegistrationItem] | None = None


class EnigmaLegalEntityPersonItem(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None


class EnigmaLegalEntityItem(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_type: str | None = None
    registered_entities: list[EnigmaRegisteredEntityItem] | None = None
    persons: list[EnigmaLegalEntityPersonItem] | None = None


class EnigmaLegalEntitiesOutput(BaseModel):
    enigma_brand_id: str | None = None
    legal_entity_count: int | None = None
    legal_entities: list[EnigmaLegalEntityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma address deliverability ---

class EnigmaDeliverabilityItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    rdi: str | None = None
    delivery_type: str | None = None
    deliverable: str | None = None
    virtual: str | None = None


class EnigmaAddressDeliverabilityOutput(BaseModel):
    enigma_brand_id: str | None = None
    location_count: int | None = None
    deliverable_count: int | None = None
    vacant_count: int | None = None
    not_deliverable_count: int | None = None
    virtual_count: int | None = None
    locations: list[EnigmaDeliverabilityItem] | None = None
    source_provider: str = "enigma"


# --- Enigma technologies ---

class EnigmaTechnologyItem(BaseModel):
    technology: str | None = None
    category: str | None = None
    first_observed_date: str | None = None
    last_observed_date: str | None = None


class EnigmaLocationTechnologyItem(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    city: str | None = None
    state: str | None = None
    technologies: list[EnigmaTechnologyItem] | None = None


class EnigmaTechnologiesOutput(BaseModel):
    enigma_brand_id: str | None = None
    location_count: int | None = None
    locations_with_technology_count: int | None = None
    locations: list[EnigmaLocationTechnologyItem] | None = None
    technology_summary: dict[str, int] | None = None
    source_provider: str = "enigma"


# --- Enigma person search ---

class EnigmaPersonBrandResult(BaseModel):
    enigma_brand_id: str | None = None
    brand_name: str | None = None
    website: str | None = None
    location_count: int | None = None


class EnigmaPersonLocationResult(BaseModel):
    enigma_location_id: str | None = None
    location_name: str | None = None
    full_address: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    operating_status: str | None = None


class EnigmaPersonLegalEntityResult(BaseModel):
    enigma_legal_entity_id: str | None = None
    legal_entity_type: str | None = None
    name: str | None = None


class EnigmaPersonSearchOutput(BaseModel):
    brands: list[EnigmaPersonBrandResult] | None = None
    operating_locations: list[EnigmaPersonLocationResult] | None = None
    legal_entities: list[EnigmaPersonLegalEntityResult] | None = None
    total_returned: int | None = None
    source_provider: str = "enigma"


# --- Enigma industries ---

class EnigmaIndustryItem(BaseModel):
    industry_desc: str | None = None
    industry_code: str | None = None
    industry_type: str | None = None


class EnigmaIndustriesOutput(BaseModel):
    enigma_brand_id: str | None = None
    industry_count: int | None = None
    industries: list[EnigmaIndustryItem] | None = None
    naics_codes: list[str] | None = None
    sic_codes: list[str] | None = None
    source_provider: str = "enigma"
```

**Commit standalone:** "Add Enigma Pydantic contracts: aggregate, legal entities, deliverability, technologies, person search, industries"

---

## Deliverable 3: Service functions

Add six service functions to `app/services/company_operations.py`. Follow the exact pattern of `execute_company_enrich_card_revenue()` and `execute_company_enrich_locations()`. Study those functions carefully — the context extraction pattern (`_as_dict(input_data.get("cumulative_context"))`), the `run_id`, `operation_id`, `status`, `output`, `provider_attempts` result dict shape, and the `EnigmaXOutput(**mapped).model_dump()` validation step are all required.

Each function extracts inputs from `input_data` first, then from `cumulative_context` as fallback.

---

### Service 3a: `execute_company_search_enigma_aggregate()`

```python
async def execute_company_search_enigma_aggregate(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `state` — from `input_data.get("state")` or context
- `city` — from `input_data.get("city")` or context
- `operating_status_filter` — from `input_data.get("operating_status_filter")` or context (optional)

**Missing-inputs guard:** If no `state` AND no `city` → return failed immediately without calling the adapter.

**Adapter call:** `enigma.aggregate_locations(api_key=..., state=..., city=..., operating_status_filter=...)`

**Output validation:** `EnigmaAggregateOutput(**mapped).model_dump()`

**Operation ID:** `"company.search.enigma.aggregate"`

---

### Service 3b: `execute_company_enrich_enigma_legal_entities()`

```python
async def execute_company_enrich_enigma_legal_entities(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `enigma_brand_id` — from `input_data` or context. Required.

**Missing-inputs guard:** If no `enigma_brand_id` → failed.

**Adapter call:** `enigma.get_brand_legal_entities(api_key=..., brand_id=enigma_brand_id)`

**Output validation:** `EnigmaLegalEntitiesOutput(**mapped).model_dump()`

**Operation ID:** `"company.enrich.enigma.legal_entities"`

---

### Service 3c: `execute_company_enrich_enigma_address_deliverability()`

```python
async def execute_company_enrich_enigma_address_deliverability(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `enigma_brand_id` — required
- `limit` — from `input_data.get("limit")` or `step_config.get("limit")`, default 25, clamped 1–100

**Adapter call:** `enigma.get_brand_address_deliverability(api_key=..., brand_id=..., limit=...)`

**Output validation:** `EnigmaAddressDeliverabilityOutput(**mapped).model_dump()`

**Operation ID:** `"company.enrich.enigma.address_deliverability"`

---

### Service 3d: `execute_company_enrich_enigma_technologies()`

```python
async def execute_company_enrich_enigma_technologies(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `enigma_brand_id` — required
- `limit` — default 25, clamped 1–100

**Adapter call:** `enigma.get_brand_technologies(api_key=..., brand_id=..., limit=...)`

**Output validation:** `EnigmaTechnologiesOutput(**mapped).model_dump()`

**Operation ID:** `"company.enrich.enigma.technologies"`

---

### Service 3e: `execute_company_search_enigma_person()`

```python
async def execute_company_search_enigma_person(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `first_name` — required
- `last_name` — required
- `date_of_birth` — optional
- `state`, `city`, `street`, `postal_code` — optional geographic filters

**Missing-inputs guard:** If no `first_name` or no `last_name` → failed.

**Adapter call:** `enigma.search_by_person(api_key=..., first_name=..., last_name=..., date_of_birth=..., state=..., city=..., street=..., postal_code=...)`

**Output validation:** `EnigmaPersonSearchOutput(**mapped).model_dump()`

**Operation ID:** `"company.search.enigma.person"`

---

### Service 3f: `execute_company_enrich_enigma_industries()`

```python
async def execute_company_enrich_enigma_industries(*, input_data: dict[str, Any]) -> dict[str, Any]:
```

**Inputs:**
- `enigma_brand_id` — required

**Adapter call:** `enigma.get_brand_industries(api_key=..., brand_id=enigma_brand_id)`

**Output validation:** `EnigmaIndustriesOutput(**mapped).model_dump()`

**Operation ID:** `"company.enrich.enigma.industries"`

---

**Commit standalone:** "Add Enigma service functions: aggregate, legal entities, deliverability, technologies, person search, industries"

---

## Deliverable 4: Wire into execute router

In `app/routers/execute_v1.py`:

**Step 1:** Import the six new service functions at the top (find the existing Enigma service function import block and add to it):

```python
from app.services.company_operations import (
    # ... existing imports ...
    execute_company_enrich_enigma_address_deliverability,
    execute_company_enrich_enigma_industries,
    execute_company_enrich_enigma_legal_entities,
    execute_company_enrich_enigma_technologies,
    execute_company_search_enigma_aggregate,
    execute_company_search_enigma_person,
)
```

**Step 2:** Add all six to `SUPPORTED_OPERATION_IDS` (find the existing Enigma entries at ~lines 159–176 and add after them):

```python
"company.search.enigma.aggregate",
"company.enrich.enigma.legal_entities",
"company.enrich.enigma.address_deliverability",
"company.enrich.enigma.technologies",
"company.search.enigma.person",
"company.enrich.enigma.industries",
```

**Step 3:** Add dispatch branches following the existing pattern (near lines 617–640). Each branch is:

```python
if payload.operation_id == "company.search.enigma.aggregate":
    result = await execute_company_search_enigma_aggregate(input_data=payload.input)
    await persist_operation_execution(result, db=db, api_token=api_token)
    return DataEnvelope(data=result)
```

Add one block for each of the six operations. Follow the exact same dispatch shape — the existing Enigma blocks are the reference.

**Commit standalone:** "Wire six new Enigma operations into execute router"

---

## Deliverable 5: Investigate negative news and government archive

These two MCP tools are listed in `docs/api-reference-docs/enigma/07-use-enigma-with-ai-via-mcp/01-mcp-tools.md`:
- `search_negative_news` — inputs: business name + address; outputs: risk findings by category
- `search_gov_archive` — inputs: business name + prompt context; outputs: government records

**Investigation task:**

1. Read `docs/api-reference-docs/enigma/07-use-enigma-with-ai-via-mcp/01-mcp-tools.md` fully.
2. Read the Appendix of `docs/ENIGMA_API_REFERENCE.md` (MCP tools section).
3. Search `docs/api-reference-docs/enigma/` for any file that documents a GraphQL query or REST endpoint for `search_negative_news` or `search_gov_archive`. Check every subdirectory.
4. Search `docs/api-reference-docs/enigma/08-reference/02-graphql-api-reference.md` for any `Query` field or type that could correspond to these tools.

**Decision rule:**

- If you find a documented GraphQL query or REST endpoint with a known URL and request/response shape → implement it following the same adapter pattern as Deliverable 1. Add to this commit.
- If you find partial documentation (e.g., endpoint URL but unknown request shape, or request shape but no endpoint) → document what was found in the work log entry. Do not implement. Flag for the chief agent to verify with Enigma support.
- If you find no REST/GraphQL documentation at all (only MCP tool descriptions) → document that finding in the work log entry. Do not guess or implement. The operations remain out of scope.

Do not implement either operation if the API surface is not documented in the repo. Do not call the live Enigma API to discover the endpoint shape.

**No separate commit is needed for this deliverable unless an operation is implemented.** The findings go into the work log entry.

---

## Final Deliverable: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary: built 6 new Enigma operations callable via `/api/v1/execute` — `company.search.enigma.aggregate` (market sizing via aggregate query), `company.enrich.enigma.legal_entities` (SoS registration and ownership data, Premium tier), `company.enrich.enigma.address_deliverability` (USPS deliverability for direct mail, Plus tier), `company.enrich.enigma.technologies` (payment processor detection, Premium tier), `company.search.enigma.person` (person reverse lookup), `company.enrich.enigma.industries` (NAICS/SIC classification, Core tier). Include findings on `search_negative_news` / `search_gov_archive` investigation — confirm whether they were implemented, skipped, or flagged.

This is your final commit.

---

## What is NOT in scope

- **No changes to `trigger/src/`** — these operations are callable via `/api/v1/execute` only. No dedicated Trigger.dev workflow for this batch. The existing `enigma-smb-discovery` workflow can call them via the execute endpoint if needed.
- **No new database migrations** — no new tables required. These operations return data in the operation output; persistence to dedicated tables is a future concern.
- **No changes to `run-pipeline.ts`** — never.
- **No deploy commands.** Do not push.
- **No blueprint definitions** — the operations are wired for ad-hoc execute calls. Blueprint integration is a chief agent decision.
- **No modifications to existing Enigma operations** (`company.enrich.card_revenue`, `company.enrich.locations`, `company.search.enigma.brands`). These are complete and working.
- **No persistence registry changes** — if `app/services/persistence_registry.py` does not exist, skip entirely.
- **No production API calls to Enigma** — do not call the live API to test or discover endpoint shapes.
- **No test files** — tests are out of scope for this directive.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:

(a) **Adapters:** for each of the 6 adapter functions, confirm the GraphQL query used and any deviation from the spec above. Flag any field name that differed from the SDL.

(b) **Contracts:** count of new Pydantic models added, confirm they were appended without overwriting existing models.

(c) **Services:** list all 6 function names and their operation IDs. Confirm the input extraction pattern matches existing Enigma service functions.

(d) **Router:** confirm all 6 operation IDs are in `SUPPORTED_OPERATION_IDS`. Confirm all 6 dispatch branches are present and follow the existing pattern.

(e) **Aggregate credit cost:** after reading the docs, confirm whether `aggregate` calls consume credits. Note the finding.

(f) **Negative news + gov archive:** state what documentation was found (or not found) for each tool. State whether either was implemented or skipped.

(g) **Persistence registry:** state whether `app/services/persistence_registry.py` exists and whether the skip note applies.

(h) **Anything to flag:** SDL field names that differed from the directive, type ambiguities (e.g., if `legalEntityType` is not directly on `LegalEntity`), any Premium-tier operations where the credit cost was significantly different from the estimate.
