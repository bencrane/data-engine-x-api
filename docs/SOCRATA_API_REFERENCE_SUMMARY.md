# Socrata API Reference Summary for FMCSA Carrier Queries

## Overview

Socrata's SODA API is the query surface behind datasets hosted on `data.transportation.gov`. For this repo's FMCSA work, the practical use is simple: once you know the correct FMCSA dataset ID and the dataset's field names, you can issue targeted row-level queries for carrier records or download full dataset exports for offline processing.

SODA is not an FMCSA-specific API contract. It is a dataset query platform. That means the platform gives you a consistent endpoint model and query language, but it does **not** give you a universal carrier schema across FMCSA datasets. In practice, per-carrier lookups depend on knowing:

- the correct dataset ID
- the dataset's actual column names
- which carrier identifier columns that dataset exposes

For FMCSA engineering work, the main value of this reference is to separate the stable Socrata mechanics from the dataset-specific mapping work that must happen per feed.

## Endpoint Model

SODA3 documentation consistently points to dataset-specific endpoints built from an eight-character dataset identifier in the form `xxxx-xxxx`.

Canonical SODA3 endpoint shapes:

- Row-level query: `https://data.transportation.gov/api/v3/views/{dataset_id}/query.json`
- Bulk export: `https://data.transportation.gov/api/v3/views/{dataset_id}/export.csv`

Example dataset ID shape:

- `anj8-k6f5`

Important notes from the source docs:

- The docs repeatedly show the `views/{dataset_id}` form.
- One endpoint overview sentence mentions `/api/v3/IDENTIFIER/query.json` without `views/`; the surrounding examples use `/api/v3/views/{dataset_id}/query.json`. The `views/{dataset_id}` shape appears to be the more concrete and consistently demonstrated SODA3 form.
- The docs recommend `POST` for `/query`, because it supports longer queries and clearer request options.
- `/export` is a separate endpoint meant for file-style retrieval rather than richer interactive query control.

## Dataset Targeting by Dataset ID

Every dataset has its own Socrata ID. That ID is the first thing an engineer needs before writing any FMCSA query logic.

How to think about targeting a dataset:

1. Identify the correct FMCSA dataset on `data.transportation.gov`.
2. Capture its dataset ID.
3. Inspect that dataset's field list and API docs.
4. Determine which columns correspond to the carrier keys you care about.
5. Only then write per-carrier queries.

This matters because Socrata gives you a uniform transport and query layer, but FMCSA datasets do not share one guaranteed carrier schema. A DOT number in one dataset may be named differently from a DOT number in another dataset. MC number, docket number, carrier name, legal name, or related identifiers are all dataset-column-dependent, not platform-global.

## Authentication And Identification

The source material describes several ways to identify or authenticate requests.

### App Tokens

App tokens identify the calling application. They are sent most clearly via:

- `X-App-Token` header

Older docs also mention token-in-URL parameter styles. For SODA3, the docs strongly prefer header-based identification and `POST` requests.

What app tokens do in practice:

- attribute usage to an application instead of only an IP address
- raise throttling tolerance compared with anonymous/shared-IP traffic
- satisfy the SODA3 requirement that public-read requests identify the caller, when full user auth is not needed

App tokens are primarily an identification mechanism for public reads, not a substitute for user permissions on private assets.

### API Keys

API keys are personal user credentials consisting of:

- `keyId`
- `keySecret`

They are used through HTTP Basic authentication, with `keyId` as username and `keySecret` as password. API keys act as a proxy for a real user account and inherit that user's rights.

Practical implication:

- Use API keys when your FMCSA workflow needs authenticated user context, or when your organization standardizes on user-bound automation rather than app-token-only public reads.

### HTTP Basic Authentication

The authentication docs describe HTTP Basic as the supported non-interactive authentication method. Basic auth can use either:

- username + password
- API key ID + key secret

All authenticated requests must use HTTPS.

### OAuth / User-Authenticated Access

The generic Socrata authentication docs also describe OAuth 2.0 for interactive applications acting on behalf of a user. That is usually less relevant for backend FMCSA ingestion or carrier lookup jobs in this repo, but it matters conceptually because it reinforces the distinction between:

- user-authenticated access: request is acting as a real user with that user's permissions
- app-token-identified public access: request identifies the application, but is still only appropriate for public reads

### What The Newer SODA3 Docs Emphasize

The newer SODA3 docs and support article are explicit that SODA3 requests must identify the caller, either by:

- user authentication
- app token on public datasets

That is the most SODA3-specific guidance in the source set and should be treated as the safer default assumption for new engineering work.

## Rate Limits And Throttling

The docs present throttling in two layers: older app-token guidance and newer SODA3 caller-identification guidance.

Practical conclusions:

- Without an app token, docs describe much lower limits and throttling based mainly on shared IP criteria.
- With an app token, usage is attributed to the application rather than only to IP.
- Older app-token docs say tokened requests are generally not throttled unless abusive or malicious.
- If throttled, the platform returns `429 Too Many Requests`.

Important documentation tension:

- Older guidance says simple unauthenticated public queries may still work, just with much lower limits.
- Newer SODA3 guidance says requests must be user-authenticated or identified by app token.

For new FMCSA work on SODA3 endpoints, the more current and more SODA3-specific interpretation is:

- assume caller identification is required
- use an app token even for public FMCSA dataset reads
- do not design production query paths around anonymous access

## Query Mechanics

SODA3 uses SoQL in the `query` request field. The docs recommend sending the request body as JSON to the `/query` endpoint.

Core request options explicitly documented for `/query`:

- `query`
- `page`
- `parameters`
- `timeout`
- `includeSystem`
- `includeSynthetic`
- `orderingSpecifier`

The SoQL clauses most useful for FMCSA work are below.

### `SELECT`

Use `SELECT` to control the returned columns.

Examples:

```sql
SELECT *
SELECT `dot_number`, `legal_name`
SELECT `dot_number` AS `usdot_number`
```

The docs say `SELECT` is required. Backticks around column names are recommended.

### `WHERE`

Use `WHERE` for per-carrier filtering and general record selection.

Examples:

```sql
SELECT * WHERE `dot_number` = '123456'
SELECT * WHERE `mc_number` = '78910'
SELECT * WHERE `legal_name` like '%LOGISTICS%'
SELECT * WHERE starts_with(`legal_name`, 'ABC')
SELECT * WHERE `state` in('TX', 'OK')
```

Boolean operators supported in the docs include:

- `AND`
- `OR`
- `NOT`
- `IS NULL`
- `IS NOT NULL`

For FMCSA carrier lookups, this is usually the most important clause.

### `ORDER BY`

Use `ORDER BY` when you need deterministic sorting, especially if multiple rows may match a carrier filter.

Example:

```sql
SELECT * WHERE `dot_number` = '123456' ORDER BY `:updated_at` DESC
```

### `LIMIT`

Use `LIMIT` to cap returned rows.

Example:

```sql
SELECT * WHERE `dot_number` = '123456' LIMIT 5
```

### `OFFSET`

The docs say `OFFSET` exists, but SODA3 guidance prefers the `page` request object over manual `LIMIT`/`OFFSET` paging.

### `GROUP BY`

Useful for aggregations, counts, and profiling dataset contents.

Example:

```sql
SELECT `state`, count(*) AS `carrier_count` GROUP BY `state`
```

### `HAVING`

Use `HAVING` to filter aggregated results.

Example:

```sql
SELECT `state`, count(*) AS `carrier_count`
GROUP BY `state`
HAVING `carrier_count` > 1000
```

### Text Matching And Filtering Helpers

The function reference explicitly lists several helpers that are practically useful for carrier-oriented searching:

- `like`
- `not like`
- `starts_with(...)`
- `in(...)`
- `not in(...)`
- `lower(...)`
- `upper(...)`
- `distinct`

Practical filtering patterns for FMCSA datasets:

- exact identifier matches for DOT number or MC number when the dataset has dedicated columns
- prefix text matching when a dataset stores formatted identifiers or leading text patterns
- `in(...)` when checking a small candidate set of values
- case normalization with `lower(...)` or `upper(...)` if the dataset's text conventions are inconsistent

## Pagination, Limits, And Ordering

SODA3 documents a structured `page` request object on `/query`:

```json
{
  "page": {
    "pageNumber": 1,
    "pageSize": 1000
  }
}
```

Documented behavior and guidance:

- `page` is only available on `/query`
- paging is 1-indexed
- the platform imposes an ordering to keep paging consistent
- performance degrades drastically as page number increases
- the docs explicitly advise using filters instead of walking deep pages
- manual `LIMIT` and `OFFSET` exist in SoQL, but the docs say `page` is preferred for SODA3

For FMCSA carrier lookups, the engineering preference should be:

- first try a highly targeted `WHERE` filter on carrier identifiers
- use small pages only when you truly need result browsing
- avoid deep page scans as a primary lookup strategy

There is one documentation inconsistency worth noting:

- SODA3 docs show the `page` object in JSON request bodies
- the dataset-specific `data.transportation.gov` example shows `pageNumber` and `pageSize` in the URL query string

That suggests the platform may support multiple request encodings, but the SODA3-specific guidance still favors `POST` with the structured `page` object.

## Bulk Export Vs Row-Level Query

This distinction matters for FMCSA work.

### Use `/query` When

- you need per-carrier lookups
- you need targeted filters by DOT number, MC number, or other carrier keys
- you want smaller result sets
- you need controlled selection, aggregation, or sorting
- you are building application logic around exact field-level filtering

### Use `/export` When

- you need the whole dataset or a very large slice
- you are doing offline analysis, local joins, or snapshot-style processing
- you want a file-oriented download, especially CSV
- row-level API pagination would be inefficient

The source docs frame `/query` as machine-oriented and customizable, and `/export` as more file-oriented and human-consumable. For this repo, `/query` is the normal tool for targeted enrichment lookups; `/export` is the normal tool for dataset-wide ingestion or offline validation work.

## Response Formats, Status Codes, And Useful Headers

### Formats

The docs explicitly support JSON and CSV in the SODA materials provided here.

Engineering-relevant points:

- `/query.json` returns JSON
- `/export.csv` returns CSV
- JSON responses are arrays of objects keyed by field name
- in JSON, `null` fields are omitted rather than emitted as `"field": null`

Some source docs also mention other formats such as GeoJSON, XML, KML, KMZ, Shapefile, XLSX, and XML in broader platform support language. Those mentions appear in general/platform support context rather than being central to the FMCSA row-query use case. For FMCSA engineering in this repo, JSON and CSV are the primary formats that matter.

### Status Codes

The response-code doc lists these important codes:

- `200 OK`: request succeeded
- `202 Request Processing`: request still processing; retry later
- `400 Bad Request`: malformed request or invalid query
- `401 Unauthorized`: authentication attempt failed
- `403 Forbidden`: caller lacks access
- `404 Not Found`: dataset or resource not found
- `429 Too Many Requests`: throttled
- `500 Server Error`: platform-side failure

### Useful Headers

The docs explicitly document several useful headers, though that page is written around SODA 2.1 terminology rather than a SODA3-specific header contract.

Most practically useful:

- `X-Socrata-RequestId`: include this when debugging failed requests with Socrata support
- `Last-Modified`: can help with cache validation or change checks
- `ETag`: can help with caching and revalidation
- `X-SODA2-Fields`: field names included in the response
- `X-SODA2-Types`: response field types

Constraint:

- the documented field/type headers may be omitted on very wide datasets
- because the header section is written for SODA 2.1, treat those headers as useful when present, but do not assume all SODA3 responses will expose the exact same header set

The error format in the docs is also useful operationally because it includes:

- an error code
- human-readable message
- machine-readable error metadata
- query position details for SoQL parsing/type errors

## System Fields And Row Identifiers

System fields can matter for FMCSA change detection and stable row tracking.

Useful system fields documented:

- `:id`
- `:created_at`
- `:updated_at`

Practical uses:

- `:id` can give you a Socrata-side internal row identifier
- `:updated_at` can help detect changes or retrieve recently modified rows
- `:created_at` can help reason about record creation timing

Important constraint:

- row identifiers may be internal Socrata IDs or publisher-specified identifiers
- publisher-specified identifiers are dataset-defined and not guaranteed across FMCSA datasets

Important documentation conflict:

- the SODA3 request-options page says `includeSystem` defaults to `true`
- the system-fields page says system fields are not included by default

Because those docs do not reconcile the difference explicitly, treat system-field inclusion as something to request deliberately when you need it, rather than depending on defaults.

## Practical FMCSA Query Guidance On `data.transportation.gov`

For FMCSA work, the correct mental model is:

1. find the correct FMCSA dataset first
2. inspect that dataset's field names
3. identify which columns represent carrier identifiers
4. issue targeted queries against that dataset

Do **not** assume Socrata itself knows what a carrier is, or that DOT number / MC number fields will have one universal name across FMCSA datasets.

### How To Approach Per-Carrier Lookups

Per-carrier enrichment queries will usually be shaped around dataset-specific columns such as:

- DOT number column
- MC number or docket column
- legal name or DBA name column
- state, address, status, or census-related carrier attributes

But those are dataset-level semantics, not Socrata platform semantics. The platform only guarantees the query interface, not the FMCSA business schema.

### DOT Number, MC Number, And Related Keys

DOT number, MC number, and similar carrier identifiers should be treated as dataset-column-dependent filters. Before implementation, each FMCSA dataset needs its own explicit field mapping.

Examples of the kinds of filters an engineer will likely need:

- exact match on a DOT-number column when retrieving a single carrier row
- exact or normalized match on an MC-number column when the dataset tracks operating authority or registration records
- fallback matching on carrier legal name or state when no single identifier is sufficient
- filtered queries on recently updated records using a dataset timestamp or system timestamp when building differential sync logic

### When `/query` Is The Right Tool

Use `/query` for:

- single-carrier or few-carrier lookups
- API-driven enrichment
- filtering by known identifiers
- compact result sets
- aggregation or debugging queries during schema exploration

### When `/export` Is The Right Tool

Use `/export` for:

- full-feed ingestion
- local snapshot analysis
- validating row counts or performing wide offline comparisons
- workflows where repeatedly paging through the API would be inefficient

### Recommended Engineering Bias For FMCSA

- prefer exact identifier filters over name-based searches whenever the dataset exposes stable carrier keys
- prefer dataset-specific field mapping documents over assumptions from other FMCSA feeds
- prefer targeted `/query` calls over deep paging
- prefer `/export` for bulk backfills and dataset-wide inspection
- always identify the caller with an app token at minimum for public datasets

## Gotchas And Constraints

- SODA provides a common query platform, not a universal FMCSA carrier schema.
- Dataset IDs are mandatory; there is no query without the correct `xxxx-xxxx` target.
- SODA3 docs favor `POST` JSON requests to `/query`; some dataset pages still show GET-style querystring examples.
- Newer SODA3 guidance says requests must identify the caller; older docs still discuss limited unauthenticated access with lower throttling.
- App tokens help with attribution and throttling but are not the same as user-authenticated access.
- API keys are effectively user credentials and inherit that user's rights.
- Deep paging is explicitly discouraged for performance reasons.
- `LIMIT` and `OFFSET` exist, but SODA3 docs prefer the `page` object.
- JSON omits `null` fields, which matters when downstream code expects missing-vs-null distinctions.
- System-field default behavior is documented inconsistently; request them intentionally when needed.
- Header guidance in the provided docs is partly framed around SODA 2.1, so treat some headers as helpful but not as a rigid SODA3 contract.

## Working Assumption For Future FMCSA Implementation

For new carrier-query implementation work in this repo, the safest operational assumptions from the provided docs are:

- use `https://data.transportation.gov/api/v3/views/{dataset_id}/query.json`
- send `POST` requests with JSON payloads
- include `X-App-Token` on public-read requests
- use Basic auth with API key credentials when user-authenticated access is needed
- design query logic around dataset-specific field mappings for DOT number, MC number, and related identifiers
- use `/export.csv` for full-feed workflows instead of trying to simulate bulk retrieval through deep paging
