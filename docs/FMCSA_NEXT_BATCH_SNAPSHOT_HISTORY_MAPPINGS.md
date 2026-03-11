# FMCSA Next Batch Snapshot + History Mappings

This document locks the ingestion contract for the next FMCSA batch in scope:

- `Carrier`
- `Rejected`
- `BOC3`
- `InsHist - All With History`
- `BOC3 - All With History`
- `ActPendInsur - All With History`
- `Rejected - All With History`
- `AuthHist - All With History`

## Shared Ingestion Rules

- All feeds are ingested as direct-download `text/plain` files whose contents are quoted comma-delimited rows with no header row.
- All feeds are parsed with a real CSV parser.
- All rows are stored exactly as observed for a given `feed_date`.
- Daily feeds are treated as source snapshots for the observed day, not as business diffs.
- All With History feeds are also treated as source snapshots for the observed day, not as deduped entity histories.
- No business-level deduplication happens at ingestion time.
- Same-`feed_date` reruns are idempotent by source-row identity.
- Different `feed_date` values always produce distinct stored observations, even when the business row looks identical.

## Shared Metadata / Idempotency Contract

Every canonical table in this batch must include:

- `feed_date DATE NOT NULL`
- `row_position INTEGER NOT NULL`
- `source_provider TEXT NOT NULL` with value `fmcsa_open_data`
- `source_feed_name TEXT NOT NULL`
- `source_download_url TEXT NOT NULL`
- `source_file_variant TEXT NOT NULL`
- `source_observed_at TIMESTAMPTZ NOT NULL`
- `source_task_id TEXT NOT NULL`
- `source_schedule_id TEXT`
- `source_run_metadata JSONB NOT NULL`
- `raw_source_row JSONB NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL`
- `updated_at TIMESTAMPTZ NOT NULL`

Raw source preservation plan:

- `raw_source_row` stores:
  - the source row number as observed in the file
  - the ordered raw values array
  - the keyed field map built from the locked dictionary order

Row identity / rerun idempotency strategy:

- Storage key is `UNIQUE(feed_date, source_feed_name, row_position)`.
- Same-`feed_date` reruns overwrite the same source-row slot for the same source feed artifact.
- Different `feed_date` values preserve distinct observations.
- This is intentionally source-row-oriented rather than business-row-oriented.

Global scoping rule:

- All tables in this batch are global `entities` tables, not tenant-scoped.
- These are public FMCSA records, not tenant-generated enrichment outputs.

## Explicit Share/Split Decision

Question: should the All With History feeds share tables with their daily counterparts?

Answer:

- `AuthHist - All With History`: share with `operating_authority_histories`
- `ActPendInsur - All With History`: share with `insurance_policy_filings`
- `InsHist - All With History`: share with `insurance_policy_history_events`
- `Rejected - All With History`: share with `insurance_filing_rejections`
- `BOC3 - All With History`: share with `process_agent_filings`

Why shared-table storage is safe for those feeds:

- The daily and all-history dictionaries are materially identical for each pair.
- The row concepts are the same within each pair.
- `source_file_variant` plus `feed_date` keeps downstream interpretation unambiguous.
- We are storing source observations, not trying to flatten the data into one current-state row per business concept.

When table splitting was still required in this batch:

- `Carrier` needs its own table because batch one never created a carrier-registration concept table.
- `BOC3` and `Rejected` also need new tables because batch one never created canonical tables for those concepts.
- `Carrier` is not merged into any existing authority/insurance/history table because that would collapse unlike concepts and create ambiguous downstream semantics.

## Feed: Carrier

- Source feed name: `Carrier`
- Source variant: `daily`
- Direct download URL: `https://data.transportation.gov/download/6qg9-x4f8/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `MX Type`
  4. `RFC Number`
  5. `Common Authority`
  6. `Contract Authority`
  7. `Broker Authority`
  8. `Pending Common Authority`
  9. `Pending Contract Authority`
  10. `Pending Broker Authority`
  11. `Common Authority Revocation`
  12. `Contract Authority Revocation`
  13. `Broker Authority Revocation`
  14. `Property`
  15. `Passenger`
  16. `Household Goods`
  17. `Private Check`
  18. `Enterprise Check`
  19. `BIPD Required`
  20. `Cargo Required`
  21. `Bond/Surety Required`
  22. `BIPD on File`
  23. `Cargo on File`
  24. `Bond/Surety on File`
  25. `Address Status`
  26. `DBA Name`
  27. `Legal Name`
  28. `Business Address - PO Box/Street`
  29. `Business Address - Colonia`
  30. `Business Address - City`
  31. `Business Address - State Code`
  32. `Business Address - Country Code`
  33. `Business Address - Zip Code`
  34. `Business Address - Telephone Number`
  35. `Business Address - Fax Number`
  36. `Mailing Address - PO Box/Street`
  37. `Mailing Address - Colonia`
  38. `Mailing Address - City`
  39. `Mailing Address - State Code`
  40. `Mailing Address - Country Code`
  41. `Mailing Address - Zip Code`
  42. `Mailing Address - Telephone Number`
  43. `Mailing Address - Fax Number`
- Row width expected in raw file: `43`
- Canonical business concept represented: carrier registration / census / authority snapshot row
- Chosen canonical table name: `carrier_registrations`
- Existing first-batch table or new table: new table
- Why new table:
  - No existing first-batch table models carrier registration rows.
  - `Carrier` is a broad registration snapshot concept, not authority history, revocation history, or insurance-policy history.
  - Merging it into any existing batch-one table would mix unlike concepts and make downstream interpretation unsafe.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `mx_type`
  - `rfc_number`
  - `common_authority_status`
  - `contract_authority_status`
  - `broker_authority_status`
  - `pending_common_authority`
  - `pending_contract_authority`
  - `pending_broker_authority`
  - `common_authority_revocation`
  - `contract_authority_revocation`
  - `broker_authority_revocation`
  - `property_authority`
  - `passenger_authority`
  - `household_goods_authority`
  - `private_check`
  - `enterprise_check`
  - `bipd_required_thousands_usd`
  - `cargo_required`
  - `bond_surety_required`
  - `bipd_on_file_thousands_usd`
  - `cargo_on_file`
  - `bond_surety_on_file`
  - `address_status`
  - `dba_name`
  - `legal_name`
  - `business_address_street`
  - `business_address_colonia`
  - `business_address_city`
  - `business_address_state_code`
  - `business_address_country_code`
  - `business_address_zip_code`
  - `business_address_telephone_number`
  - `business_address_fax_number`
  - `mailing_address_street`
  - `mailing_address_colonia`
  - `mailing_address_city`
  - `mailing_address_state_code`
  - `mailing_address_country_code`
  - `mailing_address_zip_code`
  - `mailing_address_telephone_number`
  - `mailing_address_fax_number`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Even though FMCSA labels this a daily difference feed, ingestion must treat it as a snapshot file observed for that `feed_date`.
  - Do not collapse rows into a one-row-per-carrier current-state model at ingestion time.
  - This feed is the broad master registration snapshot and must remain separate from more specific authority/insurance history tables.

## Feed: Rejected

- Source feed name: `Rejected`
- Source variant: `daily`
- Direct download URL: `https://data.transportation.gov/download/t3zq-c6n3/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/06-rejected-daily-diff/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/06-rejected-daily-diff/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `Form Code (Insurance or Cancel)`
  4. `Insurance Type Description`
  5. `Policy Number`
  6. `Received Date`
  7. `Insurance Class Code`
  8. `Insurance Type Code`
  9. `Underlying Limit Amount`
  10. `Maximum Coverage Amount`
  11. `Rejected Date`
  12. `Insurance Branch`
  13. `Company Name`
  14. `Rejected Reason`
  15. `Minimum Coverage Amount`
- Row width expected in raw file: `15`
- Canonical business concept represented: rejected insurance filing / rejected insurance form row
- Chosen canonical table name: `insurance_filing_rejections`
- Existing first-batch table or new table: new table
- Why new table:
  - Batch one has no canonical table for rejected insurance filing rows.
  - This is not the same concept as active insurance inventory, active/pending filing timing, or outgoing policy history.
  - Rejections are their own enforcement/compliance concept and deserve separate storage.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `form_code`
  - `insurance_type_description`
  - `policy_number`
  - `received_date`
  - `insurance_class_code`
  - `insurance_type_code`
  - `underlying_limit_amount_thousands_usd`
  - `maximum_coverage_amount_thousands_usd`
  - `rejected_date`
  - `insurance_branch`
  - `insurance_company_name`
  - `rejected_reason`
  - `minimum_coverage_amount_thousands_usd`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Do not dedupe by docket/policy/reason during ingestion.
  - Rejection reason text is a first-class typed field because downstream consumers will likely filter/group on it.
  - Daily rows are stored as observed snapshots, not merged into a single long-lived rejection record.

## Feed: BOC3

- Source feed name: `BOC3`
- Source variant: `daily`
- Direct download URL: `https://data.transportation.gov/download/fb8g-ngam/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/09-boc3-daily-diff/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/09-boc3-daily-diff/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `Company Name`
  4. `Attention to or Title`
  5. `Street or PO Box`
  6. `City`
  7. `State`
  8. `Country`
  9. `Zip Code`
- Row width expected in raw file: `9`
- Canonical business concept represented: process-agent filing row for a regulated carrier/broker/freight forwarder
- Chosen canonical table name: `process_agent_filings`
- Existing first-batch table or new table: new table
- Why new table:
  - Batch one has no canonical table for BOC3 process-agent rows.
  - This is a legal-representation / filing concept, not a carrier master row and not an authority/insurance history row.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `process_agent_company_name`
  - `attention_to_or_title`
  - `street_or_po_box`
  - `city`
  - `state`
  - `country`
  - `zip_code`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - The source dictionary skips field number `3`, but the actual raw row contract is `9` fields.
  - Do not invent a placeholder column for the skipped numbering.
  - BOC3 daily is treated as a snapshot file observed for the day, not as a semantic diff stream.

## Feed: InsHist - All With History

- Source feed name: `InsHist - All With History`
- Source variant: `all_with_history`
- Direct download URL: `https://data.transportation.gov/download/nzpz-e5xn/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/12-inshist-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/12-inshist-all-with-history/overview-data-dictionary.md`
- Exact ordered source fields:
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
  16. `Insurance Company Branch`
  17. `Insurance Company Name`
- Row width expected in raw file: `17`
- Canonical business concept represented: outgoing insurance-policy history event row
- Chosen canonical table name: `insurance_policy_history_events`
- Existing first-batch table or new table: existing first-batch table
- Why compatible with existing table:
  - The daily and all-history dictionaries are materially identical.
  - The row concept is identical: outgoing policy history, not the replacement/current policy.
  - `source_file_variant` cleanly distinguishes daily snapshot observations from all-history snapshot observations without making downstream interpretation ambiguous.
- Typed columns:
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
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Keep this separate from active/pending policy tables.
  - The all-history variant is not a reason to build a deduped one-row-per-policy history abstraction at ingestion time.

## Feed: BOC3 - All With History

- Source feed name: `BOC3 - All With History`
- Source variant: `all_with_history`
- Direct download URL: `https://data.transportation.gov/download/gmxu-awv7/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/13-boc3-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/13-boc3-all-with-history/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `Company Name`
  4. `Attention to or Title`
  5. `Street or PO Box`
  6. `City`
  7. `State`
  8. `Country`
  9. `Zip Code`
- Row width expected in raw file: `9`
- Canonical business concept represented: process-agent filing row
- Chosen canonical table name: `process_agent_filings`
- Existing first-batch table or new table: new table shared with `BOC3` daily
- Why shared-table storage is compatible:
  - The daily and all-history dictionaries are materially identical.
  - The row meaning is the same: a BOC3 process-agent filing row.
  - `source_file_variant` keeps daily vs all-history provenance explicit.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `process_agent_company_name`
  - `attention_to_or_title`
  - `street_or_po_box`
  - `city`
  - `state`
  - `country`
  - `zip_code`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - The source numbering skip remains a documentation quirk, not a raw-file placeholder column.
  - Shared-table storage is safe because there is no structural or semantic mismatch between the pair.

## Feed: ActPendInsur - All With History

- Source feed name: `ActPendInsur - All With History`
- Source variant: `all_with_history`
- Direct download URL: `https://data.transportation.gov/download/y77m-3nfx/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/14-actpendinsur-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/14-actpendinsur-all-with-history/overview-data-dictionary.md`
- Exact ordered source fields:
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
- Row width expected in raw file: `11`
- Canonical business concept represented: active/pending insurance filing timing/status row
- Chosen canonical table name: `insurance_policy_filings`
- Existing first-batch table or new table: existing first-batch table
- Why compatible with existing table:
  - The daily and all-history dictionaries are materially identical.
  - The row meaning is identical: active/pending filing timing state for a policy.
  - `source_file_variant` prevents ambiguity while allowing one canonical concept table.
- Typed columns:
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
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Keep this distinct from both current-policy inventory and outgoing-policy history.
  - Do not interpret all-history rows as a deduped entity lifecycle model at ingestion time.

## Feed: Rejected - All With History

- Source feed name: `Rejected - All With History`
- Source variant: `all_with_history`
- Direct download URL: `https://data.transportation.gov/download/9m5y-imtw/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/15-rejected-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/15-rejected-all-with-history/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `Form Code (Insurance or Cancel)`
  4. `Insurance Type Description`
  5. `Policy Number`
  6. `Received Date`
  7. `Insurance Class Code`
  8. `Insurance Type Code`
  9. `Underlying Limit Amount`
  10. `Maximum Coverage Amount`
  11. `Rejected Date`
  12. `Insurance Branch`
  13. `Company Name`
  14. `Rejected Reason`
  15. `Minimum Coverage Amount`
- Row width expected in raw file: `15`
- Canonical business concept represented: rejected insurance filing / rejected insurance form row
- Chosen canonical table name: `insurance_filing_rejections`
- Existing first-batch table or new table: new table shared with `Rejected` daily
- Why shared-table storage is compatible:
  - The daily and all-history dictionaries are materially identical.
  - The row meaning is identical.
  - `source_file_variant` keeps provenance explicit while preserving one concept table.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `form_code`
  - `insurance_type_description`
  - `policy_number`
  - `received_date`
  - `insurance_class_code`
  - `insurance_type_code`
  - `underlying_limit_amount_thousands_usd`
  - `maximum_coverage_amount_thousands_usd`
  - `rejected_date`
  - `insurance_branch`
  - `insurance_company_name`
  - `rejected_reason`
  - `minimum_coverage_amount_thousands_usd`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Shared-table storage is safe because there is no structure mismatch and no semantic ambiguity once `source_file_variant` is preserved.

## Feed: AuthHist - All With History

- Source feed name: `AuthHist - All With History`
- Source variant: `all_with_history`
- Direct download URL: `https://data.transportation.gov/download/wahn-z3rq/text%2Fplain`
- Source docs used:
  - `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/16-authhist-all-with-history/overview-data-dictionary.md`
- Exact ordered source fields:
  1. `Docket Number`
  2. `USDOT Number`
  3. `Sub Number`
  4. `Operating Authority Type`
  5. `Original Authority Action Description`
  6. `Original Authority Action Served Date`
  7. `Final Authority Action Description`
  8. `Final Authority Decision Date`
  9. `Final Authority Served Date`
- Row width expected in raw file: `9`
- Canonical business concept represented: authority lifecycle history row
- Chosen canonical table name: `operating_authority_histories`
- Existing first-batch table or new table: existing first-batch table
- Why compatible with existing table:
  - The daily and all-history dictionaries are materially identical.
  - The row meaning is identical: authority lifecycle history, not current authority state.
  - `source_file_variant` preserves provenance without requiring duplicate structure.
- Typed columns:
  - `docket_number`
  - `usdot_number`
  - `sub_number`
  - `operating_authority_type`
  - `original_authority_action_description`
  - `original_authority_action_served_date`
  - `final_authority_action_description`
  - `final_authority_decision_date`
  - `final_authority_served_date`
- Raw source row preservation plan: shared contract above
- Required source metadata columns: shared contract above, including `feed_date`
- Row identity / rerun idempotency strategy: shared contract above
- Source-specific semantic caveats:
  - Shared-table storage is safe because the row contract and concept match the daily feed exactly.
  - Do not flatten the combined data into a current authority status model.

## Dictionary / Semantics Flags

- `Carrier` is the broad carrier registration / authority / insurance-summary snapshot. It is not interchangeable with any batch-one concept table.
- `BOC3` dictionaries skip field number `3`, but the actual contract is still `9` ordered fields.
- `Rejected` dictionaries skip field number `12`, but the actual contract is still `15` ordered fields.
- `InsHist` dictionaries skip field number `16`, but the actual contract is still `17` ordered fields.
- For the five daily/all-history pairs represented by `AuthHist`, `ActPendInsur`, `InsHist`, `BOC3`, and `Rejected`, the dictionaries are materially identical between variants, so shared-table storage is safe.
