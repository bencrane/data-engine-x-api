# Directive: Socrata API Reference Summary for FMCSA Carrier Queries

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need a single in-repo reference that distills the Socrata/SODA documentation into something operationally useful for engineers and agents querying FMCSA datasets on `data.transportation.gov`. The repo already contains the raw Socrata reference pages, but they are fragmented across endpoint, auth, paging, query, and support articles. This directive is to consolidate that material into one practical summary focused on per-carrier lookups by identifiers like DOT number, MC number, and related carrier keys.

**Relevant API surface to document:**

- SODA3 query endpoint shape: `https://data.transportation.gov/api/v3/views/{dataset_id}/query.json`
- SODA3 export endpoint shape: `https://data.transportation.gov/api/v3/views/{dataset_id}/export.csv`
- dataset identifier shape: Socrata dataset IDs are eight-character identifiers in the form `xxxx-xxxx`
- query model: SoQL via the `query` payload field, with paging and request options handled through SODA3 request fields

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/01-API Endpoints/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/02-SODA3 Query Syntax/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/03-Query Option Deep Dive/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/04-Authentication/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/05-API Keys/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/06-SoQL Function Reference/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/07-Paging Through Data/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/08-Application Tokens/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/09-Response Codes & Headers/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/10-System Fields/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/11-Row Identifiers/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/12-JSON Format/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/13-SODA3 API Overview (Support)/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/14-API Keys FAQ (Support)/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/15-Generating App Tokens & API Keys (Support)/overview.md`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/socrata/16-FMCSA Dataset Endpoint/overview.md`

---

### Deliverable 1: Comprehensive Socrata Reference Summary

Create `/Users/benjamincrane/data-engine-x-api/docs/SOCRATA_API_REFERENCE_SUMMARY.md`.

The document must be a single, comprehensive markdown reference that an engineer or AI agent can read to understand how to query FMCSA carrier-related datasets hosted on `data.transportation.gov` via Socrata.

Required content:

- explain what Socrata/SODA is and what it enables in practice for this repo's FMCSA work
- explain the difference between row-level querying and bulk export
- explain how to target a specific dataset by dataset ID
- explain the SODA3 endpoint shapes for `/query` and `/export`
- explain request identification and authentication options, including:
  - app tokens
  - API keys
  - HTTP Basic authentication
  - the distinction between user-authenticated access and app-token-identified public reads
- explain rate limits and throttling behavior, including:
  - lower limits without an app token
  - application-level attribution with an app token
  - `429 Too Many Requests`
  - the fact that some documentation indicates SODA3 requests must identify the caller, while older guidance discusses limited unauthenticated access
- explain the core query model and the practically useful SoQL clauses:
  - `SELECT`
  - `WHERE`
  - `ORDER BY`
  - `LIMIT`
  - `OFFSET`
  - `GROUP BY`
  - `HAVING`
  - relevant text matching helpers such as `like`, `starts_with`, `in`, and related filtering patterns
- explain pagination and ordering behavior, including:
  - SODA3 `page` request object
  - performance degradation at high page numbers
  - preference for targeted filters over deep paging
  - when manual `LIMIT` and `OFFSET` appear in docs and why `page` is preferred in SODA3
- explain response formats and export formats that are relevant to engineering use, including JSON and CSV, and mention other formats only if the docs explicitly support them
- explain response codes and useful headers, especially anything relevant to debugging, throttling, caching, or schema inspection
- explain system fields and row identifiers only to the extent they are useful for FMCSA querying, dataset change detection, or stable row tracking
- include a section specifically titled around FMCSA practical usage on `data.transportation.gov`

The FMCSA practical-usage section must:

- translate the generic Socrata docs into practical guidance for FMCSA carrier lookups
- explain how an engineer should think about finding the correct dataset ID first, then querying that dataset
- explain that per-carrier enrichment queries will generally depend on dataset-specific field names, not on a universal Socrata carrier schema
- explicitly frame DOT number, MC number, and similar carrier identifiers as dataset-column-dependent filters that must be mapped per FMCSA dataset
- explain when `/query` is the right tool versus when `/export` is the right tool
- include concrete examples in prose of the kinds of filters an engineer would likely need, without turning the document into a generic tutorial or implementation guide

Hard requirements:

- read every file listed above before writing the summary
- produce exactly one new output file: `/Users/benjamincrane/data-engine-x-api/docs/SOCRATA_API_REFERENCE_SUMMARY.md`
- do not modify any application code, tests, migrations, or existing docs beyond creating that one summary file
- do not invent unsupported Socrata behavior; if the source docs are ambiguous or internally inconsistent, say so explicitly in the summary
- where the source docs appear to conflict, preserve the conflict honestly and state which guidance appears newer or more SODA3-specific
- keep the document practical and FMCSA-oriented rather than a broad Socrata encyclopedia
- prefer clear sections, short examples, and explicit constraints over marketing language

Recommended structure:

- overview
- endpoint model
- authentication and identification
- query mechanics
- pagination, limits, and ordering
- dataset targeting by dataset ID
- bulk export vs row-level query
- response formats, status codes, and useful headers
- practical FMCSA query guidance
- gotchas and constraints

Commit standalone.

---

**What is NOT in scope:** No code changes. No provider integrations. No FMCSA dataset-by-dataset field mapping document. No validation against live endpoints. No browser automation. No scripts. No new tests. No changes to any existing files besides creating `/Users/benjamincrane/data-engine-x-api/docs/SOCRATA_API_REFERENCE_SUMMARY.md`. No deploy commands.

**Commit convention:** One commit only. Do not push.

**When done:** Report back with: (a) confirmation that every listed Socrata source file was read, (b) the path to the created summary document, (c) the major sections included in the summary, (d) any documentation conflicts or ambiguities surfaced in the source material, especially around SODA3 authentication versus older throttling guidance, and (e) anything to flag that would matter for future FMCSA carrier-query implementation work.
