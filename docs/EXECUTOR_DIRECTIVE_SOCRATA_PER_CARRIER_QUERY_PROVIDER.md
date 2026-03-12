# Directive: Socrata Per-Carrier Query Provider for FMCSA Datasets

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** This work is the per-carrier enrichment layer for FMCSA datasets hosted on `data.transportation.gov`. It is separate from the FMCSA bulk daily-feed ingestion system. The bulk system downloads whole files on schedule; this new layer performs targeted on-demand Socrata lookups for individual carriers by DOT number or MC number against specific datasets. The correct architecture for this slice is: one generic Socrata query adapter in FastAPI, then thin dataset-specific wrappers that map carrier identifiers to the correct dataset ID and dataset column names. Do not treat this as a generic public SoQL execution feature.

**Socrata API contract for this directive:**

- Endpoint: `POST https://data.transportation.gov/api/v3/views/{dataset_id}/query.json`
- Request body: JSON containing the SoQL query in the `query` field
- Authentication: HTTP Basic using Doppler secrets:
  - `SOCRATA_API_KEY_ID` as username
  - `SOCRATA_API_KEY_SECRET` as password
- Response: JSON rows from the dataset query

**Initial dataset scope:**

Datasets with provided API dataset IDs:

- `Company Census File` — `az4n-8mr2`
- `Carrier - All With History` — `6eyk-hxee`
- `Revocation - All With History` — `sa6p-acbp`
- `Insur - All With History` — `ypjt-5ydn`

Conditional fifth dataset:

- `AuthHist - All With History` — build this wrapper only if you can verify a real Socrata API dataset ID and API field mapping from repo docs or the dataset’s API documentation. Do not invent a dataset ID.

Architectural judgment you must preserve:

- the generic Socrata adapter is an internal provider/service abstraction
- do **not** expose a new arbitrary public `/api/v1/execute` operation that accepts any dataset ID and raw SoQL from callers
- the public execute surface for this directive is only the dataset-specific wrappers

**Existing code to read:**

- `/Users/benjamincrane/data-engine-x-api/CLAUDE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/STRATEGIC_DIRECTIVE.md`
- `/Users/benjamincrane/data-engine-x-api/docs/SOCRATA_API_REFERENCE_SUMMARY.md`
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
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/01-company-census-file/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/data-dictionary.json`
- `/Users/benjamincrane/data-engine-x-api/app/config.py`
- `/Users/benjamincrane/data-engine-x-api/app/providers/common.py`
- `/Users/benjamincrane/data-engine-x-api/app/providers/fmcsa.py`
- `/Users/benjamincrane/data-engine-x-api/app/providers/__init__.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/company_operations.py`
- `/Users/benjamincrane/data-engine-x-api/app/services/search_operations.py`
- `/Users/benjamincrane/data-engine-x-api/app/contracts/company_enrich.py`
- `/Users/benjamincrane/data-engine-x-api/app/contracts/search.py`
- `/Users/benjamincrane/data-engine-x-api/app/routers/execute_v1.py`
- `/Users/benjamincrane/data-engine-x-api/trigger/src/workflows/fmcsa-daily-diff.ts`
- `/Users/benjamincrane/data-engine-x-api/tests/test_fmcsa.py`

---

### Deliverable 1: Dataset Mapping and Operation Contract Lock

Create `docs/FMCSA_SOCRATA_PER_CARRIER_QUERY_MAPPINGS.md`.

For each initial dataset in scope, record:

- dataset name
- dataset ID
- whether API availability is verified
- exact Socrata API field names for:
  - DOT number filter
  - MC/docket filter, if supported
  - legal name / carrier name fields, if relevant
- whether DOT lookup is supported
- whether MC lookup is supported
- if MC lookup requires dataset-specific multi-column logic, document the exact rule
- proposed operation ID
- expected wrapper input requirements
- expected output summary shape
- any dataset-specific caveats

Hard requirements:

- do not guess field names from human-readable labels alone if the actual Socrata field names differ
- use the FMCSA dictionaries and any already-verified in-repo Socrata header mappings to determine the real queryable field names
- for datasets already represented in `trigger/src/workflows/fmcsa-daily-diff.ts` as Socrata-backed CSV exports, use that file as a reference point for the already-known header names
- for `AuthHist - All With History`, do not build a wrapper unless you can verify the API dataset ID and field mapping

Proposed operation IDs for this directive:

- `company.enrich.fmcsa.company_census`
- `company.enrich.fmcsa.carrier_all_history`
- `company.enrich.fmcsa.revocation_all_history`
- `company.enrich.fmcsa.insur_all_history`
- `company.enrich.fmcsa.authhist_all_history` only if verified

Commit standalone.

### Deliverable 2: Generic Internal Socrata Query Adapter

Build one generic Socrata adapter as an internal provider abstraction.

Create:

- `app/providers/socrata.py`

Update as needed:

- `app/providers/__init__.py`
- `app/config.py`

Adapter requirements:

- use `httpx`
- use HTTP Basic auth with `SOCRATA_API_KEY_ID` and `SOCRATA_API_KEY_SECRET`
- issue `POST` requests to `https://data.transportation.gov/api/v3/views/{dataset_id}/query.json`
- send JSON request bodies with at minimum the `query` field
- return rows parsed from JSON along with provider attempt metadata via `ProviderAdapterResult`
- surface HTTP status, duration, and raw response/error details in the provider attempt
- handle expected failure classes such as `400`, `401`, `403`, `404`, `429`, and `500`

Scope rule:

- keep this adapter internal-only
- do **not** add a generic externally callable operation that accepts arbitrary dataset IDs or arbitrary raw SoQL from users

You may add small helper functions for:

- building safe SoQL queries from dataset-specific filters
- normalizing DOT/MC inputs
- parsing JSON responses that may be arrays rather than dicts

Commit standalone.

### Deliverable 3: Thin Dataset-Specific Wrapper Operations

Create the dataset-specific wrapper layer on top of the generic adapter.

Create:

- `app/contracts/fmcsa_socrata.py`
- `app/services/fmcsa_socrata_operations.py`

Update:

- `app/routers/execute_v1.py`
- any existing contract or service imports needed for router wiring

Wrapper requirements:

- build wrappers for:
  - `Company Census File`
  - `Carrier - All With History`
  - `Revocation - All With History`
  - `Insur - All With History`
  - `AuthHist - All With History` only if verified
- each wrapper should map an input `dot_number` or `mc_number` to the correct dataset-specific filter columns
- DOT lookup should be the primary happy path where a dataset clearly exposes a DOT-number field
- MC lookup should be supported where the dataset clearly exposes a docket/MC-equivalent field mapping; if a dataset’s MC logic is ambiguous, document that and do not invent behavior
- each wrapper should return a structured operation result with:
  - `run_id`
  - `operation_id`
  - `status`
  - `output`
  - `provider_attempts`

Contract requirements:

- do not create five different deeply typed row contracts for this first slice
- use one shared output contract for dataset-query results, with fields like:
  - dataset name
  - dataset ID
  - identifier type used (`dot_number` or `mc_number`)
  - identifier value used
  - result count
  - matched rows
  - source provider
- the matched rows may remain dataset-native JSON objects for this first slice
- thin wrappers are for dataset selection and filter construction, not for fully canonicalizing all 19 datasets up front

Router-wiring requirements:

- add the new operation IDs to `SUPPORTED_OPERATION_IDS`
- wire the dispatch branches in `app/routers/execute_v1.py`
- persist operation history the same way other FastAPI operations do

Auth/config requirements:

- add settings for `SOCRATA_API_KEY_ID` and `SOCRATA_API_KEY_SECRET`
- do not invent new secret names
- do not introduce app-token requirements unless the implementation proves they are necessary for these authenticated queries; if you discover that they are required, stop and report rather than guessing new env names

Commit standalone.

### Deliverable 4: Tests

Add `tests/test_socrata_fmcsa.py`.

At minimum, cover:

- generic adapter sends `POST` to the correct Socrata endpoint shape
- generic adapter uses HTTP Basic auth with the Socrata key ID and secret
- generic adapter includes the expected JSON `query` payload
- wrapper operation returns `missing_inputs` when neither DOT nor MC input is usable
- wrapper operation maps DOT lookup to the correct dataset field for each implemented dataset
- wrapper operation maps MC lookup correctly where supported
- router wiring for the new operation IDs
- contract validation for the shared output model
- error handling for at least one Socrata `400`/`404`-class response and one `429` or `500`-class response
- `AuthHist - All With History` behavior:
  - if implemented, verify the wrapper path
  - if not implemented because API availability could not be verified, add an explicit test or report note covering that decision path

Mock all HTTP calls. Do not hit live Socrata endpoints in tests.

Commit standalone.

---

**What is NOT in scope:** No bulk FMCSA feed ingestion changes. No direct Postgres write work. No Trigger.dev task changes. No browser automation. No generic public execute operation for arbitrary SoQL or arbitrary dataset IDs. No implementation of all 19 wrappers in this directive. No deployment. No push.

**Commit convention:** Each deliverable is one commit. Do not push.

**When done:** Report back with: (a) the path to `docs/FMCSA_SOCRATA_PER_CARRIER_QUERY_MAPPINGS.md`, (b) the exact dataset-field mapping chosen for each implemented wrapper, (c) whether `AuthHist - All With History` API availability was verified and what dataset ID was used or why it was skipped, (d) every file changed, (e) the new operation IDs added, (f) the shared output contract shape, (g) the tests added and what they cover, and (h) anything to flag — especially any dataset where MC lookup logic was too ambiguous to implement safely in this slice.
