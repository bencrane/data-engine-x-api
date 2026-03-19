# Executor Directive: FMCSA Carrier Query Endpoints

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA pipeline ingests 31 feeds into 18 tables in the `entities` schema — millions of rows of carrier, safety, crash, insurance, and authority data. Zero query endpoints exist today. The data is completely inaccessible from the API. This directive builds the read layer: 6 endpoints that unlock FMCSA carrier data for frontend applications and outbound campaign builders.

All 6 endpoints are read-only — no writes, no ingestion, no data mutation.

---

## Reference Documents (Read Before Starting)

**Must read — existing query code (your primary pattern reference):**
- `app/services/federal_leads_query.py` — Connection pool singleton, parameterized filter building with `%s` placeholders, `COUNT(*) OVER()` pagination, `dict_row` cursor
- `app/services/federal_leads_export.py` — CSV streaming with server-side cursor, `max_rows` safety check, `_build_where()` helper
- `app/services/federal_leads_company_detail.py` — Multi-table detail view, separate queries per table aggregated in Python
- `app/services/federal_leads_verticals.py` — Aggregate stats with CTE, `NULLIF` divide-by-zero safety, Decimal-to-float coercion
- `app/routers/entities_v1.py` — Endpoint registration, `_resolve_flexible_auth` dependency, `DataEnvelope` response wrapper, request model pattern, `StreamingResponse` for CSV export

**Must read — FMCSA table schemas:**
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql`
- `supabase/migrations/023_fmcsa_next_batch_snapshot_history_tables.sql`
- `supabase/migrations/024_fmcsa_sms_feed_tables.sql`
- `supabase/migrations/025_fmcsa_remaining_csv_export_tables.sql`

**Must read — project conventions:**
- `CLAUDE.md`
- `docs/ENTITY_DATABASE_DESIGN_PRINCIPLES.md`

---

## Critical Technical Constraints

### 1. Latest-Snapshot Filtering

FMCSA tables store daily snapshots identified by `feed_date`. Every query must filter to the **latest `feed_date`** to avoid returning historical duplicates. Multiple feeds may write to the same table (e.g., `motor_carrier_census_records` receives data from both "SMS Input - Motor Carrier Census" and "Company Census File"). Within the latest `feed_date`, use `DISTINCT ON (dot_number)` to return one row per carrier.

The standard pattern is a CTE:
```
WITH latest AS (
  SELECT DISTINCT ON (dot_number) *
  FROM entities.{table}
  WHERE feed_date = (SELECT MAX(feed_date) FROM entities.{table})
  ORDER BY dot_number, row_position
)
```

**Exception:** `insurance_policies` (migration 022) does NOT have a `feed_date` column. It uses `record_fingerprint` as its unique key and `last_observed_at` for recency. Query it directly — no feed_date CTE needed.

### 2. Schema Qualification

All FMCSA tables live in the `entities` schema. Every SQL query must use `entities.{table_name}`. Never use bare table names.

### 3. Global Public Data — No Org Scoping

FMCSA is global public data, not tenant-scoped enrichment output. These endpoints do NOT filter by `org_id`. Every authenticated user sees the same FMCSA data.

### 4. Auth

Use the existing `_resolve_flexible_auth` dependency from `app/routers/entities_v1.py`. This accepts both tenant JWT and super-admin auth. Do not use `require_org_admin` or `get_current_auth` with org scoping — these are read-only public data queries.

### 5. Join Keys

- `dot_number` is the primary join key across census, safety, and crash tables.
- Insurance and authority tables use `docket_number`. The `carrier_registrations` table provides the docket-to-DOT mapping via both `docket_number` and `usdot_number` columns.

---

## File Structure

Create these new files:

| File | Purpose |
|---|---|
| `app/services/fmcsa_carrier_query.py` | Carrier directory query + shared connection pool |
| `app/services/fmcsa_carrier_detail.py` | Single-carrier multi-table detail view |
| `app/services/fmcsa_carrier_stats.py` | Dashboard aggregate stats |
| `app/services/fmcsa_safety_risk.py` | Safety-risk carrier search |
| `app/services/fmcsa_crash_query.py` | Crash history query |
| `app/services/fmcsa_carrier_export.py` | CSV export with streaming |
| `app/routers/fmcsa_v1.py` | All 6 FMCSA endpoints |
| `tests/test_fmcsa_query_endpoints.py` | Tests for all services and endpoints |

Register the new router in `app/main.py` alongside the existing entity routers:
```
app.include_router(fmcsa_v1.fmcsa_router, prefix="/api/v1", tags=["fmcsa-v1"])
```

---

## Deliverable 1: Carrier Directory Query

Create `app/services/fmcsa_carrier_query.py`.

**`query_fmcsa_carriers(*, filters: dict[str, Any], limit: int = 25, offset: int = 0) -> dict[str, Any]`**

Follow `federal_leads_query.py` exactly:
- Module-level connection pool singleton with threading lock (`psycopg_pool.ConnectionPool`, `min_size=1, max_size=4`)
- Settings from `app.config.get_settings()`
- `dict_row` cursor factory
- `COUNT(*) OVER() AS total_matched` window function
- Safe clamp: `limit` to `[1, 500]`, `offset` to `[0, ∞)`
- All filter values parameterized via `%s` — never string interpolation

**Source table:** `entities.motor_carrier_census_records`

**Latest-snapshot CTE required.** Filter to `feed_date = (SELECT MAX(feed_date) FROM entities.motor_carrier_census_records)`, then `DISTINCT ON (dot_number)` to deduplicate.

**Supported filters:**

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `state` | `str` | `physical_state = %s` (2-letter code) |
| `min_power_units` | `int` | `power_unit_count >= %s` |
| `max_power_units` | `int` | `power_unit_count <= %s` |
| `carrier_operation` | `str` | `carrier_operation_code = %s` |
| `authorized_for_hire` | `bool` | `authorized_for_hire = TRUE` (append only when filter is `True`) |
| `private_only` | `bool` | `private_only = TRUE` |
| `exempt_for_hire` | `bool` | `exempt_for_hire = TRUE` |
| `private_property` | `bool` | `private_property = TRUE` |
| `hazmat_flag` | `bool` | `hazmat_flag = TRUE` |
| `passenger_carrier_flag` | `bool` | `passenger_carrier_flag = TRUE` |
| `mcs150_date_from` | `str` | `mcs150_date >= %s::DATE` |
| `mcs150_date_to` | `str` | `mcs150_date <= %s::DATE` |
| `legal_name_contains` | `str` | `legal_name ILIKE %s` with `%{value}%` |
| `dot_number` | `str` | `dot_number = %s` (exact match) |
| `min_drivers` | `int` | `driver_total >= %s` |
| `max_drivers` | `int` | `driver_total <= %s` |

**Default ordering:** `ORDER BY power_unit_count DESC NULLS LAST, dot_number`

**Return columns:** Return a curated subset, not all 100+ columns. Include: `dot_number`, `legal_name`, `dba_name`, `carrier_operation_code`, `physical_street`, `physical_city`, `physical_state`, `physical_zip`, `telephone`, `email_address`, `power_unit_count`, `driver_total`, `mcs150_date`, `mcs150_mileage`, `mcs150_mileage_year`, `hazmat_flag`, `passenger_carrier_flag`, `authorized_for_hire`, `private_only`, `exempt_for_hire`, `private_property`, `fleet_size_code`, `safety_rating_code`, `safety_rating_date`, `feed_date`.

**Response shape:**
```
{
    "items": [...],
    "total_matched": int,
    "limit": int,
    "offset": int
}
```

Create `app/routers/fmcsa_v1.py` with the router and this first endpoint:

**`POST /api/v1/fmcsa-carriers/query`**

Auth: `_resolve_flexible_auth` (import from `app.routers.entities_v1` or duplicate the helper — use your judgment on which is cleaner).

Request model: `FmcsaCarrierQueryRequest(BaseModel)` with all filter fields as optional + `limit: int = Field(default=25, ge=1, le=500)` + `offset: int = Field(default=0, ge=0)`.

Response: `DataEnvelope(data=results)`.

Register the router in `app/main.py`.

Commit standalone.

---

## Deliverable 2: Carrier Detail

Create `app/services/fmcsa_carrier_detail.py`.

**`get_fmcsa_carrier_detail(*, dot_number: str) -> dict[str, Any] | None`**

Builds a complete carrier profile by querying multiple tables. Follow the `federal_leads_company_detail.py` pattern: separate queries per table, aggregated in Python — no multi-table SQL joins.

Use its own connection pool (`min_size=1, max_size=3`).

**Sections to build:**

1. **Census record** — Query `entities.motor_carrier_census_records` for the latest snapshot where `dot_number` matches. Return the curated column set from Deliverable 1 plus additional fields: `fax`, `mailing_street`, `mailing_city`, `mailing_state`, `mailing_zip`, `company_officer_1`, `company_officer_2`, `add_date`, `recent_mileage`, `recent_mileage_year`. If no census match, return `None` (404 at endpoint level).

2. **Safety percentiles** — Query `entities.carrier_safety_basic_percentiles` for the latest snapshot where `dot_number` matches. Return all 5 BASIC category percentiles, measures, and alert flags: `unsafe_driving_percentile`, `unsafe_driving_measure`, `unsafe_driving_roadside_alert`, `unsafe_driving_acute_critical`, `unsafe_driving_basic_alert` (and the same 5 fields for `hours_of_service`, `driver_fitness`, `controlled_substances_alcohol`, `vehicle_maintenance`). Also include `inspection_total`, `driver_inspection_total`, `vehicle_inspection_total`, `carrier_segment`. If no safety data, this section is `null`.

3. **Authority status** — Query `entities.carrier_registrations` for the latest snapshot where `usdot_number` matches. Return: `docket_number`, `common_authority_status`, `contract_authority_status`, `broker_authority_status`, `pending_common_authority`, `pending_contract_authority`, `pending_broker_authority`, `bipd_required_thousands_usd`, `bipd_on_file_thousands_usd`, `cargo_required`, `cargo_on_file`. If no match, this section is `null`. **Save the `docket_number` for the insurance lookup below.**

4. **Recent crashes** — Query `entities.commercial_vehicle_crashes` for the latest snapshot where `dot_number` matches. Return: `total_crashes` (count), `most_recent_crash_date` (max `report_date`), `total_fatalities` (sum), `total_injuries` (sum), and the 5 most recent crash records with: `crash_id`, `report_date`, `state`, `city`, `fatalities`, `injuries`, `tow_away`, `hazmat_released`. If no crashes, return `{ total_crashes: 0, records: [] }`.

5. **Insurance status** — If a `docket_number` was found in step 3, query `entities.insurance_policies` where `docket_number` matches. This table has NO `feed_date` — query directly. Return the list of active policies: `insurance_type_code`, `insurance_type_description`, `bipd_maximum_dollar_limit_thousands_usd`, `policy_number`, `effective_date`, `insurance_company_name`, `is_removal_signal`. If no docket_number or no policies, this section is an empty list.

6. **Out-of-service orders** — Query `entities.out_of_service_orders` for the latest snapshot where `dot_number` matches. Return: `total_oos_orders` (count), and the list with: `oos_date`, `oos_reason`, `status`, `oos_rescind_date`. If none, return `{ total_oos_orders: 0, orders: [] }`.

**Response shape:**
```
{
    "dot_number": str,
    "census": { ... },
    "safety": { ... } | null,
    "authority": { ... } | null,
    "crashes": { "total_crashes": int, "total_fatalities": int, "total_injuries": int, "most_recent_crash_date": str | null, "records": [...] },
    "insurance": [...],
    "out_of_service": { "total_oos_orders": int, "orders": [...] }
}
```

Wire endpoint in `app/routers/fmcsa_v1.py`:

**`GET /api/v1/fmcsa-carriers/{dot_number}`**

Auth: `_resolve_flexible_auth`.

Path parameter: `dot_number` (string).

Response: `DataEnvelope(data=result)`. Return 404 if `dot_number` not found in census.

**Note on routing:** Register this endpoint AFTER any `/fmcsa-carriers/...` POST endpoints in the file so the path parameter doesn't shadow named routes. The GET method already distinguishes it from POST endpoints, but keep it last among carrier routes for clarity.

Commit standalone.

---

## Deliverable 3: Carrier Stats

Create `app/services/fmcsa_carrier_stats.py`.

**`get_fmcsa_carrier_stats() -> dict[str, Any]`**

Dashboard-level aggregates over the latest census snapshot. Single SQL query with multiple aggregate expressions.

Use its own connection pool (`min_size=1, max_size=2`).

**Source table:** `entities.motor_carrier_census_records` with latest-snapshot CTE, deduped by `dot_number`.

**Stats to compute (all from the same query or a small set of queries):**

| Stat | Description |
|---|---|
| `total_carriers` | `COUNT(*)` |
| `latest_feed_date` | The `feed_date` value used (data freshness indicator) |
| `by_state` | Top 20 states by carrier count: `[{ "state": str, "count": int }]` — `GROUP BY physical_state ORDER BY count DESC LIMIT 20` |
| `by_fleet_size` | Carrier count per bucket: `1-5`, `6-25`, `26-100`, `101+` — use `CASE WHEN` on `power_unit_count` |
| `by_classification` | Carrier count for each classification flag: `authorized_for_hire`, `private_only`, `exempt_for_hire`, `private_property` — `COUNT(*) FILTER (WHERE flag = TRUE)` for each |
| `hazmat_carriers` | `COUNT(*) FILTER (WHERE hazmat_flag = TRUE)` |
| `passenger_carriers` | `COUNT(*) FILTER (WHERE passenger_carrier_flag = TRUE)` |

**Safety alert counts** — requires a second query joining to the latest `entities.carrier_safety_basic_percentiles` snapshot:

| Stat | Description |
|---|---|
| `carriers_with_unsafe_driving_alert` | `COUNT(*) FILTER (WHERE unsafe_driving_basic_alert = TRUE)` |
| `carriers_with_hos_alert` | `COUNT(*) FILTER (WHERE hours_of_service_basic_alert = TRUE)` |
| `carriers_with_vehicle_maintenance_alert` | `COUNT(*) FILTER (WHERE vehicle_maintenance_basic_alert = TRUE)` |
| `carriers_with_driver_fitness_alert` | `COUNT(*) FILTER (WHERE driver_fitness_basic_alert = TRUE)` |
| `carriers_with_controlled_substances_alert` | `COUNT(*) FILTER (WHERE controlled_substances_alcohol_basic_alert = TRUE)` |

Use Decimal-to-float coercion where needed. Null-safe with `COALESCE` or Python fallbacks.

Wire endpoint in `app/routers/fmcsa_v1.py`:

**`POST /api/v1/fmcsa-carriers/stats`**

Auth: `_resolve_flexible_auth`.

No request body (or empty body accepted).

Response: `DataEnvelope(data=stats)`.

Commit standalone.

---

## Deliverable 4: Safety Risk Search

Create `app/services/fmcsa_safety_risk.py`.

**`query_fmcsa_safety_risk(*, filters: dict[str, Any], limit: int = 25, offset: int = 0) -> dict[str, Any]`**

Joins census with safety percentiles and crash counts. This is the highest-value outbound query — "show me Texas carriers with 20+ trucks that have active unsafe driving alerts and at least one recent crash."

Use its own connection pool (`min_size=1, max_size=4`).

**SQL approach:** Build a CTE that joins the latest `motor_carrier_census_records` snapshot with the latest `carrier_safety_basic_percentiles` snapshot on `dot_number`. Add a crash-count subquery (count of crashes from `commercial_vehicle_crashes` in the trailing 12 months per `dot_number`).

**Supported filters:**

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `state` | `str` | `census.physical_state = %s` |
| `min_power_units` | `int` | `census.power_unit_count >= %s` |
| `min_unsafe_driving_percentile` | `int` | `safety.unsafe_driving_percentile >= %s` (higher = worse) |
| `min_hos_percentile` | `int` | `safety.hours_of_service_percentile >= %s` |
| `min_vehicle_maintenance_percentile` | `int` | `safety.vehicle_maintenance_percentile >= %s` |
| `min_driver_fitness_percentile` | `int` | `safety.driver_fitness_percentile >= %s` |
| `min_controlled_substances_percentile` | `int` | `safety.controlled_substances_alcohol_percentile >= %s` |
| `has_alert_unsafe_driving` | `bool` | `safety.unsafe_driving_basic_alert = TRUE` |
| `has_alert_hos` | `bool` | `safety.hours_of_service_basic_alert = TRUE` |
| `has_alert_vehicle_maintenance` | `bool` | `safety.vehicle_maintenance_basic_alert = TRUE` |
| `has_alert_driver_fitness` | `bool` | `safety.driver_fitness_basic_alert = TRUE` |
| `has_alert_controlled_substances` | `bool` | `safety.controlled_substances_alcohol_basic_alert = TRUE` |
| `min_crash_count_12mo` | `int` | Carrier's crash count in trailing 12 months `>= %s` |

**Return columns:** Census fields (same curated set as Deliverable 1) plus safety fields: all 5 BASIC percentiles, all 5 BASIC alert flags, `inspection_total`, and `crash_count_12mo`.

**Default ordering:** `unsafe_driving_percentile DESC NULLS LAST, power_unit_count DESC NULLS LAST`

**Pagination:** Same `COUNT(*) OVER()` + `LIMIT`/`OFFSET` pattern.

**Response shape:** Same as Deliverable 1: `{ items, total_matched, limit, offset }`.

Wire endpoint in `app/routers/fmcsa_v1.py`:

**`POST /api/v1/fmcsa-carriers/safety-risk`**

Auth: `_resolve_flexible_auth`.

Request model: `FmcsaSafetyRiskQueryRequest(BaseModel)` with all filter fields as optional + `limit` + `offset`.

Response: `DataEnvelope(data=results)`.

Commit standalone.

---

## Deliverable 5: Crash History Query

Create `app/services/fmcsa_crash_query.py`.

**`query_fmcsa_crashes(*, filters: dict[str, Any], limit: int = 25, offset: int = 0) -> dict[str, Any]`**

Direct query against the crash table. Follow `federal_leads_query.py` pattern exactly.

Use its own connection pool (`min_size=1, max_size=3`).

**Source table:** `entities.commercial_vehicle_crashes` with latest-snapshot CTE.

**Supported filters:**

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `dot_number` | `str` | `dot_number = %s` (exact match) |
| `state` | `str` | `state = %s` (2-letter crash location state) |
| `report_date_from` | `str` | `report_date >= %s::DATE` |
| `report_date_to` | `str` | `report_date <= %s::DATE` |
| `min_fatalities` | `int` | `fatalities >= %s` |
| `min_injuries` | `int` | `injuries >= %s` |
| `hazmat_released` | `bool` | `hazmat_released = TRUE` |

**Return columns:** `crash_id`, `dot_number`, `report_date`, `state`, `city`, `location`, `fatalities`, `injuries`, `tow_away`, `hazmat_released`, `truck_bus_indicator`, `crash_carrier_name`, `crash_carrier_state`, `vehicles_in_accident`, `weather_condition_id`, `light_condition_id`, `road_surface_condition_id`, `feed_date`.

**Default ordering:** `report_date DESC NULLS LAST, crash_id`

**Pagination:** Same `COUNT(*) OVER()` + `LIMIT`/`OFFSET` pattern.

**Response shape:** `{ items, total_matched, limit, offset }`.

Wire endpoint in `app/routers/fmcsa_v1.py`:

**`POST /api/v1/fmcsa-crashes/query`**

Auth: `_resolve_flexible_auth`.

Request model: `FmcsaCrashQueryRequest(BaseModel)` with all filter fields as optional + `limit` + `offset`.

Response: `DataEnvelope(data=results)`.

Commit standalone.

---

## Deliverable 6: Carrier CSV Export

Create `app/services/fmcsa_carrier_export.py`.

**`stream_fmcsa_carriers_csv(*, filters: dict[str, Any], max_rows: int = 100_000) -> Iterator[str]`**

Follow `federal_leads_export.py` exactly:
- Reuse the same filter-building logic as `fmcsa_carrier_query.py` — extract a shared `_build_carrier_where(filters)` helper (either in the query module or a shared utility) to avoid duplicating WHERE clause construction
- **First pass:** Count query with same filters. Raise `ValueError` if count exceeds `max_rows`
- **Second pass:** Server-side cursor with `name="fmcsa_csv_export_cursor"`, `itersize=5000`
- Yield CSV header row first, then data rows via `csv.writer` to `StringIO`
- `fetchmany(5000)` in loop

Use its own connection pool (`min_size=1, max_size=2`).

**Source:** Same latest-snapshot CTE as Deliverable 1.

**Export columns:** The curated census column set from Deliverable 1, plus (if available via a LEFT JOIN to `carrier_safety_basic_percentiles` latest snapshot on `dot_number`): the 5 BASIC percentiles and 5 BASIC alert flags. Total ~35 columns in the CSV.

Wire endpoint in `app/routers/fmcsa_v1.py`:

**`POST /api/v1/fmcsa-carriers/export`**

Auth: `_resolve_flexible_auth`.

Request model: Reuse `FmcsaCarrierQueryRequest` from Deliverable 1. Ignore `limit` and `offset` fields — export returns all matches.

Response: `StreamingResponse` with `media_type="text/csv"` and `Content-Disposition: attachment; filename=fmcsa_carriers_export.csv`.

**Safety pattern:** Eagerly trigger the count check by calling `next()` on the generator before wrapping in `StreamingResponse`. Catch `ValueError` and return 422 with the message. Follow the exact pattern from the federal leads export endpoint in `entities_v1.py`.

Commit standalone.

---

## Deliverable 7: Tests

Create `tests/test_fmcsa_query_endpoints.py`.

All tests mock database calls. Use `pytest`. Do not hit real databases or APIs.

**1. Carrier query service tests:**
- Default query returns paginated envelope with `items`, `total_matched`, `limit`, `offset`
- `state` filter generates exact match condition
- `min_power_units` / `max_power_units` generate range conditions
- Boolean filters (`hazmat_flag`, `authorized_for_hire`, etc.) only append when `True`
- `legal_name_contains` generates ILIKE with wildcards
- `dot_number` generates exact match
- `mcs150_date_from` / `mcs150_date_to` cast to DATE
- Multiple filters combine with AND
- Pagination safe-clamping works (limit > 500 → 500, offset < 0 → 0)

**2. Carrier detail tests:**
- Returns all 6 sections (census, safety, authority, crashes, insurance, out_of_service)
- Returns 404 when dot_number not found in census
- Handles missing safety data (section is `null`)
- Handles missing authority data (section is `null`, insurance is empty)
- Handles zero crashes (returns `{ total_crashes: 0, records: [] }`)
- Handles zero OOS orders

**3. Carrier stats tests:**
- Returns all expected stat keys
- `by_state` is a list of `{ state, count }` dicts, max 20
- `by_fleet_size` has 4 buckets
- `by_classification` has counts for each flag
- Safety alert counts are non-negative integers

**4. Safety risk tests:**
- Joins census + safety + crash count correctly
- Percentile filters use `>=` comparison
- Boolean alert filters only fire when `True`
- `min_crash_count_12mo` filters on trailing 12-month window
- Pagination works

**5. Crash query tests:**
- `dot_number` filter generates exact match
- Date range filters cast to DATE
- `min_fatalities` / `min_injuries` generate `>=` conditions
- `hazmat_released` only appends when `True`
- Pagination works

**6. CSV export tests:**
- Returns iterator of CSV lines
- First line is header row with expected column count
- Filters are applied (same WHERE as carrier query)
- `max_rows` check raises `ValueError` when exceeded

**7. Endpoint/router tests:**
- All 6 endpoints return correct response shapes via `DataEnvelope`
- Auth required on all endpoints (401 without token)
- CSV export returns `text/csv` content type with Content-Disposition header
- GET `/{dot_number}` accepts path parameter and returns 404 for unknown DOT
- POST endpoints accept their respective request models

Commit standalone.

---

## What is NOT in scope

- **No data ingestion.** These are read-only query endpoints.
- **No schema migrations.** All tables already exist.
- **No Trigger.dev tasks.**
- **No deploy commands.** Do not push.
- **No modifications to existing endpoints.** The existing entity query endpoints in `entities_v1.py` stay as-is.
- **No insurance query endpoint** (`/fmcsa-insurance/query`) — that is P3 follow-up.
- **No authority changes query endpoint** (`/fmcsa-authority/query`) — that is P3 follow-up.
- **No verticals endpoint** (`/fmcsa-carriers/verticals`) — that is P3 follow-up.
- **No caching layer.**
- **No materialized views.** Query the tables directly.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Carrier query: filter count, parameterization approach, curated return column count, latest-snapshot CTE approach
(b) Carrier detail: number of table sections, join strategy for docket-to-DOT mapping, response shape
(c) Carrier stats: stat categories, fleet size buckets, safety alert categories
(d) Safety risk: join approach (census + percentiles + crash count), filter count, trailing 12-month crash count method
(e) Crash query: filter count, return column count
(f) CSV export: streaming approach, max_rows safety, column count in header, shared filter builder location
(g) Router: all 6 endpoint paths, HTTP methods, auth dependency, registration in main.py
(h) Tests: total test count, all passing
(i) Anything to flag — especially: query performance concerns on large tables, any ambiguity in column names or types discovered in the migrations
