# Executor Directive: Analytical Materialized Views & Index Tuning

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The large tables in the `entities` schema — `usaspending_contracts` (14.6M rows, 308 TEXT columns), FMCSA census/safety/crash tables (collectively ~75M rows) — are unusable for interactive analytical queries from tools like Hex or psql. Self-joins on `usaspending_contracts` timeout because every aggregation requires casting TEXT columns to numeric/date types across 14.6M rows. FMCSA queries repeat the same expensive latest-snapshot CTE pattern (`DISTINCT ON (dot_number) WHERE feed_date = MAX(feed_date)`) on every single query. The API service layer already implements these patterns as CTEs (`app/services/fmcsa_carrier_query.py`, `app/services/fmcsa_safety_risk.py`), but analysts hitting the database directly pay the full cost every time.

The goal: after these migrations run, an analyst connecting from Hex or psql can run common queries (carrier lookups, first-time awardee identification, cross-table joins, safety risk ranking) without hitting timeouts.

---

## Existing code to read

Before writing any migration SQL, read these files carefully to understand the existing patterns:

### Existing materialized view migrations (your pattern templates)

- `supabase/migrations/033_mv_federal_contract_leads.sql` — the first federal MV. Study the CTE chain, `DISTINCT ON` pattern, index strategy, and the `SET statement_timeout = '0'` pattern. Note: migration 034 replaced this with an expanded version.
- `supabase/migrations/034_mv_federal_contract_leads_agency_first_time.sql` — the current production MV for federal contract leads. Study the 7-CTE chain, multi-agency first-time-awardee computation, join pattern on `recipient_uei`, and the index strategy (unique index for `REFRESH CONCURRENTLY`, plus filtered indexes on boolean flags).
- `supabase/migrations/036_mv_fmcsa_authority_grants.sql` — FMCSA authority grants MV. Study the pre-filter pattern and index strategy.
- `supabase/migrations/037_mv_fmcsa_insurance_cancellations.sql` — FMCSA insurance cancellations MV. Same pattern.

### FMCSA query patterns to replicate as MVs

- `app/services/fmcsa_carrier_query.py` — the latest-census-snapshot CTE. This is the query pattern that `mv_fmcsa_latest_census` should eliminate.
- `app/services/fmcsa_safety_risk.py` — the 3-way join (latest census + latest safety percentiles + trailing-12-month crash counts). This is the query pattern that `mv_fmcsa_carrier_master` should eliminate.
- `app/routers/fmcsa_v1.py` — shows which endpoints serve these queries. The MVs should make these faster but do NOT require API code changes.

### Source table schemas

- `supabase/migrations/031_usaspending_contracts.sql` — all 308 TEXT columns. The executor needs to know exact column names for the typed MV.
- `supabase/migrations/030_sam_gov_entities.sql` — SAM.gov table schema.
- `supabase/migrations/032_sba_7a_loans.sql` — SBA 7(a) loans schema.
- `supabase/migrations/024_fmcsa_sms_tables.sql` — FMCSA SMS tables (census, safety measures, safety percentiles, inspections, inspection violations). Note existing indexes.
- `supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql` — FMCSA remaining tables (crashes, vehicle inspection units, etc.). Note existing indexes.
- `supabase/migrations/023_fmcsa_snapshot_history_tables.sql` — FMCSA snapshot/history tables (operating authority, insurance, carrier registrations). Note existing indexes.

### Deploy protocol

- `docs/DEPLOY_PROTOCOL.md` — migration numbering convention and the migration list you must update.

---

## Existing index state (do not duplicate)

The following indexes already exist in production. Do NOT recreate them. If you need additional indexes beyond these, add them in the migration.

**USASpending contracts** (migration 031): `contract_transaction_unique_key`, `contract_award_unique_key`, `recipient_uei`, `action_date`, `awarding_agency_name`, `naics_code`, `extract_date`

**SAM.gov entities** (migration 030): `unique_entity_id`, `extract_date`, `entity_registration_expiration_date__extract_code`, `primary_naics`, `physical_address_province_or_state_code`, `legal_business_name`

**SBA 7(a) loans** (migration 032): `borrname`, `borrstate`, `naicscode`, `approvaldate`, `extract_date`, `loanstatus`

**FMCSA tables** (migrations 023-025): All 18 canonical tables have indexes on `feed_date` and their primary lookup columns (`dot_number`, `docket_number`, `usdot_number`, etc.).

---

## Deliverable 1: USASpending Analytical Views

Create migration `supabase/migrations/038_mv_usaspending_analytical.sql`.

Follow the established migration patterns:

```sql
SET statement_timeout = '0';
BEGIN;
-- ... views and indexes ...
COMMIT;
```

### View 1: `entities.mv_usaspending_contracts_typed`

A clean typed base view of `usaspending_contracts` that casts the most analytically useful columns to proper types so downstream queries don't pay casting costs on every run.

**Source:** `entities.usaspending_contracts`

**De-duplication:** Use `DISTINCT ON (contract_transaction_unique_key) ... ORDER BY contract_transaction_unique_key, extract_date DESC` to get the latest version of each transaction (same pattern as migration 034).

**Columns to include (cast from TEXT to proper types):**

| Column | Target Type | Notes |
|---|---|---|
| `contract_transaction_unique_key` | TEXT (as-is) | Primary key |
| `contract_award_unique_key` | TEXT (as-is) | Award grouping |
| `recipient_uei` | TEXT (as-is) | Join key to SAM |
| `recipient_name` | TEXT (as-is) | Display |
| `recipient_parent_uei` | TEXT (as-is) | Parent company |
| `recipient_parent_name` | TEXT (as-is) | Display |
| `awarding_agency_name` | TEXT (as-is) | Primary filter |
| `awarding_sub_agency_name` | TEXT (as-is) | Secondary filter |
| `funding_agency_name` | TEXT (as-is) | Filter |
| `naics_code` | TEXT (as-is) | Industry filter |
| `naics_description` | TEXT (as-is) | Display |
| `product_or_service_code` | TEXT (as-is) | PSC filter |
| `product_or_service_code_description` | TEXT (as-is) | Display |
| `federal_action_obligation` | NUMERIC | Cast with `NULLIF(federal_action_obligation, '')::NUMERIC` |
| `total_dollars_obligated` | NUMERIC | Same cast pattern |
| `base_and_exercised_options_value` | NUMERIC | Same cast pattern |
| `current_total_value_of_award` | NUMERIC | Same cast pattern |
| `action_date` | DATE | Cast with `NULLIF(action_date, '')::DATE` |
| `period_of_performance_start_date` | DATE | Same cast pattern |
| `period_of_performance_current_end_date` | DATE | Same cast pattern |
| `award_type` | TEXT (as-is) | Filter |
| `type_of_contract_pricing` | TEXT (as-is) | Filter |
| `recipient_city_name` | TEXT (as-is) | Geo filter |
| `recipient_state_code` | TEXT (as-is) | Geo filter |
| `recipient_country_code` | TEXT (as-is) | Geo filter |
| `place_of_performance_state_code` | TEXT (as-is) | Geo filter |
| `small_business_competitive_flag` | BOOLEAN | Cast non-empty to boolean if possible, else TEXT |
| `extract_date` | DATE | Cast |

The executor should check the actual column names in migration 031 and adjust if any names differ slightly. Use `NULLIF(..., '')` before casting to avoid cast errors on empty strings. Use explicit `NULL` for values that fail to cast (wrap in a CASE or use `try_cast`-style pattern if Postgres version supports it, otherwise let NULLs propagate from NULLIF).

**Add a SQL comment at the top of the view definition:**

```sql
-- Refresh: weekly, or after USASpending backfill ingestion
-- Source: entities.usaspending_contracts (14.6M+ rows, all TEXT)
-- Purpose: pre-cast typed base for analytical queries from Hex/psql
```

**Indexes on the MV:**

```sql
CREATE UNIQUE INDEX idx_mv_usa_typed_txn_key ON entities.mv_usaspending_contracts_typed (contract_transaction_unique_key);
CREATE INDEX idx_mv_usa_typed_recipient_uei ON entities.mv_usaspending_contracts_typed (recipient_uei);
CREATE INDEX idx_mv_usa_typed_action_date ON entities.mv_usaspending_contracts_typed (action_date);
CREATE INDEX idx_mv_usa_typed_agency ON entities.mv_usaspending_contracts_typed (awarding_agency_name);
CREATE INDEX idx_mv_usa_typed_naics ON entities.mv_usaspending_contracts_typed (naics_code);
CREATE INDEX idx_mv_usa_typed_state ON entities.mv_usaspending_contracts_typed (recipient_state_code);
CREATE INDEX idx_mv_usa_typed_obligation ON entities.mv_usaspending_contracts_typed (federal_action_obligation);
```

The unique index on `contract_transaction_unique_key` enables `REFRESH MATERIALIZED VIEW CONCURRENTLY`.

### View 2: `entities.mv_usaspending_first_contracts`

First contract date per company — the foundation for first-time vs repeat awardee analysis.

**Source:** `entities.usaspending_contracts`

**Definition:**

```sql
CREATE MATERIALIZED VIEW entities.mv_usaspending_first_contracts AS
-- Refresh: weekly, or after USASpending backfill ingestion
-- Purpose: first contract per recipient for first-time awardee analysis
SELECT
    recipient_uei,
    MIN(NULLIF(action_date, '')::DATE) AS first_contract_date,
    (array_agg(awarding_agency_name ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_agency,
    (array_agg(naics_code ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_naics,
    (array_agg(contract_award_unique_key ORDER BY NULLIF(action_date, '')::DATE ASC NULLS LAST))[1] AS first_contract_award_key,
    COUNT(DISTINCT contract_award_unique_key) AS total_awards
FROM entities.usaspending_contracts
WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
GROUP BY recipient_uei;
```

The executor should verify the exact column names from migration 031 and adjust. The key insight: this view lets analysts do `WHERE total_awards = 1` to find first-time awardees, or join on `recipient_uei` to enrich any company lookup with first-contract metadata.

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_mv_usa_first_uei ON entities.mv_usaspending_first_contracts (recipient_uei);
CREATE INDEX idx_mv_usa_first_date ON entities.mv_usaspending_first_contracts (first_contract_date);
CREATE INDEX idx_mv_usa_first_total_awards ON entities.mv_usaspending_first_contracts (total_awards);
```

Commit standalone.

---

## Deliverable 2: FMCSA Analytical Views

Create migration `supabase/migrations/039_mv_fmcsa_analytical.sql`.

Same `SET statement_timeout = '0'; BEGIN; ... COMMIT;` pattern.

### View 1: `entities.mv_fmcsa_latest_census`

Latest census snapshot — eliminates the repeated `DISTINCT ON (dot_number) WHERE feed_date = MAX(feed_date)` CTE.

**Source:** `entities.motor_carrier_census_records`

**Definition pattern:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_latest_census AS
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.motor_carrier_census_records
-- Purpose: latest snapshot per carrier, eliminating repeated DISTINCT ON CTE
SELECT DISTINCT ON (dot_number) *
FROM entities.motor_carrier_census_records
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)
ORDER BY dot_number, row_position;
```

**Important:** This replicates exactly the CTE in `app/services/fmcsa_carrier_query.py`. The executor should read that file to confirm the exact pattern and column ordering.

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_mv_fmcsa_lc_dot ON entities.mv_fmcsa_latest_census (dot_number);
CREATE INDEX idx_mv_fmcsa_lc_state ON entities.mv_fmcsa_latest_census (physical_state);
CREATE INDEX idx_mv_fmcsa_lc_op_code ON entities.mv_fmcsa_latest_census (carrier_operation_code);
CREATE INDEX idx_mv_fmcsa_lc_legal_name ON entities.mv_fmcsa_latest_census (legal_name);
CREATE INDEX idx_mv_fmcsa_lc_power_units ON entities.mv_fmcsa_latest_census (power_unit_count);
```

Verify column names against migration 024.

### View 2: `entities.mv_fmcsa_latest_safety_percentiles`

Latest safety percentile snapshot — same pattern for the safety/compliance data.

**Source:** `entities.carrier_safety_basic_percentiles`

**Definition pattern:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_latest_safety_percentiles AS
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.carrier_safety_basic_percentiles
-- Purpose: latest safety percentile snapshot per carrier
SELECT DISTINCT ON (dot_number) *
FROM entities.carrier_safety_basic_percentiles
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.carrier_safety_basic_percentiles)
ORDER BY dot_number, row_position;
```

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_mv_fmcsa_lsp_dot ON entities.mv_fmcsa_latest_safety_percentiles (dot_number);
```

Add additional indexes on the percentile columns used for filtering in `fmcsa_safety_risk.py` (trace the file to identify which percentile columns are commonly filtered — likely `unsafe_driving_percentile`, `hours_of_service_percentile`, `vehicle_maintenance_percentile`).

### View 3: `entities.mv_fmcsa_crash_counts_12mo`

Trailing 12-month crash counts per carrier — eliminates the crash count CTE from the 3-way join.

**Source:** `entities.commercial_vehicle_crashes`

**Definition pattern:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_crash_counts_12mo AS
-- Refresh: daily, after FMCSA feed ingestion completes
-- Source: entities.commercial_vehicle_crashes
-- Purpose: trailing 12-month crash counts per carrier
SELECT
    dot_number,
    COUNT(*) AS crash_count_12mo,
    MAX(report_date) AS latest_crash_date,
    SUM(CASE WHEN fatalities > 0 THEN 1 ELSE 0 END) AS fatal_crash_count_12mo
FROM entities.commercial_vehicle_crashes
WHERE feed_date = (SELECT MAX(feed_date) FROM entities.commercial_vehicle_crashes)
  AND report_date >= CURRENT_DATE - INTERVAL '12 months'
GROUP BY dot_number;
```

The executor should verify the exact column names from migration 025 (especially `fatalities` — check if it exists or if the fatal count needs to be derived differently). If `fatalities` doesn't exist as a column, drop the `fatal_crash_count_12mo` computed column.

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_mv_fmcsa_cc12_dot ON entities.mv_fmcsa_crash_counts_12mo (dot_number);
CREATE INDEX idx_mv_fmcsa_cc12_count ON entities.mv_fmcsa_crash_counts_12mo (crash_count_12mo);
```

### View 4: `entities.mv_fmcsa_carrier_master`

Master carrier view — joins latest census + latest safety percentiles + crash counts. This is the single table that most analytical queries should start from.

**Source:** The three MVs above (or directly from the source tables if the executor determines that nesting MVs is problematic — use judgment).

**Definition pattern:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_carrier_master AS
-- Refresh: daily, after the three upstream MVs are refreshed
-- Purpose: master carrier view joining census + safety + crashes for one-stop analytical queries
SELECT
    census.*,
    safety.unsafe_driving_percentile,
    safety.hours_of_service_percentile,
    safety.vehicle_maintenance_percentile,
    safety.driver_fitness_percentile,
    safety.controlled_substances_alcohol_percentile,
    -- include alert flag columns from safety if they exist
    COALESCE(crashes.crash_count_12mo, 0) AS crash_count_12mo,
    crashes.latest_crash_date,
    COALESCE(crashes.fatal_crash_count_12mo, 0) AS fatal_crash_count_12mo
FROM entities.mv_fmcsa_latest_census census
LEFT JOIN entities.mv_fmcsa_latest_safety_percentiles safety ON census.dot_number = safety.dot_number
LEFT JOIN entities.mv_fmcsa_crash_counts_12mo crashes ON census.dot_number = crashes.dot_number;
```

**Important:** The executor should read `app/services/fmcsa_safety_risk.py` to get the exact join pattern and columns. The safety risk service uses `INNER JOIN` for census+safety and `LEFT JOIN` for crashes. The master MV should use `LEFT JOIN` for both so that carriers without safety data or crashes still appear (the MV is for analysis, not risk scoring).

The executor should verify all column names from the source tables. If `SELECT *` from the census table creates ambiguity on the join, select specific columns instead.

**Indexes:**

```sql
CREATE UNIQUE INDEX idx_mv_fmcsa_cm_dot ON entities.mv_fmcsa_carrier_master (dot_number);
CREATE INDEX idx_mv_fmcsa_cm_state ON entities.mv_fmcsa_carrier_master (physical_state);
CREATE INDEX idx_mv_fmcsa_cm_op_code ON entities.mv_fmcsa_carrier_master (carrier_operation_code);
CREATE INDEX idx_mv_fmcsa_cm_crash_count ON entities.mv_fmcsa_carrier_master (crash_count_12mo);
CREATE INDEX idx_mv_fmcsa_cm_unsafe_driving ON entities.mv_fmcsa_carrier_master (unsafe_driving_percentile);
```

Commit standalone.

---

## Deliverable 3: Missing Base Table Indexes

Create migration `supabase/migrations/040_analytical_missing_indexes.sql`.

The executor should check the source table schemas (migrations 023-025, 030-032) and add any indexes that are missing for common analytical patterns. Specifically check for:

**FMCSA tables — check and add if missing:**

- `entities.operating_authority_histories` — index on `usdot_number` (may only have `feed_date` + `docket_number`)
- `entities.insurance_policies` — index on `usdot_number` or `docket_number`
- `entities.insurance_policy_filings` — index on `usdot_number` or `docket_number`
- `entities.insurance_policy_history_events` — index on `usdot_number`
- `entities.out_of_service_orders` — index on `dot_number`
- `entities.vehicle_inspection_special_studies` — index on `dot_number`
- `entities.vehicle_inspection_citations` — index on any carrier identifier column

For each table, read the migration that created it to determine the exact column names. Use `CREATE INDEX IF NOT EXISTS` to be safe.

**USASpending — additional composite indexes for common analytical joins:**

```sql
CREATE INDEX IF NOT EXISTS idx_usaspending_contracts_uei_action_date
    ON entities.usaspending_contracts (recipient_uei, action_date);
CREATE INDEX IF NOT EXISTS idx_usaspending_contracts_agency_naics
    ON entities.usaspending_contracts (awarding_agency_name, naics_code);
```

**SAM.gov — check and add if missing:**

- Composite index on `(unique_entity_id, extract_date)` for the `DISTINCT ON` latest-snapshot pattern used in migration 034

**SBA 7(a) — check and add if missing:**

- Index on `borrower_zip` or equivalent geo column if not already indexed

The executor should use judgment — only add indexes that clearly support common query patterns. Do not add speculative indexes. Use `IF NOT EXISTS` on everything.

If after checking, no indexes are missing, this deliverable can be an empty migration with a comment explaining the audit found no gaps. That's a valid outcome.

Commit standalone.

---

## Deliverable 4: Refresh Script & Documentation

Create `scripts/refresh_analytical_views.sql`.

This file should contain the refresh commands for all materialized views in the system, organized by refresh frequency. Include comments explaining the dependency order.

```sql
-- =============================================================
-- Analytical Materialized View Refresh Script
-- =============================================================
-- Run with: doppler run -p data-engine-x-api -c prd -- psql -f scripts/refresh_analytical_views.sql
--
-- Refresh frequency guide:
--   DAILY (after FMCSA feed ingestion): FMCSA views
--   WEEKLY (or after USASpending backfill): USASpending views
--   WEEKLY: Federal contract leads view
--
-- Dependency order:
--   1. Latest-snapshot MVs first (census, safety, crashes)
--   2. Master carrier view second (depends on step 1)
--   3. Independent views in any order
-- =============================================================

-- ---- DAILY: FMCSA latest-snapshot views (run after feed ingestion) ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_latest_census;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_latest_safety_percentiles;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_crash_counts_12mo;

-- depends on the three above
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_carrier_master;

-- existing FMCSA views (from migrations 036, 037)
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_authority_grants;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_fmcsa_insurance_cancellations;

-- ---- WEEKLY: USASpending views ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_usaspending_contracts_typed;
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_usaspending_first_contracts;

-- ---- WEEKLY: Federal contract leads (existing, from migration 034) ----
REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_federal_contract_leads;
```

The executor should verify that `mv_fmcsa_authority_grants` and `mv_fmcsa_insurance_cancellations` exist in migration 036/037 and use the correct schema-qualified names. Also verify `mv_federal_contract_leads` from migration 034.

**Important:** If any of the existing MVs from migrations 036/037 have not been applied to production (the operational reality check notes they may not exist), include them in the script anyway with a comment noting they depend on those migrations being applied first.

Commit standalone.

---

## Deliverable 5: Update Deploy Protocol

Update `docs/DEPLOY_PROTOCOL.md`:

1. Add migrations 038, 039, and 040 to the migration list with brief descriptions.
2. Add a note in the migration section that migrations 038 and 039 create materialized views and will take significant time to run (potentially 10-30 minutes for USASpending at 14.6M rows). Recommend running them during low-traffic windows.

Commit standalone.

---

## Deliverable 6: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Summary should note: created migrations 038-040 adding analytical materialized views for USASpending (typed base + first-contract), FMCSA (latest census, latest safety percentiles, 12-month crash counts, master carrier), and supplemental indexes. Created refresh script at `scripts/refresh_analytical_views.sql`.

Add a last-updated timestamp at the top of each file you create or modify, in the format `**Last updated:** 2026-03-18T[HH:MM:SS]Z`.

Commit standalone.

---

## What is NOT in scope

- **No applying migrations to production.** Commit migration files only. The chief agent will apply manually.
- **No API code changes.** The MVs should make existing queries faster by allowing analysts to query the MVs directly. The API service layer continues using its CTEs — migrating the API to use MVs is a separate future directive.
- **No deploy commands.** Do not push.
- **No changes to existing migrations.** Do not modify migrations 030-037.
- **No Trigger.dev changes.** No workflow or task file changes.
- **No scheduled refresh automation.** The refresh script is manual. Cron/scheduling is a separate concern.
- **Do not create views for tables with fewer than 100K rows.** The small FMCSA tables (signals, process agents, filing rejections) don't need MVs.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Migrations created: file paths, number of views per migration, number of indexes per migration
(b) USASpending views: column count in typed view, row estimate for first-contracts view (based on distinct `recipient_uei` count if knowable)
(c) FMCSA views: list each view, its source table, and estimated row count (based on distinct `dot_number` count if knowable)
(d) Missing indexes: how many added vs how many tables audited. If none were missing, say so.
(e) Refresh script: total views included, estimated total refresh time if knowable
(f) Anything to flag — especially: column names that didn't match expectations, tables that were missing columns assumed in the directive, any Postgres version concerns with the SQL patterns used
