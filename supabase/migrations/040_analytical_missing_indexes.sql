-- Migration 040: Supplemental Indexes for Analytical Query Patterns
--
-- Index audit of tables in migrations 022-025, 030-032.
--
-- FMCSA tables audited (22, 23, 24, 25):
--   operating_authority_histories — usdot_number, docket_number already indexed (022)
--   operating_authority_revocations — usdot_number, docket_number already indexed (022)
--   insurance_policies — docket_number indexed; table has no usdot_number column (022)
--   insurance_policy_filings — usdot_number, docket_number already indexed (022)
--   insurance_policy_history_events — usdot_number, docket_number already indexed (022)
--   carrier_registrations — usdot_number, docket_number already indexed (023)
--   process_agent_filings — usdot_number, docket_number already indexed (023)
--   insurance_filing_rejections — usdot_number, docket_number already indexed (023)
--   motor_carrier_census_records — dot_number already indexed (024)
--   carrier_safety_basic_measures — dot_number already indexed (024)
--   carrier_safety_basic_percentiles — dot_number already indexed (024)
--   carrier_inspections — dot_number already indexed (024)
--   carrier_inspection_violations — dot_number already indexed (024)
--   commercial_vehicle_crashes — dot_number already indexed (025)
--   out_of_service_orders — dot_number already indexed (025)
--   vehicle_inspection_units — no carrier identifier column (keyed by inspection_id)
--   vehicle_inspection_special_studies — no carrier identifier column (keyed by inspection_id)
--   vehicle_inspection_citations — no carrier identifier column (keyed by inspection_id)
--
-- Result: No missing FMCSA indexes. All carrier-level tables already have indexes
-- on their primary lookup columns.
--
-- Additional composite indexes below support common analytical join/filter patterns.
--
-- NOTE: No BEGIN/COMMIT wrapper. Index creation on 14.6M+ row tables exceeds
-- Supabase's default statement_timeout inside a transaction.

SET statement_timeout = '0';

-- USASpending: composite indexes for common analytical joins
CREATE INDEX IF NOT EXISTS idx_usaspending_contracts_uei_action_date
    ON entities.usaspending_contracts (recipient_uei, action_date);

CREATE INDEX IF NOT EXISTS idx_usaspending_contracts_agency_naics
    ON entities.usaspending_contracts (awarding_agency_name, naics_code);

-- SAM.gov: composite index for DISTINCT ON latest-snapshot pattern (used in migration 034)
CREATE INDEX IF NOT EXISTS idx_sam_gov_entities_uei_extract_date
    ON entities.sam_gov_entities (unique_entity_id, extract_date DESC);

-- SBA 7(a): geographic lookup by borrower zip code
CREATE INDEX IF NOT EXISTS idx_sba_7a_loans_borrzip
    ON entities.sba_7a_loans (borrzip);

RESET statement_timeout;
