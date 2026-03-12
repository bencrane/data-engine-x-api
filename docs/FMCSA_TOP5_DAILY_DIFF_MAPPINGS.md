# FMCSA Top 5 Daily Diff Mappings

This document is the contract lock for the five FMCSA daily diff feeds in scope:

- `AuthHist`
- `Revocation`
- `Insurance`
- `ActPendInsur`
- `InsHist`

## Shared Contract Decisions

- All five canonical tables live in the `entities` schema.
- All five tables are global, not tenant-scoped.
- None of these tables should carry `org_id` or `company_id`.
- None of these tables should block ingestion on linkage to `company_entities`.
- Each table keeps typed business columns plus shared ingestion/lineage columns:
  - `feed_date DATE NOT NULL`
  - `row_position INTEGER NOT NULL`
  - `source_provider TEXT NOT NULL` with value `fmcsa_open_data`
  - `source_feed_name TEXT NOT NULL`
  - `source_download_url TEXT NOT NULL`
  - `source_file_variant TEXT NOT NULL` with value `daily diff`
  - `source_observed_at TIMESTAMPTZ NOT NULL`
  - `source_task_id TEXT`
  - `source_schedule_id TEXT`
  - `source_run_metadata JSONB NOT NULL`
  - `raw_source_row JSONB NOT NULL`
  - `created_at TIMESTAMPTZ NOT NULL`
  - `updated_at TIMESTAMPTZ NOT NULL`
- Each table enforces `UNIQUE(feed_date, row_position)` to prevent double-ingesting the same day's file while still storing the same business row again on later feed dates.
- `raw_source_row` preserves both the ordered raw values and the keyed source-field mapping for the row, along with the source row number.
- Ingestion stores exactly what the worker saw in that day's file. Change detection happens downstream by comparing rows across `feed_date` values.
- Nullable linkage to existing `company_entities` is explicitly deferred. The current `company_entities` model is not a global FMCSA carrier master, so adding nullable tenant-shaped foreign keys now would create misleading semantics.

## Feed 1: AuthHist

- Feed name: `AuthHist`
- Download URL: `https://data.transportation.gov/download/sn3k-dnx7/text%2Fplain`
- Data dictionary: `docs/api-reference-docs/fmcsa-open-data/08-authhist-daily-difference-daily-diff/data-dictionary.json`
- Overview: `docs/api-reference-docs/fmcsa-open-data/08-authhist-daily-difference-daily-diff/overview-data-dictionary.md`
- Row width expected: `9`
- Canonical table: `entities.operating_authority_histories`
- Business concept: authority lifecycle history rows for a docket/authority combination, not current authority state

Exact ordered source fields:

1. `Docket Number`
2. `USDOT Number`
3. `Sub Number`
4. `Operating Authority Type`
5. `Original Authority Action Description`
6. `Original Authority Action Served Date`
7. `Final Authority Action Description`
8. `Final Authority Decision Date`
9. `Final Authority Served Date`

Chosen typed columns:

- `docket_number`
- `usdot_number`
- `sub_number`
- `operating_authority_type`
- `original_authority_action_description`
- `original_authority_action_served_date`
- `final_authority_action_description`
- `final_authority_decision_date`
- `final_authority_served_date`

Raw payload and source metadata preservation:

- Use the shared lineage columns above.
- `raw_source_row` stores the original 9 values plus the keyed field map.

Dedup/idempotency behavior:

- No business-row deduplication at ingestion time.
- The same authority-history row can appear on multiple `feed_date` values and will be stored once per day.
- Same-day reruns upsert on `(feed_date, row_position)`.

Dataset scope:

- Global.
- Justification: these are public FMCSA authority-history records that exist independently of any tenant request.

Nullable linkage decision:

- Deferred explicitly.
- Matching to tenant-shaped `company_entities` is useful follow-on work but should not shape ingestion.

Special handling:

- Multiple rows per docket are expected.
- Empty "final" fields remain meaningful and must not be coerced into synthetic current-state flags.

## Feed 2: Revocation

- Feed name: `Revocation`
- Download URL: `https://data.transportation.gov/download/pivg-szje/text%2Fplain`
- Data dictionary: `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/data-dictionary.json`
- Overview: `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/overview-data-dictionary.md`
- Row width expected: `6`
- Canonical table: `entities.operating_authority_revocations`
- Business concept: operating-authority revocation event/history rows, not carrier snapshot state

Exact ordered source fields:

1. `Docket Number`
2. `USDOT Number`
3. `Operating Authority Registration Type`
4. `Serve Date`
5. `Revocation Type`
6. `Effective Date`

Chosen typed columns:

- `docket_number`
- `usdot_number`
- `operating_authority_registration_type`
- `serve_date`
- `revocation_type`
- `effective_date`

Raw payload and source metadata preservation:

- Use the shared lineage columns above.
- `raw_source_row` stores the original 6 values plus the keyed field map.

Dedup/idempotency behavior:

- No business-row deduplication at ingestion time.
- The same revocation row can exist on Monday and Tuesday as two rows with different `feed_date` values.
- Same-day reruns upsert on `(feed_date, row_position)`.

Dataset scope:

- Global.
- Justification: revocation records are public enforcement signals, not tenant-owned research output.

Nullable linkage decision:

- Deferred explicitly.

Special handling:

- A single entity can have multiple revocation rows for different authority types or different revocation events.
- This table must remain an event/history table rather than being flattened into current revocation flags.

## Feed 3: Insurance

- Feed name: `Insurance`
- Download URL: `https://data.transportation.gov/download/mzmm-6xep/text%2Fplain`
- Data dictionary: `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/data-dictionary.json`
- Overview: `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/overview-data-dictionary.md`
- Row width expected: `9`
- Canonical table: `entities.insurance_policies`
- Business concept: active/pending individual insurance policy records, with daily-diff removal rows preserved as removal signals

Exact ordered source fields:

1. `Docket Number`
2. `Insurance Type`
3. `BI&PD Class`
4. `BI&PD Maximum Dollar Limit`
5. `BI&PD Underlying Dollar Limit`
6. `Policy Number`
7. `Effective Date`
8. `Form Code`
9. `Insurance Company Name`

Chosen typed columns:

- `docket_number`
- `insurance_type_code`
- `insurance_type_description`
- `bipd_class_code`
- `bipd_maximum_dollar_limit_thousands_usd`
- `bipd_underlying_dollar_limit_thousands_usd`
- `policy_number`
- `effective_date`
- `form_code`
- `insurance_company_name`
- `is_removal_signal`
- `removal_signal_reason`

Raw payload and source metadata preservation:

- Use the shared lineage columns above.
- `raw_source_row` stores the original 9 values plus the keyed field map.

Dedup/idempotency behavior:

- No business-row deduplication at ingestion time.
- Repeated appearances of the same policy row across feed dates are stored once per day.
- Same-day reruns upsert on `(feed_date, row_position)`.

Dataset scope:

- Global.
- Justification: these are public FMCSA insurance-on-file records.

Nullable linkage decision:

- Deferred explicitly.

Special handling:

- Blank or zeroed daily-diff rows are not malformed noise.
- If every field except `Docket Number` is blank/zeroed, persist the row as `is_removal_signal = true`.
- Removal-signal rows keep non-docket typed business columns null unless the literal source value itself is semantically meaningful.
- Do not invent a linkage from the removal signal to a prior policy row; FMCSA does not identify the removed policy in this feed.
- Multiple policy rows per docket are expected.

## Feed 4: ActPendInsur

- Feed name: `ActPendInsur`
- Download URL: `https://data.transportation.gov/download/chgs-tx6x/text%2Fplain`
- Data dictionary: `docs/api-reference-docs/fmcsa-open-data/07-actpendinsur-daily-difference-daily-diff/data-dictionary.json`
- Overview: `docs/api-reference-docs/fmcsa-open-data/07-actpendinsur-daily-difference-daily-diff/overview-data-dictionary.md`
- Row width expected: `11`
- Canonical table: `entities.insurance_policy_filings`
- Business concept: active/pending insurance filing timing/status rows, distinct from the simpler current-policy inventory in `insurance_policies`

Exact ordered source fields:

1. `Docket Number`
2. `USDOT Number`
3. `Form Code`
4. `Insurance Type Description`
5. `Insurance Company Name`
6. `Policy Number`
7. `Posted Date`
8. `BI&PD Underlying Limit`
9. `BI&PD Maximum Limit`
10. `Effective Date`
11. `Cancel Effective Date`

Chosen typed columns:

- `docket_number`
- `usdot_number`
- `form_code`
- `insurance_type_description`
- `insurance_company_name`
- `policy_number`
- `posted_date`
- `bipd_underlying_limit_thousands_usd`
- `bipd_maximum_limit_thousands_usd`
- `effective_date`
- `cancel_effective_date`

Raw payload and source metadata preservation:

- Use the shared lineage columns above.
- `raw_source_row` stores the original 11 values plus the keyed field map.

Dedup/idempotency behavior:

- No business-row deduplication at ingestion time.
- The same filing row can appear on multiple `feed_date` values and is stored once per day.
- Same-day reruns upsert on `(feed_date, row_position)`.

Dataset scope:

- Global.
- Justification: this is public FMCSA filing-state data, not tenant-owned enrichment output.

Nullable linkage decision:

- Deferred explicitly.

Special handling:

- This table must remain distinct from `insurance_policies`.
- The timing fields are the point of the dataset; do not collapse this into a generic current-policy table.
- Multiple rows per docket and policy are expected across lifecycle changes.

## Feed 5: InsHist

- Feed name: `InsHist`
- Download URL: `https://data.transportation.gov/download/xkmg-ff2t/text%2Fplain`
- Data dictionary: `docs/api-reference-docs/fmcsa-open-data/10-inshist-daily-diff/data-dictionary.json`
- Overview: `docs/api-reference-docs/fmcsa-open-data/10-inshist-daily-diff/overview-data-dictionary.md`
- Row width expected: `17`
- Canonical table: `entities.insurance_policy_history_events`
- Business concept: outgoing insurance-policy history rows for cancellations, replacements, name changes, and transfers

Exact ordered source fields:

1. `Docket Number`
2. `USDOT Number`
3. `Form Code`
4. `Cancellation Method`
5. `Cancel/Replace/Name Change/Transfer Form`
6. `Insurance Type Indicator`
7. `Insurance Type Description`
8. `Policy Number`
9. `Minimum Coverage Amount`
10. `Insurance Class Code`
11. `Effective Date`
12. `BI&PD Underlying Limit Amount`
13. `BI&PD Max Coverage Amount`
14. `Cancel Effective Date`
15. `Specific Cancellation Method`
17. `Insurance Company Branch`
18. `Insurance Company Name`

Chosen typed columns:

- `docket_number`
- `usdot_number`
- `form_code`
- `cancellation_method`
- `cancellation_form_code`
- `insurance_type_indicator`
- `insurance_type_description`
- `policy_number`
- `minimum_coverage_amount_thousands_usd`
- `insurance_class_code`
- `effective_date`
- `bipd_underlying_limit_amount_thousands_usd`
- `bipd_max_coverage_amount_thousands_usd`
- `cancel_effective_date`
- `specific_cancellation_method`
- `insurance_company_branch`
- `insurance_company_name`

Raw payload and source metadata preservation:

- Use the shared lineage columns above.
- `raw_source_row` stores the original 17 values plus the keyed field map.

Dedup/idempotency behavior:

- No business-row deduplication at ingestion time.
- The same historical policy row can appear on multiple `feed_date` values and is stored once per day.
- Same-day reruns upsert on `(feed_date, row_position)`.

Dataset scope:

- Global.
- Justification: this is public FMCSA historical insurance-state data.

Nullable linkage decision:

- Deferred explicitly.

Special handling:

- Do not merge this table with `insurance_policies` or `insurance_policy_filings`.
- This table refers to the outgoing policy, not the replacement/current policy.
- Multiple rows per docket and policy are expected.

## Contract Notes To Preserve In Code

- `AuthHist` is authority lifecycle history, not current authority state.
- `Revocation` is revocation-event/history data, not a carrier snapshot.
- `Insurance` blank/zeroed daily-diff rows must be preserved as removal signals.
- `ActPendInsur` captures active/pending filing timing state, not generic current insurance inventory.
- `InsHist` captures outgoing historical policy state, not the replacement/current policy.

## Explicit Ambiguity Flag

- `InsHist` overview text says "Total fields: 18" while the dictionary enumerates 17 actual fields with skipped position `16`.
- The contract for implementation locks to the dictionary and to a live sample row width of `17`.
- Treat the overview count as a documentation bug, not as an 18-column parser contract.
