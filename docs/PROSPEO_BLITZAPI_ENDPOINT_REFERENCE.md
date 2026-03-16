# Prospeo & BlitzAPI Endpoint Reference

Reference for API endpoints we call, their inputs, and where they're documented.

---

## Prospeo

### Endpoints We Call

| Endpoint | URL | Used by | Config |
|----------|-----|---------|--------|
| **search-company** | `https://api.prospeo.io/search-company` | `company.search` via `prospeo.search_companies()` | `PROSPEO_API_KEY` |
| **search-person** | `https://api.prospeo.io/search-person` | `person.search` via `prospeo.search_people()` | `PROSPEO_API_KEY` |
| **enrich-company** | `https://api.prospeo.io/enrich-company` | `company.enrich.profile` via `prospeo.enrich_company()` | `PROSPEO_API_KEY` |
| **enrich-person** | `https://api.prospeo.io/enrich-person` | `person.enrich.profile` via `_prospeo_enrich_person()` | `PROSPEO_API_KEY` |

All use `X-KEY` header with `settings.prospeo_api_key`.

### Input Specifications

#### 1. enrich-company (`POST /enrich-company`)

**Request body:**
- `data` (required) — object with at least one of:
  - `company_website` — e.g. `deloitte.com`
  - `company_linkedin_url` — e.g. `https://linkedin.com/company/deloitte`
  - `company_name` — discouraged as sole identifier
  - `company_id` — from a prior Prospeo company object

**What we send:** `company_website`, `company_linkedin_url`, `company_name`, `company_id` (from `source_company_id`). All non-empty values passed.

---

#### 2. enrich-person (`POST /enrich-person`)

**Request body:**
- `data` (required) — object with at least one of:
  - `first_name` + `last_name` + any of (`company_name` / `company_website` / `company_linkedin_url`)
  - `full_name` + any of (`company_name` / `company_website` / `company_linkedin_url`)
  - `linkedin_url` alone
  - `email` alone
  - `person_id` (from Search Person results)
- Optional top-level params (we don't use): `only_verified_email`, `enrich_mobile`, `only_verified_mobile`

**What we send:** `first_name`, `last_name`, `full_name`, `linkedin_url`, `email`, `person_id`, `company_name`, `company_website`, `company_linkedin_url`. We omit the optional flags.

---

#### 3. search-company (`POST /search-company`)

**Request body:**
- `filters` (required) — filter object. At least one positive filter required; cannot use only `exclude`.
- `page` (optional) — default `1`, max `1000`.

**Filter reference:** `docs/api-reference-docs/prospeo/02-search/04-filters-documentation.md`

**API-only filters:** `company.websites` (max 500 domains), `company.names` (max 500 names).

**What we send:** If no `provider_filters.prospeo`, we use `{"company": {"names": {"include": [query]}}}`. Otherwise pass through `provider_filters.prospeo` as-is.

---

#### 4. search-person (`POST /search-person`)

**Request body:**
- `filters` (required) — filter object. Same constraint as search-company.
- `page` (optional) — default `1`, max `1000`.

**Filter reference:** Same filters doc. Person-specific filters include `person_job_title`, `person_department`, `person_seniority`, `person_location_search`, etc.

**API-only filters:** `company.websites`, `company.names`.

**What we send:** If no `provider_filters.prospeo`, we build from:
- `query` / `job_title` → `person_job_title.include`
- `location` → `person_location_search.include`
- `company_domain` → `company.websites.include`
- `company_name` → `company.names.include`
Then merge with `provider_filters.prospeo`.

### Prospeo Gaps

1. **Enums:** Industries (256), Technologies (4,946), Seniorities, Departments, etc. are documented in the filters doc but full lists aren't in the repo. Search Suggestions API (`/search-suggestions`) is referenced for job titles and locations but we don't implement it.
2. **enrich-person options:** We never pass `only_verified_email`, `enrich_mobile`, or `only_verified_mobile`.
3. **search filters:** `person_location_search` and `person_job_title` expect values from Search Suggestions API or dashboard; arbitrary strings may cause `INVALID_FILTERS`.

### Prospeo Not Implemented

- `search-suggestions` — docs only
- `bulk-enrich-company` — docs only
- `bulk-enrich-person` — docs only

---

## BlitzAPI

### Endpoints We Call

All use base URL `https://api.blitz-api.ai/v2` and auth header `x-api-key`.

| Endpoint | URL | Used by |
|----------|-----|---------|
| **domain-to-linkedin** | `POST /v2/enrichment/domain-to-linkedin` | `company.resolve.linkedin_from_domain_blitzapi`, `company.enrich.profile` (bridge), `company.search` (BlitzAPI branch) |
| **enrichment/company** | `POST /v2/enrichment/company` | `company.enrich.profile`, `company.enrich.profile_blitzapi`, `company.search` (BlitzAPI branch) |
| **search/companies** | `POST /v2/search/companies` | `company.search.blitzapi` |
| **search/employee-finder** | `POST /v2/search/employee-finder` | `person.search`, `person.search.employee_finder_blitzapi` |
| **search/waterfall-icp-keyword** | `POST /v2/search/waterfall-icp-keyword` | `person.search` (BlitzAPI waterfall), `person.search.waterfall_icp_blitzapi` |
| **enrichment/phone** | `POST /v2/enrichment/phone` | `person.contact.resolve_mobile_phone` (BlitzAPI branch) |
| **enrichment/email** | `POST /v2/enrichment/email` | `person.contact.resolve_email_blitzapi` |

### Input Specifications

#### 1. domain-to-linkedin (`POST /v2/enrichment/domain-to-linkedin`)

**Request body:**
- `domain` (required) — e.g. `blitz-api.ai`

---

#### 2. enrichment/company (`POST /v2/enrichment/company`)

**Request body:**
- `company_linkedin_url` (required) — e.g. `https://www.linkedin.com/company/blitz-api`

---

#### 3. search/companies (`POST /v2/search/companies`)

**Request body:**
- `company` (optional) — filter object:
  - `keywords`: `{include: string[], exclude: string[]}`
  - `industry`: `{include: string[], exclude: string[]}`
  - `hq`: `{continent: string[], country_code: string[], sales_region: string[], city: {include, exclude}}`
  - `employee_range`: string[] — e.g. `["51-200", "201-500"]`
  - `employee_count`: `{min: int, max: int}` — `max: 0` = unbounded
  - `founded_year`: `{min: int, max: int}`
  - `type`: `{include: string[], exclude: string[]}` — e.g. `Privately Held`, `Public Company`, `Nonprofit`, etc.
  - `name`: `{include: string[], exclude: string[]}`
  - `website`: `{include: string[], exclude: string[]}`
  - `min_linkedin_followers`: int
- `max_results`: 1–50 (default 10)
- `cursor`: string | null — pagination cursor from previous response

**What we send:** Built from `company`, `company_filters`, `keywords`, `industry`, `hq`, `employee_range`, `founded_year_min/max`, `company_type`, `min_linkedin_followers`, `domain`, `company_name`. See `blitzapi_company_search._build_company_filters`.

---

#### 4. search/employee-finder (`POST /v2/search/employee-finder`)

**Request body:**
- `company_linkedin_url` (required)
- `max_results`: 1–100
- `page`: 1+
- `job_level` (optional): string or string[]
- `job_function` (optional): string or string[]
- `country_code` (optional): string or string[]
- `continent` (optional): string[]
- `sales_region` (optional): string[]
- `min_connections_count` (optional): 0–500

---

#### 5. search/waterfall-icp-keyword (`POST /v2/search/waterfall-icp-keyword`)

**Request body:**
- `company_linkedin_url` (required)
- `cascade` (required) — list of tier objects:
  - `include_title`: string[]
  - `exclude_title`: string[]
  - `location`: string[] — e.g. `["WORLD"]`
  - `include_headline_search`: bool
- `max_results`: 1–100

**Default cascade (when not provided):**
```json
[
  {"include_title": ["VP", "Director", "Head of"], "exclude_title": ["intern", "assistant", "junior"], "location": ["WORLD"], "include_headline_search": false},
  {"include_title": ["CEO", "founder", "cofounder", "CTO", "COO", "CRO"], "exclude_title": [], "location": ["WORLD"], "include_headline_search": false}
]
```

**When `query` used in `person_search`:** cascade is `[{"include_title": [query], "exclude_title": ["intern", "assistant", "junior"], "location": ["WORLD"], "include_headline_search": true}]`.

---

#### 6. enrichment/phone (`POST /v2/enrichment/phone`)

**Request body:**
- `person_linkedin_url` (required)

---

#### 7. enrichment/email (`POST /v2/enrichment/email`)

**Request body:**
- `person_linkedin_url` (required)

### BlitzAPI Enum Values (from api-reference-docs)

**continent:** Africa, Antarctica, Asia, Europe, North America, Oceania, South America

**sales_region:** NORAM, LATAM, EMEA, APAC

**job_level:** C-Team, Director, Manager, Other, Staff, VP

**job_function:** Advertising & Marketing, Art Culture and Creative Professionals, Construction, Customer/Client Service, Education, Engineering, Finance & Accounting, General Business & Management, Healthcare & Human Services, Human Resources, Information Technology, Legal, Manufacturing & Production, Operations, Other, Public Administration & Safety, Purchasing, Research & Development, Sales & Business Development, Science, Supply Chain & Logistics, Writing/Editing

**employee_range:** 1-10, 11-50, 51-200, 201-500, 501-1000, 1001-5000, 5001-10000, 10001+

**company type:** Educational, Educational Institution, Government Agency, Nonprofit, Partnership, Privately Held, Public Company, Self-Employed, Self-Owned, Sole Proprietorship

### BlitzAPI Gaps

1. **company_search vs search_companies:** `company_search` (and `enrich_company`) hit `/v2/enrichment/company` for single-company lookup by LinkedIn URL. `search_companies` hits `/v2/search/companies` for multi-company search with filters.
2. **Field normalization:** Industry names, country codes, and other enum fields must match exact normalized values. See BlitzAPI Field Normalization Reference: https://docs.blitz-api.ai/guide/reference/field-normalization

---

## api-reference-docs-new (Submodule)

The submodule lives at `docs/api-reference-docs` and is cloned from `https://github.com/bencrane/api-reference-docs-new.git`.

### BlitzAPI Docs in Submodule

| File | Endpoint |
|------|----------|
| `blitzapi/01-company-search/01-find-companies.md` | `POST /v2/search/companies` |
| `blitzapi/03-company-enrichment/02-domain-to-linkedin-url.md` | `POST /v2/enrichment/domain-to-linkedin` |
| `blitzapi/03-company-enrichment/03-company-enrichment.md` | `POST /v2/enrichment/company` |
| `blitzapi/04-people-search/01-waterfall-icp-search.md` | `POST /v2/search/waterfall-icp-keyword` |
| `blitzapi/04-people-search/02-employee-finder.md` | `POST /v2/search/employee-finder` |
| `blitzapi/02-people-enrichment/03-find-mobile-and-direct-phone.md` | `POST /v2/enrichment/phone` |
| `blitzapi/02-people-enrichment/04-find-work-email.md` | `POST /v2/enrichment/email` |

### BlitzAPI Docs Not Used by Our App

- `01-linkedin-url-to-domain.md` — LinkedIn URL → domain
- `01-reverse-phone-lookup.md`
- `02-reverse-email-lookup.md`
- `05-utilities/01-get-current-date-and-time.md`

### Prospeo Docs in Submodule

Same as in main repo: enrich-person, enrich-company, search-person, search-company, bulk variants, search-suggestions, object schemas.

### Other Providers in Submodule

adyntel, ampleleads, brightdata, clay-native, companyenrich.com, courtlistener, enigma, fmcsa, fmcsa-open-data, hyperbrowser, icypeas, leadmagic, millionverifier, openwebninja, parallel, reoon, sam-gov, shovels, socrata, storeleads, theirstack, trigger.dev, twilio, usa-spending.gov, voicedrop.ai
