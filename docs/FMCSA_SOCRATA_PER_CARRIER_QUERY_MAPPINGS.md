# FMCSA Socrata Per-Carrier Query Mappings

This document locks the dataset-specific Socrata mapping for targeted per-carrier lookups against `data.transportation.gov`.

Scope:

- one internal Socrata query adapter
- thin FastAPI wrapper operations only
- no arbitrary dataset-ID or raw-SoQL public execution surface

Source evidence used:

- `docs/SOCRATA_API_REFERENCE_SUMMARY.md`
- `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/data-dictionary.json`
- `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/data-dictionary.json`
- `trigger/src/workflows/fmcsa-daily-diff.ts`
- `docs/FMCSA_REMAINING_CSV_EXPORT_FEEDS_PREFLIGHT_AND_MAPPINGS.md`
- public metadata checks against `data.transportation.gov/api/views/*`

## Dataset: Company Census File

- Dataset ID: `az4n-8mr2`
- API availability verified: yes
- DOT filter field: `DOT_NUMBER`
- MC/docket filter fields:
  - `DOCKET1PREFIX` + `DOCKET1`
  - `DOCKET2PREFIX` + `DOCKET2`
  - `DOCKET3PREFIX` + `DOCKET3`
- Legal/carrier name fields:
  - `LEGAL_NAME`
  - `DBA_NAME`
- DOT lookup supported: yes
- MC lookup supported: yes
- MC lookup rule:
  - treat `mc_number` as digits only
  - query rows where any docket slot matches `MC`
  - exact SoQL shape:
    - ``(`DOCKET1PREFIX` = 'MC' AND `DOCKET1` = <mc_digits_as_integer>) OR (`DOCKET2PREFIX` = 'MC' AND `DOCKET2` = <mc_digits_as_integer>) OR (`DOCKET3PREFIX` = 'MC' AND `DOCKET3` = <mc_digits_as_integer>)``
- Proposed operation ID: `company.enrich.fmcsa.company_census`
- Expected wrapper input requirements:
  - accepts `dot_number` or `mc_number`
  - `dot_number` is the preferred path
- Expected output summary shape:
  - dataset name
  - dataset ID
  - identifier type used
  - identifier value used
  - result count
  - matched rows
  - source provider
- Dataset-specific caveats:
  - the MC path is not a single field lookup; it requires three parallel docket-slot checks
  - this wrapper is limited to `MC` prefixes and does not infer `MX` or `FF`

## Dataset: Carrier - All With History

- Dataset ID: `6eyk-hxee`
- API availability verified: yes
- DOT filter field: `DOT_NUMBER`
- MC/docket filter field: `DOCKET_NUMBER`
- Legal/carrier name fields:
  - `LEGAL_NAME`
  - `DBA_NAME`
- DOT lookup supported: yes
- MC lookup supported: yes
- MC lookup rule:
  - normalize `mc_number` to `MC` plus a zero-padded 6-digit numeric suffix
  - exact SoQL shape:
    - `` `DOCKET_NUMBER` = 'MC000123' ``
- Proposed operation ID: `company.enrich.fmcsa.carrier_all_history`
- Expected wrapper input requirements:
  - accepts `dot_number` or `mc_number`
  - `dot_number` is the preferred path
- Expected output summary shape:
  - dataset name
  - dataset ID
  - identifier type used
  - identifier value used
  - result count
  - matched rows
  - source provider
- Dataset-specific caveats:
  - all-history CSV export headers are Socrata/export aliases, not the human-readable dictionary labels
  - the verified queryable lookup fields for this slice are the live/export aliases from the existing workflow contract

## Dataset: Revocation - All With History

- Dataset ID: `sa6p-acbp`
- API availability verified: yes
- DOT filter field: `DOT_NUMBER`
- MC/docket filter field: `DOCKET_NUMBER`
- Legal/carrier name fields: none verified for this slice
- DOT lookup supported: yes
- MC lookup supported: yes
- MC lookup rule:
  - normalize `mc_number` to `MC` plus a zero-padded 6-digit numeric suffix
  - exact SoQL shape:
    - `` `DOCKET_NUMBER` = 'MC000123' ``
- Proposed operation ID: `company.enrich.fmcsa.revocation_all_history`
- Expected wrapper input requirements:
  - accepts `dot_number` or `mc_number`
  - `dot_number` is the preferred path
- Expected output summary shape:
  - dataset name
  - dataset ID
  - identifier type used
  - identifier value used
  - result count
  - matched rows
  - source provider
- Dataset-specific caveats:
  - live/export headers use verified Socrata aliases:
    - `DOCKET_NUMBER`
    - `DOT_NUMBER`
    - `TYPE_LICENSE`
    - `ORDER1_SERVE_DATE`
    - `ORDER2_TYPE_DESC`
    - `order2_effective_Date`
  - no carrier-name field is required for the per-carrier identifier lookup path

## Dataset: Insur - All With History

- Dataset ID: `ypjt-5ydn`
- API availability verified: yes
- DOT filter field: none verified
- MC/docket filter field: `prefix_docket_number`
- Legal/carrier name fields: none verified for this slice
- DOT lookup supported: no
- MC lookup supported: yes
- MC lookup rule:
  - normalize `mc_number` to `MC` plus a zero-padded 6-digit numeric suffix
  - exact SoQL shape:
    - `` `prefix_docket_number` = 'MC000123' ``
- Proposed operation ID: `company.enrich.fmcsa.insur_all_history`
- Expected wrapper input requirements:
  - requires `mc_number`
  - `dot_number` alone is not sufficient because the verified all-history dataset contract does not expose a DOT field
- Expected output summary shape:
  - dataset name
  - dataset ID
  - identifier type used
  - identifier value used
  - result count
  - matched rows
  - source provider
- Dataset-specific caveats:
  - this dataset links by docket number, not DOT number
  - live/export headers use verified Socrata aliases:
    - `prefix_docket_number`
    - `ins_type_code`
    - `ins_class_code`
    - `max_cov_amount`
    - `underl_lim_amount`
    - `policy_no`
    - `effective_date`
    - `ins_form_code`
    - `name_company`

## Dataset: AuthHist - All With History

- Dataset ID status: not safely verified for implementation in this slice
- Repo evidence found:
  - `trigger/src/workflows/fmcsa-daily-diff.ts` uses download source `wahn-z3rq`
  - legacy `research.md` lists conflicting dataset ID `9mw4-x3tu`
  - `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/data-dictionary.json` confirms the business fields but not the live Socrata field aliases
- Public metadata check result:
  - `https://data.transportation.gov/api/views/wahn-z3rq.json` resolves the dataset name, but returns zero columns
  - `https://data.transportation.gov/api/views/wahn-z3rq/rows.csv?accessType=DOWNLOAD` responds with `Non-tabular datasets do not support rows requests`
- API availability verified: no for safe per-carrier wrapper implementation
- DOT filter field: unverified
- MC/docket filter field: unverified
- Legal/carrier name fields: unverified
- DOT lookup supported: not implemented
- MC lookup supported: not implemented
- Proposed operation ID: `company.enrich.fmcsa.authhist_all_history`
- Decision:
  - do not implement the wrapper in this slice
  - do not expose the operation ID in the router
- Dataset-specific caveats:
  - dataset ID evidence is internally inconsistent across repo artifacts
  - the live metadata currently does not expose a verified tabular column contract suitable for building exact SoQL filters without guessing

## Final Wrapper Set

- Implement:
  - `company.enrich.fmcsa.company_census`
  - `company.enrich.fmcsa.carrier_all_history`
  - `company.enrich.fmcsa.revocation_all_history`
  - `company.enrich.fmcsa.insur_all_history`
- Skip for now:
  - `company.enrich.fmcsa.authhist_all_history`
