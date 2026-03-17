# FMCSA Data: API Endpoints, Current State, and Query Gaps

**Generated:** 2026-03-17
**Last Updated:** 2026-03-17

---

## 1. Overview

The FMCSA (Federal Motor Carrier Safety Administration) workstream is the largest data pipeline in data-engine-x. It ingests **31 feeds** across **18 database tables** in the `entities` schema, covering motor carrier registrations, safety scores, crash records, inspections, insurance, operating authority, and more.

**Current state:** All P1 and P2 query endpoints are **live in production** as of 2026-03-17. The FMCSA data is now queryable, filterable, exportable, and ready for frontend integration and outbound campaign building. Three P3 endpoints remain unbuilt (insurance query, authority changes query, verticals).

---

## 2. What Exists Today

### 2.1 Per-Carrier Enrichment Endpoints (Live, On-Demand)

These are real-time lookup operations that query external FMCSA APIs for a single carrier at a time. They are **not** queries against our stored data.

| Operation ID | What It Does | Input | Source |
|---|---|---|---|
| `company.enrich.fmcsa` | Carrier profile, safety scores, authority status | USDOT number | FMCSA QCMobile API |
| `company.enrich.fmcsa.company_census` | Full census record | DOT or MC number | FMCSA Socrata (az4n-8mr2) |
| `company.enrich.fmcsa.carrier_all_history` | Registration history | DOT or MC number | FMCSA Socrata (6eyk-hxee) |
| `company.enrich.fmcsa.revocation_all_history` | Revocation history | DOT or MC number | FMCSA Socrata (sa6p-acbp) |
| `company.enrich.fmcsa.insur_all_history` | Insurance history | MC number | FMCSA Socrata (ypjt-5ydn) |
| `company.search.fmcsa` | Name-based carrier search | Carrier name | FMCSA QCMobile API |

**Path:** `POST /api/v1/execute` with the operation ID.

**Limitation:** These are one-carrier-at-a-time lookups against live FMCSA APIs. They are useful for enriching a known carrier but cannot support browsing, filtering, segmenting, or building outbound lists from our bulk data.

### 2.2 Bulk Ingest Endpoints (Internal Only)

These 16 internal endpoints receive batch rows from Trigger.dev tasks and write them to the database. They are **not accessible to tenants or frontend applications**.

| Internal Endpoint | Target Table | Data Description |
|---|---|---|
| `/api/internal/motor-carrier-census-records/upsert-batch` | `motor_carrier_census_records` | Full carrier census (name, address, fleet size, NAICS, classification) |
| `/api/internal/carrier-registrations/upsert-batch` | `carrier_registrations` | Authority status, docket/DOT mapping, BIPD/cargo insurance requirements |
| `/api/internal/carrier-safety-basic-measures/upsert-batch` | `carrier_safety_basic_measures` | SMS safety measure scores by category |
| `/api/internal/carrier-safety-basic-percentiles/upsert-batch` | `carrier_safety_basic_percentiles` | SMS percentile rankings and alert flags |
| `/api/internal/carrier-inspections/upsert-batch` | `carrier_inspections` | Inspection records |
| `/api/internal/carrier-inspection-violations/upsert-batch` | `carrier_inspection_violations` | Violation details per inspection |
| `/api/internal/commercial-vehicle-crashes/upsert-batch` | `commercial_vehicle_crashes` | Crash reports with fatalities, injuries, hazmat |
| `/api/internal/vehicle-inspection-units/upsert-batch` | `vehicle_inspection_units` | Per-vehicle inspection records |
| `/api/internal/vehicle-inspection-citations/upsert-batch` | `vehicle_inspection_citations` | Citation details per inspection |
| `/api/internal/vehicle-inspection-special-studies/upsert-batch` | `vehicle_inspection_special_studies` | Special study inspection records |
| `/api/internal/out-of-service-orders/upsert-batch` | `out_of_service_orders` | OOS order history |
| `/api/internal/operating-authority-histories/upsert-batch` | `operating_authority_histories` | Authority application/grant/denial history |
| `/api/internal/operating-authority-revocations/upsert-batch` | `operating_authority_revocations` | Authority revocation events |
| `/api/internal/insurance-policies/upsert-batch` | `insurance_policies` | Active insurance filings |
| `/api/internal/insurance-policy-filings/upsert-batch` | `insurance_policy_filings` | Filing date records |
| `/api/internal/insurance-policy-history-events/upsert-batch` | `insurance_policy_history_events` | Insurance action history |

### 2.3 Trigger.dev Ingest Tasks (Scheduled)

31 tasks run on daily/scheduled cadences to keep the 18 tables current:

**Healthy (22 feeds):** Daily diffs (8), quick-win CSV exports (6), medium feeds (4), recovered all-history feeds (3), plus one additional.

**Timing out at 12h (2 feeds):** `fmcsa-boc3-all-history`, `fmcsa-inshist-all-history` — narrow feeds with very large row counts stalling.

**Not yet validated on new path (8 feeds):** Large CSV exports (1M–13M rows each) recently migrated from old streaming parser to direct chunk POST. Awaiting validation runs.

---

## 3. Database Tables — What Data We Have

### 3.1 Motor Carrier Census Records (`motor_carrier_census_records`)

The flagship table — the full FMCSA carrier directory. This is the most valuable table for outbound targeting.

| Field | Description | Outbound Value |
|---|---|---|
| `dot_number` | USDOT number (unique carrier ID) | Primary lookup key |
| `legal_name` | Legal business name | Company targeting |
| `dba_name` | Doing-business-as name | Alternative company name |
| `carrier_operation_code` | Type of carrier operation | Segment by carrier type |
| `hazmat_flag` | Hazardous materials carrier | Target hazmat verticals |
| `passenger_carrier_flag` | Passenger carrier | Target passenger transport |
| `physical_street`, `physical_city`, `physical_state`, `physical_zip` | Physical address | Geographic targeting, local campaigns |
| `mailing_street`, `mailing_city`, `mailing_state`, `mailing_zip` | Mailing address | Direct mail campaigns |
| `telephone`, `fax`, `email_address` | Contact information | Direct outreach |
| `power_unit_count` | Number of power units (trucks) | Fleet size proxy — segment by size |
| `driver_total` | Number of drivers | Workforce size proxy |
| `mcs150_date` | Last MCS-150 filing date | Recency signal |
| `mcs150_mileage`, `mcs150_mileage_year` | Self-reported mileage | Activity level proxy |
| `private_only`, `authorized_for_hire`, `exempt_for_hire` | Classification flags (12 total) | Segment by business model |
| Feed: ~2.08M rows, 42 columns | | |

### 3.2 Carrier Safety Measures & Percentiles (`carrier_safety_basic_measures`, `carrier_safety_basic_percentiles`)

SMS (Safety Measurement System) scores for each carrier across 5 safety categories.

| Field | Description | Outbound Value |
|---|---|---|
| `dot_number` | Carrier DOT number | Join key to census |
| `carrier_segment` | Carrier category | Segmentation |
| `inspection_total`, `driver_inspection_total`, `vehicle_inspection_total` | Inspection counts | Activity/compliance level |
| `unsafe_driving_measure`, `unsafe_driving_percentile` | Unsafe driving score | Safety risk indicator |
| `hours_of_service_measure`, `hours_of_service_percentile` | HOS compliance score | Compliance risk |
| `driver_fitness_measure`, `driver_fitness_percentile` | Driver fitness score | Driver quality signal |
| `controlled_substances_alcohol_measure`, `controlled_substances_alcohol_percentile` | Drug/alcohol score | Compliance risk |
| `vehicle_maintenance_measure`, `vehicle_maintenance_percentile` | Vehicle maintenance score | Fleet maintenance signal |
| `*_alert_roadside`, `*_alert_acute_critical`, `*_alert_basic` | Alert flags per category | Active intervention signals |
| Feed: varies by segment | | |

### 3.3 Commercial Vehicle Crashes (`commercial_vehicle_crashes`)

Crash reports with severity data.

| Field | Description | Outbound Value |
|---|---|---|
| `crash_id` | Unique crash ID | Record key |
| `dot_number`, `docket_number` | Carrier identifiers | Join to census |
| `report_date` | Date of crash | Recency filtering |
| `location`, `city`, `state`, `county` | Crash location | Geographic analysis |
| `fatalities`, `injuries`, `tow_away` | Severity metrics | Risk scoring |
| `hazmat_released` | Hazmat involvement | Compliance signal |
| `truck_bus_indicator` | Vehicle type | Segmentation |
| Feed: ~4.9M rows, 59 columns | | |

### 3.4 Carrier Registrations (`carrier_registrations`)

Authority status and registration details. Connects DOT numbers to MC/docket numbers.

| Field | Description | Outbound Value |
|---|---|---|
| `docket_number`, `usdot_number` | Dual identifiers | Cross-reference key |
| `common_authority_status`, `contract_authority_status`, `broker_authority_status` | Authority types held | Segment by authority type |
| `pending_*_authority` | Pending applications | New entrant signal |
| `*_revocation` | Revoked authorities | Compliance risk |
| `bipd_required_thousands_usd`, `cargo_required`, `bond_surety_required` | Insurance requirements | Compliance level |
| `bipd_on_file_thousands_usd`, `cargo_on_file`, `bond_surety_on_file` | Insurance on file | Coverage status |
| `legal_name`, `dba_name` | Names | Alternative to census names |
| `business_address_*`, `mailing_address_*` | Addresses | Alternative to census addresses |
| Feed: varies | | |

### 3.5 Insurance Tables (`insurance_policies`, `insurance_policy_filings`, `insurance_policy_history_events`)

Insurance filing and coverage data by docket number.

| Field | Description | Outbound Value |
|---|---|---|
| `docket_number` | Carrier docket | Join key |
| `insurance_type_code`, `insurance_type_description` | Coverage type | Insurance vertical targeting |
| `bipd_maximum_dollar_limit_thousands_usd` | Coverage limit | Size proxy |
| `policy_number`, `effective_date` | Policy details | Recency signal |
| `insurance_company_name` | Insurer | Insurance market intelligence |
| `is_removal_signal`, `removal_signal_reason` | Coverage lapse | Compliance risk |

### 3.6 Operating Authority (`operating_authority_histories`, `operating_authority_revocations`)

Authority application, grant, denial, and revocation history.

| Field | Description | Outbound Value |
|---|---|---|
| `docket_number`, `usdot_number` | Carrier identifiers | Join key |
| `operating_authority_type` | Type of authority | Segment by authority |
| `original_authority_action_description` | Application outcome | New entrant identification |
| `revocation_type`, `effective_date` | Revocation details | Compliance risk |

### 3.7 Inspection & Violation Tables (`carrier_inspections`, `carrier_inspection_violations`, `vehicle_inspection_units`, `vehicle_inspection_citations`, `vehicle_inspection_special_studies`)

Detailed inspection and violation records.

### 3.8 Out of Service Orders (`out_of_service_orders`)

Carriers placed out of service.

---

## 4. FMCSA Query Endpoints — Live

All P1 and P2 query endpoints shipped 2026-03-17. Registered on the router at `POST /api/v1/fmcsa-*` via `app/routers/fmcsa_v1.py`. Auth: both tenant JWT and super-admin tokens via `_resolve_flexible_auth`.

### 4.1 Carrier Directory Query (P1 — Live)

**`POST /api/v1/fmcsa-carriers/query`**

Queries `motor_carrier_census_records` (latest snapshot via CTE). Returns paginated carrier list with `total_matched` count.

**Service:** `app/services/fmcsa_carrier_query.py` → `query_fmcsa_carriers()`

**Request model:** `FmcsaCarrierQueryRequest`

| Filter | Type | Description |
|---|---|---|
| `state` | string | 2-letter state code (matches `physical_state`) |
| `min_power_units` / `max_power_units` | int | Fleet size range |
| `min_drivers` / `max_drivers` | int | Workforce size range |
| `carrier_operation` | string | Operation type code |
| `authorized_for_hire` | bool | For-hire classification |
| `private_only` | bool | Private carrier classification |
| `exempt_for_hire` | bool | Exempt for-hire classification |
| `private_property` | bool | Private property classification |
| `hazmat_flag` | bool | Hazmat carrier flag |
| `passenger_carrier_flag` | bool | Passenger carrier flag |
| `mcs150_date_from` / `mcs150_date_to` | string | MCS-150 filing date range |
| `legal_name_contains` | string | Partial name search (ILIKE) |
| `dot_number` | string | Exact DOT number lookup |
| `limit` | int | 1–500, default 25 |
| `offset` | int | Default 0 |

**Response:** `DataEnvelope` with `{ items, total_matched, limit, offset }`

**Returns 25 columns** from `CENSUS_CURATED_COLUMNS` (dot_number, legal_name, dba_name, carrier_operation_code, physical address, telephone, email_address, power_unit_count, driver_total, mcs150_date, mcs150_mileage, classification flags, fleet_size_code, safety_rating_code, feed_date).

### 4.2 Carrier Detail (P1 — Live)

**`GET /api/v1/fmcsa-carriers/{dot_number}`**

Multi-table deep dive for a single carrier. Joins across 6 tables in separate queries.

**Service:** `app/services/fmcsa_carrier_detail.py` → `get_fmcsa_carrier_detail()`

**Sections returned:**
- `census` — Full census record (curated + detail extra columns)
- `safety` — Safety percentiles and alert flags from `carrier_safety_basic_percentiles`
- `authority` — Registration/authority status from `carrier_registrations`
- `crashes` — Recent crashes from `commercial_vehicle_crashes` (most recent 10)
- `insurance` — Active insurance filings from `insurance_policies` (queried by docket number via carrier_registrations mapping; no feed_date CTE since this table lacks feed_date)
- `out_of_service` — OOS orders from `out_of_service_orders` (most recent 10)

Returns 404 if DOT number not found.

### 4.3 Carrier Stats (P1 — Live)

**`POST /api/v1/fmcsa-carriers/stats`**

Dashboard aggregates from latest census snapshot + safety percentiles.

**Service:** `app/services/fmcsa_carrier_stats.py` → `get_fmcsa_carrier_stats()`

**Returns:**
- `total_carriers` — Total carrier count
- `by_state` — Top 20 states by carrier count
- `by_fleet_size` — 4 buckets: 1–5, 6–25, 26–100, 101+
- `by_classification` — authorized_for_hire, private_only, exempt_for_hire, private_property counts
- `hazmat_carriers` / `passenger_carriers` — Flag counts
- `safety_alerts` — 5 categories: unsafe_driving, hours_of_service, driver_fitness, controlled_substances_alcohol, vehicle_maintenance

### 4.4 Safety Risk Search (P2 — Live)

**`POST /api/v1/fmcsa-carriers/safety-risk`**

3-way join: latest census INNER JOIN latest safety percentiles, LEFT JOIN trailing 12-month crash counts.

**Service:** `app/services/fmcsa_safety_risk.py` → `query_fmcsa_safety_risk()`

**Request model:** `FmcsaSafetyRiskQueryRequest`

| Filter | Type | Description |
|---|---|---|
| `state` | string | 2-letter state code |
| `min_power_units` | int | Minimum fleet size |
| `min_unsafe_driving_percentile` | int | Unsafe driving threshold |
| `min_hos_percentile` | int | Hours of service threshold |
| `min_vehicle_maintenance_percentile` | int | Vehicle maintenance threshold |
| `min_driver_fitness_percentile` | int | Driver fitness threshold |
| `min_controlled_substances_percentile` | int | Controlled substances threshold |
| `has_alert_unsafe_driving` | bool | Active unsafe driving alert |
| `has_alert_hos` | bool | Active HOS alert |
| `has_alert_vehicle_maintenance` | bool | Active vehicle maintenance alert |
| `has_alert_driver_fitness` | bool | Active driver fitness alert |
| `has_alert_controlled_substances` | bool | Active controlled substances alert |
| `min_crash_count_12mo` | int | Min crashes in trailing 12 months |
| `limit` / `offset` | int | Pagination |

**Response:** Each row includes census fields, all 5 safety percentiles + alert flags, and `crash_count_12mo`.

### 4.5 Crash History Query (P2 — Live)

**`POST /api/v1/fmcsa-crashes/query`**

Queries `commercial_vehicle_crashes` (latest snapshot via CTE).

**Service:** `app/services/fmcsa_crash_query.py` → `query_fmcsa_crashes()`

**Request model:** `FmcsaCrashQueryRequest`

| Filter | Type | Description |
|---|---|---|
| `dot_number` | string | Crashes for a specific carrier |
| `state` | string | Crash location state |
| `report_date_from` / `report_date_to` | string | Date range |
| `min_fatalities` | int | Severity filter |
| `min_injuries` | int | Severity filter |
| `hazmat_released` | bool | Hazmat involvement |
| `limit` / `offset` | int | Pagination |

**Returns 18 columns:** crash_id, dot_number, report_date, state, city, location, fatalities, injuries, tow_away, hazmat_released, truck_bus_indicator, crash_carrier_name, crash_carrier_state, vehicles_in_accident, weather/light/road_surface condition IDs, feed_date.

### 4.6 Carrier CSV Export (P2 — Live)

**`POST /api/v1/fmcsa-carriers/export`**

Streaming CSV export via server-side cursor. Joins census + safety percentiles. Supports both census and safety filters.

**Service:** `app/services/fmcsa_carrier_export.py` → `stream_fmcsa_carriers_csv()`

**Request model:** `FmcsaCarrierExportRequest` — all 16 census filters from the query endpoint, plus 6 safety filters:

| Safety Filter | Type | Description |
|---|---|---|
| `min_unsafe_driving_percentile` | int | Unsafe driving threshold |
| `min_hours_of_service_percentile` | int | HOS threshold |
| `min_vehicle_maintenance_percentile` | int | Vehicle maintenance threshold |
| `has_alert_unsafe_driving` | bool | Active unsafe driving alert |
| `has_alert_vehicle_maintenance` | bool | Active vehicle maintenance alert |
| `has_alert_driver_fitness` | bool | Active driver fitness alert |

**Behavior:**
- Pre-counts result set; returns HTTP 422 if >100,000 rows (add filters to narrow)
- Streams CSV with 25 census columns + 10 safety columns (percentiles + alert flags)
- Server-side cursor with `itersize=5000`

**Architecture notes:**
- Filter helpers `_build_carrier_where()` and `_build_safety_where()` in `fmcsa_carrier_query.py` accept an optional `table_alias` parameter. The export service passes `table_alias="census"` and `table_alias="safety"` matching its JOIN aliases.
- Callers without joins (e.g. the basic carrier query) pass no alias and get unqualified column names.

---

## 5. Remaining Query Endpoints (Not Yet Built)

### 5.1 Insurance Coverage Query

**`POST /api/v1/fmcsa-insurance/query`**

Query `insurance_policies` by docket number or coverage status.

Filter parameters:
- `docket_number` — specific carrier
- `insurance_type_code` — coverage type
- `is_removal_signal` — carriers with lapsed coverage (hot leads for insurance brokers)
- `min_bipd_limit` / `max_bipd_limit` — coverage amount range
- `limit` / `offset`

**Why:** Insurance lapse data is extremely valuable for insurance broker outbound, but requires docket-to-DOT mapping which adds complexity.

### 5.2 Authority Changes Query

**`POST /api/v1/fmcsa-authority/query`**

Query `operating_authority_histories` and `operating_authority_revocations`.

Filter parameters:
- `usdot_number` or `docket_number`
- `authority_type` — common, contract, broker
- `action_date_from` / `action_date_to` — recent authority grants = new market entrants
- `action_type` — granted, denied, revoked
- `limit` / `offset`

**Why:** New authority grants identify brand-new carriers entering the market. These are excellent leads for insurance, compliance software, and fleet management companies — they need everything and are actively buying.

### 5.3 Verticals / Industry Summary

**`GET /api/v1/fmcsa-carriers/verticals`**

Pre-computed breakdown by carrier classification and operation type:
- For-hire carriers by state and fleet size
- Hazmat carriers by state
- Passenger carriers by state
- Private carriers by state and fleet size

**Why:** Enables a frontend "Explore Verticals" view similar to the federal contract leads verticals endpoint.

---

## 6. Outbound Campaign Use Cases Unlocked by These Endpoints

### Use Case 1: Safety/Compliance Software Vendor

**Query:** "Carriers in the Southeast with 15+ trucks that have active unsafe driving or vehicle maintenance alerts"

**Endpoints needed:** `/fmcsa-carriers/safety-risk` with state filter, min_power_units=15, has_alert_unsafe_driving=true OR has_alert_vehicle_maintenance=true

**Personalization data points:**
- "Your fleet of {power_unit_count} trucks currently has an unsafe driving alert at the {unsafe_driving_percentile}th percentile"
- "In the last 12 months, {crash_count} reportable crashes were recorded under DOT #{dot_number}"
- "{driver_total} drivers across your fleet"

### Use Case 2: Insurance Broker Targeting Under-Insured Carriers

**Query:** "Carriers with active authority but insurance removal signals or below-minimum BIPD coverage"

**Endpoints needed:** `/fmcsa-insurance/query` with is_removal_signal=true, cross-referenced with `/fmcsa-carriers/query`

**Personalization data points:**
- "We noticed a coverage gap flagged on docket {docket_number} effective {effective_date}"
- "Your current BIPD filing of ${bipd_on_file}K is below the ${bipd_required}K requirement"

### Use Case 3: Fleet Management / ELD Provider

**Query:** "Carriers with 5-50 trucks, authorized for hire, in specific states"

**Endpoints needed:** `/fmcsa-carriers/query` with min_power_units=5, max_power_units=50, classification=authorized_for_hire, state=TX

**Personalization data points:**
- "Managing {power_unit_count} trucks and {driver_total} drivers"
- "Based at {physical_street}, {physical_city}, {physical_state}"
- "Hours of service compliance at {hours_of_service_percentile}th percentile"

### Use Case 4: New Carrier Welcome Campaign

**Query:** "Carriers that received new operating authority in the last 90 days"

**Endpoints needed:** `/fmcsa-authority/query` with action_type=granted, action_date_from=90 days ago

**Personalization data points:**
- "Congratulations on your new {authority_type} operating authority granted {action_date}"
- "As a new carrier, you'll need {requirements_list} — we can help"

### Use Case 5: Geographic Fleet Demo Dashboard

**Query:** "All carriers in a state, grouped by fleet size"

**Endpoints needed:** `/fmcsa-carriers/stats` filtered by state, then `/fmcsa-carriers/query` for drill-down

**Frontend display:** Map view with carrier density, fleet size distribution chart, safety score heatmap.

---

## 7. Implementation Status Summary

| Status | Endpoint | Tables Involved | Outbound Value |
|---|---|---|---|
| **Live** | `POST /fmcsa-carriers/query` | motor_carrier_census_records | Core carrier directory search — enables all segmentation |
| **Live** | `GET /fmcsa-carriers/{dot_number}` | census + safety + registrations + crashes + insurance + OOS | Carrier detail view — powers personalization |
| **Live** | `POST /fmcsa-carriers/stats` | motor_carrier_census_records + safety percentiles | Dashboard aggregates — proves data value |
| **Live** | `POST /fmcsa-carriers/safety-risk` | census + percentiles + crashes (3-way join) | Safety-risk targeting — highest-value outbound query |
| **Live** | `POST /fmcsa-crashes/query` | commercial_vehicle_crashes | Crash history — most compelling outbound data point |
| **Live** | `POST /fmcsa-carriers/export` | census + safety percentiles (LEFT JOIN, streaming CSV) | CSV export for campaign platforms |
| **Not built** | `POST /fmcsa-insurance/query` | insurance_policies | Insurance gap targeting |
| **Not built** | `POST /fmcsa-authority/query` | operating_authority_histories + revocations | New entrant identification |
| **Not built** | `GET /fmcsa-carriers/verticals` | census (pre-computed) | Vertical exploration view |

---

## 8. Technical Notes

### Data Freshness

All FMCSA tables use a `feed_date` column that records when each daily snapshot was ingested. The 22 healthy feeds update daily. The 8 large CSV export feeds (including the census at 2.08M rows) are migrated to the new streaming path but not yet validated — once confirmed, they'll also update daily.

### Join Strategy

The `dot_number` field is the primary join key across census, safety, and crash tables. Insurance and authority tables use `docket_number` — the `carrier_registrations` table provides the docket-to-DOT mapping via both `docket_number` and `usdot_number` columns.

### Query Performance

All tables have indexes on the key lookup fields (`dot_number`, `docket_number`, `feed_date`). The recommended query endpoints should filter to the latest `feed_date` snapshot (latest available per `source_feed_name`) to avoid returning historical duplicates. A common pattern: `WHERE feed_date = (SELECT MAX(feed_date) FROM table WHERE source_feed_name = 'X')`.

### Implementation Pattern

The FMCSA query endpoints follow the same architectural pattern as federal contract leads (`app/services/federal_leads_query.py`, `federal_leads_export.py`, etc.): direct Postgres queries via `psycopg` connection pool against the `entities` schema, parameterized SQL with `%s` placeholders, `COUNT(*) OVER()` window function for pagination totals, and server-side cursors for CSV streaming.

**Key implementation files:**
- `app/routers/fmcsa_v1.py` — Router with 6 endpoints and request models
- `app/services/fmcsa_carrier_query.py` — Core query + shared filter helpers (`_build_carrier_where`, `_build_safety_where`, `_col`, `_conditions_to_where`)
- `app/services/fmcsa_carrier_detail.py` — Multi-table carrier detail
- `app/services/fmcsa_carrier_stats.py` — Dashboard aggregates
- `app/services/fmcsa_safety_risk.py` — 3-way join safety risk query
- `app/services/fmcsa_crash_query.py` — Crash history query
- `app/services/fmcsa_carrier_export.py` — Streaming CSV export
- `tests/test_fmcsa_query_endpoints.py` — 55 tests covering all endpoints and filter helpers
