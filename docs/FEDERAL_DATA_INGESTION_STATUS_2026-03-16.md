# Federal Data Ingestion Status — 2026-03-16

## What Was Built

Three federal bulk data sources were ingested into `data-engine-x-api` and a materialized view joins two of them into queryable lead records.

---

## Data Sources Loaded

| Source | Table | Rows | Columns | Ingest Time | Status |
|---|---|---|---|---|---|
| SAM.gov (entity registrations) | `entities.sam_gov_entities` | 867,137 | 142 | 6 min | Production |
| USASpending.gov (contract awards) | `entities.usaspending_contracts` | 1,340,862 | 297 | 18 min | Production |
| SBA 7(a) (loan data) | `entities.sba_7a_loans` | 356,386 | 43 | 73 sec | Production |

**Total: 2,564,385 rows across 3 tables.**

All columns stored as TEXT (lossless ingestion — type casting at query time). Every row tagged with extract metadata: `extract_date`, `source_filename`, `source_provider`, `ingested_at`, `row_position`.

---

## SAM.gov — Federal Entity Registrations

- **Source file:** `SAM_PUBLIC_MONTHLY_V2_20260301.ZIP` (533 MB, pipe-delimited `.dat`, no header row, BOF line)
- **142 columns** (Public V2 extract — FOUO/Sensitive columns excluded)
- **Composite unique key:** `(extract_date, unique_entity_id)`
- **Key fields:** UEI, legal business name, DBA, physical address, POC names/titles (govt, alt govt, e-business, past performance), NAICS codes, business types, entity URL, CAGE code, registration dates
- **7,572 duplicate UEIs** in source file were deduplicated (last occurrence wins)
- **Migration:** `030_sam_gov_entities.sql`
- **Code:** `app/services/sam_gov_column_map.py`, `sam_gov_common.py`, `sam_gov_extract_ingest.py`

---

## USASpending.gov — Federal Contract Award Transactions

- **Source file:** `FY2026_All_Contracts_Full_20260306.zip` (2.8 GB, 2 CSVs split at 1M rows, header row, RFC 4180)
- **297 columns** (full file); delta files have 299 (2 prepended: `correction_delete_ind`, `agency_id`)
- **Composite unique key:** `(extract_date, contract_transaction_unique_key)`
- **Key fields:** recipient UEI/name/address/phone, award amounts (6 tiers from per-action to contract ceiling), awarding/funding agency hierarchy, NAICS code, PSC code, 86 boolean business classification flags (t/f format), award type, competition type, set-aside, executive compensation, USASpending permalink
- **Join key to SAM.gov:** `recipient_uei` = `unique_entity_id` (12-char UEI)
- **7 columns renamed** during ingestion: 4 COVID/IIJA hyphen→underscore conversions, 3 digit-prefixed columns (`1862_`, `1890_`, `1994_` land grant colleges → `col_` prefix)
- **Migration:** `031_usaspending_contracts.sql`
- **Code:** `app/services/usaspending_column_map.py`, `usaspending_common.py`, `usaspending_extract_ingest.py`

---

## SBA 7(a) — Small Business Loan Data

- **Source file:** `foia-7a-fy2020-present-asof-250930.csv` (135 MB, direct download, no auth)
- **43 columns**, 357,866 rows (FY2020–present)
- **Composite unique key:** `(extract_date, borrname, borrstreet, borrcity, borrstate, approvaldate, grossapproval)` — no unique entity identifier exists in this dataset
- **Key fields:** borrower name/address, loan amount, SBA guaranteed amount, approval date, NAICS code/description, lender info, business type/age, loan status, jobs supported
- **`asofdate` in file:** `12/31/2025` (Q1 FY2026 data, despite filename suggesting 09/30/2025)
- **1,480 within-file duplicates** deduplicated on the 7-column composite key
- **No UEI, DUNS, or EIN.** Cannot join to SAM.gov or USASpending. Future entity resolution requires fuzzy matching on name + address or third-party enrichment.
- **Updated quarterly** by SBA (full replacement, not delta). Supports loading multiple quarterly snapshots side by side.
- **Download URL:** `https://data.sba.gov/dataset/0ff8e8e9-b967-4f4e-987c-6ac78c575087/resource/d67d3ccb-2002-4134-a288-481b51cd3479/download/foia-7a-fy2020-present-asof-250930.csv`
- **Migration:** `032_sba_7a_loans.sql`
- **Code:** `app/services/sba_column_map.py`, `sba_common.py`, `sba_ingest.py`

---

## Federal Contract Leads Materialized View

**View:** `entities.mv_federal_contract_leads`

Joins USASpending contract transactions to SAM.gov entity registrations on UEI. Produces flat lead records for outbound campaigns.

### View Stats (as of 2026-03-16)

| Metric | Count |
|---|---|
| Total rows | 1,340,862 |
| Unique companies (UEIs) | 55,773 |
| First-time awardees | 43,487 (78% of companies) |
| With SAM.gov match | 1,337,311 (99.7%) |
| Without SAM.gov match | 3,551 (0.3%) |

### Output Columns (55 total)

- **28 from USASpending:** transaction/award keys, recipient name/address/phone, award type, action date, 3 dollar amount fields, agency hierarchy, NAICS, PSC, business size, set-aside, competition, bid count, USASpending permalink
- **24 from SAM.gov (nullable):** legal business name, DBA, physical address, entity URL, primary NAICS, business types, CAGE code, registration dates, entity structure, 3 POC name/title sets (govt, alt govt, e-business)
- **3 computed:** `is_first_time_awardee` (boolean), `total_awards_count` (integer), `has_sam_match` (boolean)

### First-Time Awardee Logic

A company is flagged as `is_first_time_awardee = TRUE` when its UEI appears on exactly **1 distinct award** (`contract_award_unique_key`) across the entire USASpending dataset. A single award may have multiple transaction rows (modifications) — the count is on distinct awards, not rows.

### Snapshot Handling

The view uses only the **latest snapshot** from each source table:
- SAM.gov: latest `extract_date` per `unique_entity_id`
- USASpending: latest `extract_date` per `contract_transaction_unique_key`

### Indexes (9)

Unique on `contract_transaction_unique_key` (enables concurrent refresh), plus indexes on `recipient_uei`, `recipient_state_code`, `naics_code`, `action_date`, `awarding_agency_code`, `is_first_time_awardee` (partial WHERE TRUE), `contracting_officers_determination_of_business_size`, `federal_action_obligation`.

### Migration

`033_mv_federal_contract_leads.sql` — runs with `SET statement_timeout = '0'` (no transaction wrapper — the join is too heavy for Supabase's default timeout).

---

## API Endpoints Added

### Query Endpoints (tenant JWT or super-admin auth)

| Endpoint | Purpose |
|---|---|
| `POST /api/v1/federal-contract-leads/query` | Query the materialized view with 11 filter parameters |
| `POST /api/v1/federal-contract-leads/stats` | Get view stats (total rows, unique companies, first-time awardees) |

### Query Filters

| Filter | Type | Behavior |
|---|---|---|
| `naics_prefix` | string | LIKE prefix match (e.g., `"31"` for manufacturing) |
| `state` | string | Exact match on 2-letter state code |
| `action_date_from` | string | Date range start (YYYY-MM-DD) |
| `action_date_to` | string | Date range end (YYYY-MM-DD) |
| `min_obligation` | string | Minimum dollar amount (cast to numeric) |
| `business_size` | string | `SMALL BUSINESS` or `OTHER THAN SMALL BUSINESS` |
| `first_time_only` | bool | Filter to first-time awardees only |
| `awarding_agency_code` | string | Exact match on 3-digit CGAC code |
| `has_sam_match` | bool | Filter to records with SAM.gov enrichment |
| `recipient_uei` | string | Exact UEI lookup |
| `recipient_name` | string | Partial name search (ILIKE) |

### Internal Endpoints (service auth)

| Endpoint | Purpose |
|---|---|
| `POST /api/internal/usaspending-contracts/ingest` | Ingest a USASpending ZIP file |
| `POST /api/internal/sba-7a-loans/ingest` | Ingest an SBA 7(a) CSV file |
| `POST /api/internal/federal-contract-leads/refresh` | Refresh the materialized view |

---

## Code Modules Added

### USASpending

| File | Purpose |
|---|---|
| `app/services/usaspending_column_map.py` | 297-column map with 7 renamed columns |
| `app/services/usaspending_common.py` | Bulk COPY persistence, connection pool, row parser/builder |
| `app/services/usaspending_extract_ingest.py` | CSV ingest service with multi-file ZIP handling |

### SBA 7(a)

| File | Purpose |
|---|---|
| `app/services/sba_column_map.py` | 43-column map (all identity-mapped) |
| `app/services/sba_common.py` | Bulk COPY persistence with 7-column composite dedup |
| `app/services/sba_ingest.py` | CSV ingest service |

### Federal Leads View

| File | Purpose |
|---|---|
| `app/services/federal_leads_refresh.py` | Concurrent materialized view refresh, stats query |
| `app/services/federal_leads_query.py` | Parameterized query service with 11 filters |

### Tests

| File | Tests |
|---|---|
| `tests/test_usaspending_ingest.py` | 30 tests (column map, parser, row builder, ingest service) |
| `tests/test_sba_ingest.py` | 21 tests (column map, parser, row builder, ingest service) |
| `tests/test_federal_leads.py` | 18 tests (query service, endpoints) |

### Validation Scripts

| File | Purpose |
|---|---|
| `scripts/validate_usaspending_parse.py` | Parse 100 real rows from FY2026 full + 10 delta rows |
| `scripts/validate_sba_parse.py` | Parse 100 real rows from SBA CSV |
| `scripts/run_usaspending_full_ingest.py` | Full 1.34M row ingest runner |
| `scripts/run_sba_full_ingest.py` | Full 357K row ingest runner |

---

## Architecture Pattern

All three ingestion pipelines follow the same architecture:

1. **Column map module** — hardcoded ordered list of column definitions with self-test
2. **Migration** — `entities` schema, all TEXT columns, extract metadata, composite unique key, indexes, RLS
3. **Common utilities** — dedicated `psycopg_pool` connection pool, source context TypedDict, row parser, row builder, bulk COPY upsert (temp staging table → COPY → INSERT...ON CONFLICT merge)
4. **Ingest service** — chunked persistence (50K rows/chunk), header validation, error re-raise
5. **Internal endpoint** — service auth, accepts file path + metadata
6. **Tests** — column map, parser, row builder, ingest service (all mocked)
7. **Validation script** — parse real data, no DB writes

Persistence pattern: `psycopg_pool.ConnectionPool` → temp staging table → `COPY` (tab-delimited) → `INSERT INTO ... SELECT FROM tmp ON CONFLICT DO UPDATE`. Statement timeout 600s. Phase timing instrumentation. Dedup by composite key (last occurrence wins).

---

## What's Not Built Yet

1. **SBA 7(a) query endpoint** — SBA data is loaded but has no `/query` endpoint yet. Needs its own since it can't join to the other tables.
2. **SBA entity resolution** — Linking SBA loans to SAM.gov/USASpending requires fuzzy matching on name + address or third-party enrichment (no shared identifier exists).
3. **USASpending delta ingestion logic** — Delta files are parseable (2 prepended columns handled), but soft-delete logic for `correction_delete_ind = 'D'` rows is not implemented.
4. **Scheduled view refresh** — The materialized view refresh is manual (via internal endpoint). No automated periodic refresh.
5. **Trigger.dev integration** — All ingestion is manual (scripts). No Trigger.dev tasks for automated ingestion.
6. **Historical USASpending data** — Only FY2026 is loaded. Prior fiscal years available from USASpending bulk downloads.
7. **Data freshness** — SAM.gov publishes monthly extracts, USASpending updates weekly (full + delta), SBA updates quarterly. No automated download or ingestion pipeline.
