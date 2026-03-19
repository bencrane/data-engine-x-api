# Materialized Views Inventory

**Last updated:** 2026-03-19
**Production state:** as of this audit date. Row counts from live production SQL run 2026-03-19.

---

## Summary

| Name | Source table(s) | Row count | Refresh | Status |
|---|---|---:|---|---|
| `mv_federal_contract_leads` | `usaspending_contracts` + `sam_gov_entities` | 1,340,862 | WEEKLY | existing |
| `mv_fmcsa_authority_grants` | `operating_authority_histories` | 9,826,096 | DAILY | existing |
| `mv_fmcsa_carrier_master` | `mv_fmcsa_latest_census` + `mv_fmcsa_latest_safety_percentiles` + `mv_fmcsa_crash_counts_12mo` | 2,583,316 | DAILY | existing |
| `mv_fmcsa_crash_counts_12mo` | `commercial_vehicle_crashes` | 40,228 | DAILY | existing |
| `mv_fmcsa_insurance_cancellations` | `insurance_policy_history_events` | 3,704,271 | DAILY | existing |
| `mv_fmcsa_latest_census` | `motor_carrier_census_records` | 2,583,316 | DAILY | existing |
| `mv_fmcsa_latest_safety_percentiles` | `carrier_safety_basic_percentiles` | 36,604 | DAILY | existing |
| `mv_usaspending_contracts_typed` | `usaspending_contracts` | 14,665,610 | WEEKLY | existing |
| `mv_usaspending_first_contracts` | `usaspending_contracts` | 133,113 | WEEKLY | existing |
| `mv_sam_gov_entities_typed` | `sam_gov_entities` | ~867,137 | WEEKLY | proposed (042) |
| `mv_sam_gov_entities_by_state` | `sam_gov_entities` | ~57 | WEEKLY | proposed (042) |
| `mv_sam_gov_entities_by_naics` | `sam_gov_entities` | ~480 | WEEKLY | proposed (042) |
| `mv_sba_loans_typed` | `sba_7a_loans` | ~356,375 | WEEKLY | proposed (042) |
| `mv_sba_loans_by_state` | `sba_7a_loans` | ~57 | WEEKLY | proposed (042) |
| `mv_sam_usaspending_bridge` | `sam_gov_entities` + `mv_usaspending_contracts_typed` | ~118,422 distinct UEIs | WEEKLY | proposed (042) |
| `mv_fmcsa_latest_insurance_policies` | `insurance_policies` | ~1,427,273 | DAILY | proposed (042) |
| `mv_fmcsa_new_carriers_90d` | `motor_carrier_census_records` | ~16,431 | DAILY | proposed (042) |

---

## Existing Materialized Views

### entities.mv_federal_contract_leads
- **Source table(s):** `entities.usaspending_contracts`, joined with `entities.sam_gov_entities` (LEFT JOIN on `recipient_uei = unique_entity_id`)
- **Row count:** 1,340,862 (verified production)
- **Pre-computes:** DISTINCT ON dedup by `contract_transaction_unique_key`, joined SAM.gov match flag (`has_sam_match`), first-time-awardee flags per agency bucket (DOD, NASA, DOE, DHS, overall), typed numeric/date casting inherited from the join query
- **Indexes:** `idx_mv_fcl_txn_key` (unique, `contract_transaction_unique_key`), `idx_mv_fcl_action_date`, `idx_mv_fcl_agency` (`awarding_agency_code`), `idx_mv_fcl_biz_size`, `idx_mv_fcl_first_time` (partial), `idx_mv_fcl_first_time_dod` (partial), `idx_mv_fcl_naics`, `idx_mv_fcl_obligation`, `idx_mv_fcl_recipient_uei`, `idx_mv_fcl_state`
- **Recommended refresh:** WEEKLY (after USASpending backfill)
- **Migration:** 033, 034

### entities.mv_fmcsa_authority_grants
- **Source table(s):** `entities.operating_authority_histories`
- **Row count:** 9,826,096 (verified production)
- **Pre-computes:** Pre-filtered subset containing only rows where `original_authority_action_description` contains "GRANT" (eliminates sequential scan with UPPER(...) LIKE on 29.7M rows)
- **Indexes:** `idx_mv_fmcsa_ag_id` (unique, `id`), `idx_mv_fmcsa_ag_served_date`, `idx_mv_fmcsa_ag_usdot`, `idx_mv_fmcsa_ag_auth_type`, `idx_mv_fmcsa_ag_date_usdot` (composite)
- **Recommended refresh:** DAILY (after FMCSA feed ingestion)
- **Migration:** 036

### entities.mv_fmcsa_carrier_master
- **Source table(s):** `mv_fmcsa_latest_census` + `mv_fmcsa_latest_safety_percentiles` (LEFT JOIN) + `mv_fmcsa_crash_counts_12mo` (LEFT JOIN)
- **Row count:** 2,583,316 (verified production)
- **Pre-computes:** Master join of census demographics + safety BASIC percentiles + 12-month crash counts per carrier; all carriers appear even without safety data or crash history (LEFT JOIN semantics for analysis, not INNER JOIN risk-scoring)
- **Indexes:** `idx_mv_fmcsa_cm_dot` (unique, `dot_number`), `idx_mv_fmcsa_cm_state`, `idx_mv_fmcsa_cm_op_code`, `idx_mv_fmcsa_cm_crash_count`, `idx_mv_fmcsa_cm_unsafe_driving`
- **Recommended refresh:** DAILY (after upstream census/safety/crashes MVs refresh)
- **Migration:** 039

### entities.mv_fmcsa_crash_counts_12mo
- **Source table(s):** `entities.commercial_vehicle_crashes`
- **Row count:** 40,228 (verified production)
- **Pre-computes:** Trailing 12-month crash aggregate per carrier (`dot_number`): total crashes, fatal crashes, latest crash date — from the latest feed_date snapshot, excluding test_feed rows
- **Indexes:** `idx_mv_fmcsa_cc12_dot` (unique, `dot_number`), `idx_mv_fmcsa_cc12_count`
- **Recommended refresh:** DAILY (after FMCSA feed ingestion)
- **Migration:** 039

### entities.mv_fmcsa_insurance_cancellations
- **Source table(s):** `entities.insurance_policy_history_events`
- **Row count:** 3,704,271 (verified production)
- **Pre-computes:** Pre-filtered subset containing only rows with a non-null `cancel_effective_date` (eliminates sequential scan on 3.7M row table when filtering for cancellations)
- **Indexes:** `idx_mv_fmcsa_ic_id` (unique, `id`), `idx_mv_fmcsa_ic_cancel_date`, `idx_mv_fmcsa_ic_usdot`, `idx_mv_fmcsa_ic_cancel_method`, `idx_mv_fmcsa_ic_date_usdot` (composite)
- **Recommended refresh:** DAILY (after FMCSA feed ingestion)
- **Migration:** 037

### entities.mv_fmcsa_latest_census
- **Source table(s):** `entities.motor_carrier_census_records`
- **Row count:** 2,583,316 (verified production)
- **Pre-computes:** Latest census snapshot per carrier using `DISTINCT ON (dot_number)` with feed_date = MAX(feed_date), excluding test_feed rows; eliminates repeated DISTINCT ON CTE on 3.2M row table
- **Indexes:** `idx_mv_fmcsa_lc_dot` (unique, `dot_number`), `idx_mv_fmcsa_lc_state`, `idx_mv_fmcsa_lc_op_code`, `idx_mv_fmcsa_lc_legal_name`, `idx_mv_fmcsa_lc_power_units`
- **Recommended refresh:** DAILY (after FMCSA feed ingestion)
- **Migration:** 039

### entities.mv_fmcsa_latest_safety_percentiles
- **Source table(s):** `entities.carrier_safety_basic_percentiles`
- **Row count:** 36,604 (verified production)
- **Pre-computes:** Latest BASIC percentile snapshot per carrier using `DISTINCT ON (dot_number)` with feed_date = MAX(feed_date); eliminates repeated dedup on 109K row SMS table
- **Indexes:** `idx_mv_fmcsa_lsp_dot` (unique, `dot_number`), `idx_mv_fmcsa_lsp_unsafe_driving`, `idx_mv_fmcsa_lsp_hos`, `idx_mv_fmcsa_lsp_vehicle_maint`, `idx_mv_fmcsa_lsp_driver_fitness`, `idx_mv_fmcsa_lsp_controlled_sub`
- **Recommended refresh:** DAILY (after FMCSA feed ingestion; note SMS data currently lags 4 days behind other feeds)
- **Migration:** 039

### entities.mv_usaspending_contracts_typed
- **Source table(s):** `entities.usaspending_contracts`
- **Row count:** 14,665,610 (verified production)
- **Pre-computes:** Typed base view — all TEXT columns for dollar amounts cast to NUMERIC, date columns cast to DATE; DISTINCT ON dedup by `contract_transaction_unique_key` with latest `extract_date` wins; 28 curated columns selected from the raw source
- **Indexes:** `idx_mv_usa_typed_txn_key` (unique, `contract_transaction_unique_key`), `idx_mv_usa_typed_recipient_uei`, `idx_mv_usa_typed_action_date`, `idx_mv_usa_typed_agency`, `idx_mv_usa_typed_naics`, `idx_mv_usa_typed_state`, `idx_mv_usa_typed_obligation`
- **Recommended refresh:** WEEKLY (or after USASpending backfill ingestion)
- **Migration:** 038

### entities.mv_usaspending_first_contracts
- **Source table(s):** `entities.usaspending_contracts`
- **Row count:** 133,113 (verified production)
- **Pre-computes:** First contract per `recipient_uei` — `MIN(action_date)` cast, agency/NAICS/award key at first contract, total distinct award count; enables first-time awardee targeting without per-query aggregation over 14.6M rows
- **Indexes:** `idx_mv_usa_first_uei` (unique, `recipient_uei`), `idx_mv_usa_first_date`, `idx_mv_usa_first_total_awards`
- **Recommended refresh:** WEEKLY (or after USASpending backfill ingestion)
- **Migration:** 038

---

## Proposed Materialized Views

### entities.mv_sam_gov_entities_typed
- **Source table(s):** `entities.sam_gov_entities`
- **Estimated row count:** ~867,137 (one row per entity — SAM.gov has a single `extract_date` of 2026-03-01, no multi-date snapshot pattern to dedup)
- **Pre-computes:** Curated-column subset with date columns cast from TEXT to DATE (`initial_registration_date`, `registration_expiration_date`, `last_update_date`, `activation_date`, `entity_start_date`, `fiscal_year_end_close_date` — all stored as TEXT in format `YYYYMMDD` or `MM/DD/YYYY`), `sam_extract_code` renamed to a clear status label, NAICS prefix columns extracted (`LEFT(primary_naics, 2)` and `LEFT(primary_naics, 3)`) for geographic and vertical targeting without per-query string slicing. Modeled after `mv_usaspending_contracts_typed`.
- **Proposed indexes:**
  - `idx_mv_sam_typed_uei` (unique, `unique_entity_id`) — enables CONCURRENTLY refresh and is the join key for cross-vertical bridge
  - `idx_mv_sam_typed_state` (`physical_address_province_or_state`) — geographic targeting
  - `idx_mv_sam_typed_naics` (`primary_naics`) — vertical targeting
  - `idx_mv_sam_typed_naics2` (`naics_2digit`) — 2-digit prefix filtering
  - `idx_mv_sam_typed_expiration` (`registration_expiration_date_cast`) — expiring registration outbound targeting
- **Recommended refresh:** WEEKLY (SAM.gov feed updates irregularly; single extract_date currently)
- **Rationale:** All date columns in sam_gov_entities are TEXT — every analytical query must cast them. Pre-casting eliminates per-query overhead on 867K rows and enables range queries on expiration dates. 867K rows is well within practical MV size.
- **Migration:** 042

### entities.mv_sam_gov_entities_by_state
- **Source table(s):** `entities.sam_gov_entities`
- **Estimated row count:** ~57 (one row per distinct state value; 25 states seen in top-25 sample, plus foreign addresses and blank)
- **Pre-computes:** Aggregate per `physical_address_province_or_state`: total entity count, count of active entities (`sam_extract_code = 'A'`), count of expired/inactive entities (`sam_extract_code = 'E'`)
- **Proposed indexes:**
  - `idx_mv_sam_state_agg_state` (unique, `physical_address_province_or_state`) — enables CONCURRENTLY refresh
- **Recommended refresh:** WEEKLY
- **Rationale:** Geographic targeting for outbound campaigns; avoids full 867K row scan for state-level dashboards. The distribution shows CA (79K), TX (59K), FL (51K) as top states — confirms meaningful cardinality for this aggregate.
- **Migration:** 042

### entities.mv_sam_gov_entities_by_naics
- **Source table(s):** `entities.sam_gov_entities`
- **Estimated row count:** ~480 (unique 6-digit NAICS codes; ~20 2-digit buckets observed in audit sample)
- **Pre-computes:** Aggregate per `primary_naics` (6-digit): entity count, count of active entities. Includes `LEFT(primary_naics, 2)` as `naics_sector` for easy rollup to sector level.
- **Proposed indexes:**
  - `idx_mv_sam_naics_agg_naics` (unique, `primary_naics`) — enables CONCURRENTLY refresh
  - `idx_mv_sam_naics_agg_sector` (`naics_sector`) — sector rollup
- **Recommended refresh:** WEEKLY
- **Rationale:** Vertical targeting for outbound — the top NAICS sectors (54 Professional Services 139K, 23 Construction 72K, 62 Healthcare 55K) map directly to ICP targeting. Avoids aggregation over 867K rows at query time.
- **Migration:** 042

### entities.mv_sba_loans_typed
- **Source table(s):** `entities.sba_7a_loans`
- **Estimated row count:** ~356,375 (SBA has a single `extract_date` of 2025-12-31; no multi-snapshot dedup needed)
- **Pre-computes:** Typed base view — loan amount columns cast from TEXT to NUMERIC (`grossapproval`, `sbaguaranteedapproval`, `grosschargeoffamount`), date columns cast from TEXT to DATE (`approvaldate` — format is `M/D/YYYY`, `firstdisbursementdate`, `paidinfulldate`, `chargeoffdate`), `terminmonths` and `jobssupported` cast to INTEGER, `approvalfiscalyear` cast to INTEGER. Modeled after `mv_usaspending_contracts_typed`. Note: `grossapproval` is already castable as NUMERIC in production (confirmed from sample: values like `2138000`, `100000`).
- **Proposed indexes:**
  - `idx_mv_sba_typed_borrstate` (unique composite: `borrstate`, `borrname`, `approvaldate_cast`) — enables CONCURRENTLY refresh using natural near-key; no single unique column exists in SBA data
  - `idx_mv_sba_typed_state` (`borrstate`) — geographic filtering
  - `idx_mv_sba_typed_naics` (`naicscode`) — vertical filtering
  - `idx_mv_sba_typed_approval_date` (`approvaldate_cast`) — time-series analysis
  - `idx_mv_sba_typed_gross` (`grossapproval_numeric`) — loan amount filtering
- **Recommended refresh:** WEEKLY (SBA data updates less frequently than FMCSA; current extract_date is 2025-12-31)
- **Rationale:** All loan amount and date columns in sba_7a_loans are TEXT — every analytical query must cast. Pre-casting enables numeric loan amount comparisons and date range filtering without per-query overhead on 356K rows.
- **Migration:** 042

### entities.mv_sba_loans_by_state
- **Source table(s):** `entities.sba_7a_loans`
- **Estimated row count:** ~57 (one row per distinct borrower state)
- **Pre-computes:** Aggregate per `borrstate`: loan count, total gross approval (SUM of `grossapproval::NUMERIC`), average loan size, count by `loanstatus` (EXEMPT/PIF/CANCLD/COMMIT/CHGOFF). Production data confirms `grossapproval` casts cleanly to NUMERIC — no regex guard needed for current data, though included defensively.
- **Proposed indexes:**
  - `idx_mv_sba_state_agg_state` (unique, `borrstate`) — enables CONCURRENTLY refresh
- **Recommended refresh:** WEEKLY
- **Rationale:** Geographic outbound targeting for SBA-backed businesses; enables instant state-level loan volume dashboards. Top states by loan count: CA (41K loans, $26B), TX (27K, $20B), FL (26K, $15K) — meaningful targeting signal.
- **Migration:** 042

### entities.mv_sam_usaspending_bridge
- **Source table(s):** `entities.sam_gov_entities` + `entities.mv_usaspending_contracts_typed`
- **Estimated row count:** ~118,422 (confirmed by production JOIN: 118,422 distinct SAM.gov UEIs have at least one matching USASpending contract)
- **Pre-computes:** Cross-vertical join on `unique_entity_id = recipient_uei`; aggregates per entity: total contract count, total obligated dollars (SUM of `total_dollars_obligated`), first and latest contract dates, top awarding agency (by contract count using `mode()` aggregate), distinct NAICS codes used, SAM.gov entity metadata (legal name, state, NAICS). Uses latest-snapshot SAM.gov data via DISTINCT ON on `(unique_entity_id, extract_date DESC)`.
- **Proposed indexes:**
  - `idx_mv_sam_usa_bridge_uei` (unique, `unique_entity_id`) — enables CONCURRENTLY refresh; `unique_entity_id` is the join key and is unique per entity in the deduped source
  - `idx_mv_sam_usa_bridge_state` (`physical_address_province_or_state`) — geographic filtering
  - `idx_mv_sam_usa_bridge_naics` (`primary_naics`) — vertical filtering
  - `idx_mv_sam_usa_bridge_obligated` (`total_obligated_dollars`) — high-value contractor targeting
- **Recommended refresh:** WEEKLY (after both USASpending and SAM.gov data are refreshed)
- **Rationale:** This is the highest-value cross-vertical view in the dataset. It surfaces which registered government contractors have award history, their total obligated value, and their agency relationships — enabling precise outbound targeting of active federal contractors by vertical, geography, and contract value. The UEI join key (`unique_entity_id` in SAM.gov = `recipient_uei` in USASpending) is confirmed to exist in both tables with 118,422 matching entities.
- **Migration:** 042

### entities.mv_fmcsa_latest_insurance_policies
- **Source table(s):** `entities.insurance_policies`
- **Estimated row count:** ~1,427,273 (audit confirms insurance_policies has 1.4M rows; this is not a latest-snapshot dedup since insurance_policies represents current active policies per docket_number, not a daily-snapshot table in the same pattern as census records)
- **Pre-computes:** Filters to non-removal-signal rows (`is_removal_signal = FALSE`) representing current active coverage posture per carrier docket. Includes key coverage columns: `docket_number`, `feed_date`, `insurance_type_code`, `insurance_type_description`, `bipd_class_code`, `bipd_maximum_dollar_limit_thousands_usd`, `policy_number`, `effective_date`. Note: `insurance_policies` does not have a `usdot_number` column (confirmed in migration 040 audit note) — the join key to census/master is `docket_number`.
- **Proposed indexes:**
  - `idx_mv_fmcsa_lip_docket` (unique, `docket_number`, `insurance_type_code`, `policy_number`) — enables CONCURRENTLY refresh using natural composite key; no single unique column
  - `idx_mv_fmcsa_lip_feed_date` (`feed_date`) — time-based freshness filtering
  - `idx_mv_fmcsa_lip_ins_type` (`insurance_type_code`) — coverage type filtering
  - `idx_mv_fmcsa_lip_bipd_limit` (`bipd_maximum_dollar_limit_thousands_usd`) — coverage amount filtering
- **Recommended refresh:** DAILY (after FMCSA feed ingestion)
- **Rationale:** Active insurance posture per carrier is a key signal for FMCSA-based sales targeting (insurance brokers, risk assessors). Filtering to non-removal signals eliminates approximately half the raw rows at query time and pre-structures the data for join with `mv_fmcsa_carrier_master` via `docket_number`.
- **Migration:** 042

### entities.mv_fmcsa_new_carriers_90d
- **Source table(s):** `entities.motor_carrier_census_records`
- **Estimated row count:** ~16,431 (confirmed by production query: 16,431 carriers in latest census snapshot with `add_date >= CURRENT_DATE - 90 days`)
- **Pre-computes:** Latest census snapshot per carrier (same DISTINCT ON pattern as `mv_fmcsa_latest_census`) filtered to carriers whose `add_date` falls within the last 90 days. Includes curated carrier identity columns: `dot_number`, `legal_name`, `dba_name`, `physical_state`, `physical_city`, `physical_zip`, `telephone`, `email_address`, `carrier_operation_code`, `power_unit_count`, `driver_total`, `add_date`, `authorized_for_hire`, `hazmat_flag`. The `add_date` column is native DATE type (confirmed in audit).
- **Proposed indexes:**
  - `idx_mv_fmcsa_nc90_dot` (unique, `dot_number`) — enables CONCURRENTLY refresh
  - `idx_mv_fmcsa_nc90_add_date` (`add_date`) — time-series filtering within window
  - `idx_mv_fmcsa_nc90_state` (`physical_state`) — geographic filtering
- **Recommended refresh:** DAILY (after FMCSA feed ingestion; window advances daily so stale data degrades quickly)
- **Rationale:** Newly registered carriers are a high-value outbound signal for insurance, equipment, and compliance services. This MV materializes the 90-day window at refresh time, eliminating the DISTINCT ON + date filter over 3.2M rows at query time. The 16K row count confirms meaningful volume at a manageable refresh cost.
- **Migration:** 042

---

## Tables Without MVs (>10K rows)

| Table | Est. rows | feed_date pattern | extract_date pattern | Has MV | Proposed MV |
|---|---:|---|---|---|---|
| `operating_authority_histories` | 28,965,968 | yes (daily) | — | partial (`mv_fmcsa_authority_grants` filters to grants only) | none additional — grants MV covers the high-value subset |
| `usaspending_contracts` | 14,665,610 | — | yes | yes (`mv_usaspending_contracts_typed`) | none |
| `process_agent_filings` | 7,766,985 | yes (daily) | — | no | none recommended — no analytical query pattern identified |
| `carrier_safety_basic_measures` | 4,569,132 | yes (daily) | — | no | none recommended — measures are the raw BASIC violation counts; percentiles MV covers the analytical use case |
| `operating_authority_revocations` | 4,414,358 | yes (daily) | — | no | none recommended — revocations are an event log; no latest-snapshot dedup value |
| `commercial_vehicle_crashes` | 3,808,001 | yes (daily) | — | yes (`mv_fmcsa_crash_counts_12mo`) | none |
| `insurance_policy_history_events` | 3,707,493 | yes (daily) | — | yes (`mv_fmcsa_insurance_cancellations`) | none |
| `motor_carrier_census_records` | 3,221,542 | yes (daily) | — | yes (`mv_fmcsa_latest_census`) | `mv_fmcsa_new_carriers_90d` (proposed 042) |
| `insurance_policy_filings` | 3,084,873 | yes (daily) | — | no | none recommended — filings are an event log; no clear latest-snapshot value without a clear unique key per carrier |
| `vehicle_inspection_special_studies` | 2,944,780 | yes (daily) | — | no | none recommended — no carrier identifier column (keyed by inspection_id) |
| `carrier_inspections` | 2,840,500 | yes (daily) | — | no | none recommended — inspection-level event log; no clear dedup pattern |
| `carrier_registrations` | 2,427,513 | yes (daily) | — | no | none recommended — `mv_fmcsa_carrier_master` covers authority status via `mv_fmcsa_latest_census`; latest carrier_registrations snapshot is 10,323 rows (very sparse) and `usdot_number` is the join key |
| `carrier_inspection_violations` | 2,195,501 | yes (daily) | — | no | none recommended — violation-level event log |
| `vehicle_inspection_units` | 1,984,569 | yes (daily) | — | no | none recommended — no carrier identifier column |
| `insurance_policies` | 1,427,273 | yes (daily) | — | no | `mv_fmcsa_latest_insurance_policies` (proposed 042) |
| `out_of_service_orders` | 1,150,850 | yes (daily) | — | no | none recommended — OOS is a signal already available via carrier_master safety flags |
| `sam_gov_entities` | 867,137 | — | yes (single date) | no | `mv_sam_gov_entities_typed`, `mv_sam_gov_entities_by_state`, `mv_sam_gov_entities_by_naics`, `mv_sam_usaspending_bridge` (proposed 042) |
| `sba_7a_loans` | 356,375 | — | yes (single date) | no | `mv_sba_loans_typed`, `mv_sba_loans_by_state` (proposed 042) |
| `insurance_filing_rejections` | 123,064 | yes (daily) | — | no | none recommended — rejection log; low analytical value |
| `carrier_safety_basic_percentiles` | 109,728 | yes (daily) | — | yes (`mv_fmcsa_latest_safety_percentiles`) | none |
| `vehicle_inspection_citations` | 81,690 | yes (daily) | — | no | none recommended — citation log; no carrier identifier column |
| `company_entities` | 45,196 | — | — | no | none recommended — entity table; covered by API layer |

---

## Cross-Vertical Joins

### mv_sam_usaspending_bridge

**Tables joined:** `entities.sam_gov_entities` × `entities.mv_usaspending_contracts_typed`

**Join key:** `sam_gov_entities.unique_entity_id = mv_usaspending_contracts_typed.recipient_uei`

**Key confirmation:** Both columns confirmed to exist and be populated in production. `unique_entity_id` in SAM.gov is TEXT; `recipient_uei` in USASpending is TEXT. 118,422 distinct UEIs join successfully (out of 867,137 SAM.gov entities = ~13.6% match rate). 14,441,118 USASpending contract rows reference a SAM.gov-matching UEI.

**What it enables:**
- Identify registered government contractors by vertical (NAICS), geography (state), and active award history
- Filter by total obligated contract value to find high-value contractors
- Surface contractors who are registered in SAM.gov but have not yet received awards (complement set)
- Join with SBA loans via borrower name (fuzzy) or state for multi-program outbound targeting

---

## Audit Notes and Column Name Findings

The following column names in production differ from what the directive assumed:

| Directive assumption | Actual column name | Table | Note |
|---|---|---|---|
| `registration_status` | `sam_extract_code` | `sam_gov_entities` | Values: `A` (active, 771K), `E` (expired, 95K) |
| `physical_state_or_province` | `physical_address_province_or_state` | `sam_gov_entities` | Full column name includes `_address_` segment |
| `naics_code_highest` | `primary_naics` | `sam_gov_entities` | 6-digit NAICS stored as TEXT |
| `gross_approval` | `grossapproval` | `sba_7a_loans` | All lowercase, no underscore |
| `borrower_state` | `borrstate` | `sba_7a_loans` | SBA uses abbreviated column names throughout |
| `approvaldate` (DATE) | `approvaldate` (TEXT) | `sba_7a_loans` | Format is `M/D/YYYY` not ISO — requires cast |

SAM.gov date columns: all stored as TEXT. Formats include `YYYYMMDD` (e.g., `20070323` for `initial_registration_date`) and `YYYYMMDD` for registration dates. These require `TO_DATE(..., 'YYYYMMDD')` cast.

SAM.gov has a single `extract_date` value (`2026-03-01`) — there is no multi-snapshot dedup problem. The `mv_sam_gov_entities_typed` MV does not need DISTINCT ON logic.

SBA has a single `extract_date` value (`2025-12-31`). `grossapproval` casts cleanly to NUMERIC (production sample confirmed).

FMCSA gap: `insurance_policies` does not have a `usdot_number` column — the carrier join key is `docket_number`. This means `mv_fmcsa_latest_insurance_policies` cannot be directly joined to `mv_fmcsa_carrier_master` (which uses `dot_number`). A carrier_registrations lookup is needed to bridge `docket_number` → `usdot_number`, but `carrier_registrations` only has 10,323 rows in the latest snapshot — sparse coverage. The proposed MV is still valuable as a standalone insurance coverage inventory; joining to carrier master requires the docket → DOT bridge through carrier_registrations.

**Runtime warning:** `mv_sam_usaspending_bridge` requires a hash join of 867K × 14.7M rows (filtered to ~118K matching entities). The join is against `mv_usaspending_contracts_typed` (already an MV, not the raw 14.7M TEXT table) with an index on `recipient_uei`. Estimated refresh time: 5–15 minutes. Flag for chief agent awareness — run during low-traffic window.
