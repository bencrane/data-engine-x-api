# Executor Directive: FMCSA Analytics — Materialized Views for Authority Grants & Insurance Cancellations

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA analytics endpoints (`/fmcsa/analytics/monthly-summary` and `/fmcsa-carriers/analytics`) are timing out and returning 500 in production. The root cause: `operating_authority_histories` has 29.7M rows and every analytics query does `UPPER(final_authority_action_description) LIKE '%GRANT%'` — the leading `%` wildcard prevents any B-tree index from being used, forcing a full sequential scan of all 29.7M rows. The 60-second statement timeout expires before the scan completes.

**The fix — architectural, not query-level:** Build materialized views that pre-filter and pre-cast the base table data into small, purpose-built analytical tables. This is the same pattern already working for federal contract leads (`entities.mv_federal_contract_leads` built from 1.34M-row `usaspending_contracts` + 867K-row `sam_gov_entities`). The analytics endpoints query the MVs, not the base tables. The MVs are tiny (1-2% of base table rows) and have indexes tuned for the exact aggregation queries.

---

## Reference Documents (Read Before Starting)

**Must read — existing MV pattern (your primary reference):**
- `supabase/migrations/033_mv_federal_contract_leads.sql` — The MV creation pattern: `SET statement_timeout = '0'`, no transaction wrapper, CTEs for dedup/filtering, computed columns, indexes including a unique index for `REFRESH CONCURRENTLY`, `RESET statement_timeout` at end
- `app/services/federal_leads_refresh.py` — The refresh service pattern: connection pool singleton, `SET LOCAL statement_timeout = '1800s'`, `REFRESH MATERIALIZED VIEW CONCURRENTLY`, timing instrumentation, commit after refresh
- `app/routers/internal.py` (search for `federal-contract-leads/refresh`) — The internal refresh endpoint pattern: `require_internal_key` auth, `concurrent` parameter, imports service at call time

**Must read — the broken analytics code:**
- `app/services/fmcsa_analytics.py` — Current monthly summary service. Both queries timeout in prod. The `last_observed_at` filter was added as a workaround but doesn't help enough.
- `app/services/fmcsa_consolidated_analytics.py` — Newer consolidated analytics with `run_fmcsa_analytics()` dispatch. Same underlying queries, same timeout problem.

**Must read — base table schemas:**
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — `operating_authority_histories` and `insurance_policy_history_events` table definitions. Pay attention to: column names, column types, existing indexes.

---

## Deliverables

### Deliverable 1: Migration — Authority Grants Materialized View

Create `supabase/migrations/036_mv_fmcsa_authority_grants.sql`.

**Follow the exact same pattern as `033_mv_federal_contract_leads.sql`:**
- `SET statement_timeout = '0'` at top (no transaction wrapper)
- `CREATE MATERIALIZED VIEW` with query
- Indexes after creation
- `RESET statement_timeout` at end

#### View: `entities.mv_fmcsa_authority_grants`

**Purpose:** Pre-filtered, pre-cast subset of `operating_authority_histories` containing only authority grant rows. Expected size: a small fraction of the 29.7M base table rows.

**Before writing the SQL, run this discovery query** against the base table to understand the actual values:

```sql
SELECT
    final_authority_action_description,
    COUNT(*) AS cnt
FROM entities.operating_authority_histories
WHERE final_authority_action_description IS NOT NULL
GROUP BY final_authority_action_description
ORDER BY cnt DESC
LIMIT 50;
```

This tells you the exact grant-related action descriptions. The current code uses `UPPER(...) LIKE '%GRANT%'` — confirm what values that actually matches (e.g., `'GRANT OF AUTHORITY'`, `'GRANTED'`, etc.) and hard-code the filter in the MV definition to match the same rows.

**MV query:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_authority_grants AS
SELECT
    id,
    docket_number,
    usdot_number,
    sub_number,
    operating_authority_type,
    final_authority_action_description,
    final_authority_decision_date,
    final_authority_served_date,
    original_authority_action_description,
    source_feed_name,
    first_observed_at,
    last_observed_at,
    created_at
FROM entities.operating_authority_histories
WHERE final_authority_action_description IS NOT NULL
  AND UPPER(final_authority_action_description) LIKE '%GRANT%'
  AND final_authority_decision_date IS NOT NULL;
```

**Column selection rationale:**
- `id` — unique key for the MV (enables concurrent refresh)
- `docket_number`, `usdot_number`, `sub_number` — carrier identification
- `operating_authority_type` — for breakdowns by authority type (common, contract, broker)
- `final_authority_action_description` — keep for audit/verification
- `final_authority_decision_date`, `final_authority_served_date` — the date dimensions for time-series queries
- `original_authority_action_description` — may differ from final; useful for classification verification
- `source_feed_name`, `first_observed_at`, `last_observed_at`, `created_at` — lineage tracking

**Do NOT include:** `raw_source_row` (JSONB, large), `source_run_metadata` (JSONB, large), `source_download_url`, `source_task_id`, `source_schedule_id` — these are operational lineage fields not needed for analytics.

**Indexes (5):**

```sql
-- Unique index: enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_ag_id
    ON entities.mv_fmcsa_authority_grants (id);

-- Primary analytics dimension: decision date
CREATE INDEX idx_mv_fmcsa_ag_decision_date
    ON entities.mv_fmcsa_authority_grants (final_authority_decision_date);

-- Carrier lookups
CREATE INDEX idx_mv_fmcsa_ag_usdot
    ON entities.mv_fmcsa_authority_grants (usdot_number);

-- Authority type breakdowns
CREATE INDEX idx_mv_fmcsa_ag_auth_type
    ON entities.mv_fmcsa_authority_grants (operating_authority_type);

-- Composite for the exact analytics query pattern
CREATE INDEX idx_mv_fmcsa_ag_date_usdot
    ON entities.mv_fmcsa_authority_grants (final_authority_decision_date, usdot_number);
```

Commit standalone.

---

### Deliverable 2: Migration — Insurance Cancellations Materialized View

Create `supabase/migrations/037_mv_fmcsa_insurance_cancellations.sql`.

Same pattern: `SET statement_timeout = '0'`, no transaction wrapper.

#### View: `entities.mv_fmcsa_insurance_cancellations`

**Purpose:** Pre-filtered subset of `insurance_policy_history_events` containing only rows with a non-null cancellation date. The base table contains all policy history events — the cancellation MV extracts only the cancellation events.

**MV query:**

```sql
CREATE MATERIALIZED VIEW entities.mv_fmcsa_insurance_cancellations AS
SELECT
    id,
    docket_number,
    usdot_number,
    form_code,
    cancellation_method,
    cancellation_form_code,
    specific_cancellation_method,
    insurance_type_indicator,
    insurance_type_description,
    insurance_company_name,
    policy_number,
    effective_date,
    cancel_effective_date,
    bipd_underlying_limit_amount_thousands_usd,
    bipd_max_coverage_amount_thousands_usd,
    source_feed_name,
    first_observed_at,
    last_observed_at,
    created_at
FROM entities.insurance_policy_history_events
WHERE cancel_effective_date IS NOT NULL;
```

**Column selection rationale:**
- `id` — unique key for concurrent refresh
- `docket_number`, `usdot_number` — carrier identification
- `cancellation_method`, `cancellation_form_code`, `specific_cancellation_method` — cancellation classification (enables breakdown by cancellation type)
- `insurance_type_indicator`, `insurance_type_description` — insurance type for breakdowns
- `insurance_company_name` — enables "which insurers are seeing the most cancellations" analysis
- `policy_number` — dedup/audit
- `effective_date`, `cancel_effective_date` — time dimensions
- `bipd_underlying_limit_amount_thousands_usd`, `bipd_max_coverage_amount_thousands_usd` — dollar dimensions (coverage amounts affected by cancellation)
- Same lineage columns as authority grants MV

**Do NOT include:** `raw_source_row`, `source_run_metadata`, `source_download_url`, `source_task_id`, `source_schedule_id`, `insurance_class_code`, `minimum_coverage_amount_thousands_usd`, `insurance_company_branch`.

**Indexes (5):**

```sql
-- Unique index: enables REFRESH MATERIALIZED VIEW CONCURRENTLY
CREATE UNIQUE INDEX idx_mv_fmcsa_ic_id
    ON entities.mv_fmcsa_insurance_cancellations (id);

-- Primary analytics dimension: cancellation date
CREATE INDEX idx_mv_fmcsa_ic_cancel_date
    ON entities.mv_fmcsa_insurance_cancellations (cancel_effective_date);

-- Carrier lookups
CREATE INDEX idx_mv_fmcsa_ic_usdot
    ON entities.mv_fmcsa_insurance_cancellations (usdot_number);

-- Cancellation type breakdowns
CREATE INDEX idx_mv_fmcsa_ic_cancel_method
    ON entities.mv_fmcsa_insurance_cancellations (cancellation_method);

-- Composite for the exact analytics query pattern
CREATE INDEX idx_mv_fmcsa_ic_date_usdot
    ON entities.mv_fmcsa_insurance_cancellations (cancel_effective_date, usdot_number);
```

Commit standalone.

---

### Deliverable 3: Refresh Service

Create `app/services/fmcsa_analytics_refresh.py`.

**Follow the exact same pattern as `app/services/federal_leads_refresh.py`.**

Module-level connection pool singleton with threading lock.

#### Function 1: `refresh_fmcsa_authority_grants`

```python
def refresh_fmcsa_authority_grants(*, concurrent: bool = True) -> dict[str, Any]:
```

- `REFRESH MATERIALIZED VIEW [CONCURRENTLY] entities.mv_fmcsa_authority_grants`
- `SET LOCAL statement_timeout = '1800s'` (the initial population scan of 29.7M rows may take a while)
- Timing instrumentation (elapsed_ms)
- Returns `{"view": "mv_fmcsa_authority_grants", "refreshed_at": ..., "concurrent": ..., "elapsed_ms": ...}`

#### Function 2: `refresh_fmcsa_insurance_cancellations`

```python
def refresh_fmcsa_insurance_cancellations(*, concurrent: bool = True) -> dict[str, Any]:
```

Same pattern as above, targeting `entities.mv_fmcsa_insurance_cancellations`.

#### Function 3: `refresh_all_fmcsa_analytics`

```python
def refresh_all_fmcsa_analytics(*, concurrent: bool = True) -> dict[str, Any]:
```

Calls both refresh functions sequentially. Returns combined result:
```python
{
    "authority_grants": { ... },
    "insurance_cancellations": { ... },
    "total_elapsed_ms": ...,
}
```

Commit standalone.

---

### Deliverable 4: Update Analytics Services to Query the MVs

#### Update `app/services/fmcsa_analytics.py`

Change `get_fmcsa_monthly_summary()` to query the materialized views instead of the base tables.

**New authority grants query:**

```sql
SELECT
    TO_CHAR(final_authority_decision_date, 'YYYY-MM') AS month,
    COUNT(*) AS count
FROM entities.mv_fmcsa_authority_grants
WHERE final_authority_decision_date >= %s
GROUP BY month
ORDER BY month ASC
```

**Key changes from current code:**
- Queries `entities.mv_fmcsa_authority_grants` instead of `entities.operating_authority_histories`
- No `UPPER(final_authority_action_description) LIKE '%GRANT%'` filter — the MV already contains only grant rows
- No `last_observed_at` filter — that was a scan-reduction workaround that's no longer needed
- Can remove or reduce the `SET statement_timeout = '60s'` — the MV is small enough that a 30s timeout is generous
- Keep the `cutoff_date` filter on `final_authority_decision_date` — that's the actual business logic filter

**New insurance cancellations query:**

```sql
SELECT
    TO_CHAR(cancel_effective_date, 'YYYY-MM') AS month,
    COUNT(*) AS count
FROM entities.mv_fmcsa_insurance_cancellations
WHERE cancel_effective_date >= %s
GROUP BY month
ORDER BY month ASC
```

**Key changes from current code:**
- Queries `entities.mv_fmcsa_insurance_cancellations` instead of `entities.insurance_policy_history_events`
- No `last_observed_at` filter
- No `cancel_effective_date IS NOT NULL` filter — the MV already excludes NULLs

**Keep the same return format** — the function signature and return shape must not change. Existing endpoint wiring stays as-is.

#### Update `app/services/fmcsa_consolidated_analytics.py`

Same changes to the underlying queries in `_new_authorities_by_month()` and `_insurance_cancellations_by_month()`:

**`_new_authorities_by_month`:**
- Query `entities.mv_fmcsa_authority_grants` instead of `entities.operating_authority_histories`
- Remove the `LIKE '%GRANT%'` filter
- Keep date range filtering on `final_authority_decision_date`
- Keep `COUNT(DISTINCT usdot_number) AS unique_carriers`

**`_insurance_cancellations_by_month`:**
- Primary source becomes `entities.mv_fmcsa_insurance_cancellations` instead of `entities.insurance_policy_history_events`
- Remove the `cancel_effective_date IS NOT NULL` filter
- Keep date range filtering on `cancel_effective_date`
- Keep `COUNT(DISTINCT usdot_number) AS unique_carriers`
- Keep the `fmcsa_carrier_signals` fallback — it's still valid as a secondary source

**Keep the same return format and function signatures** — endpoint wiring stays as-is.

Commit standalone.

---

### Deliverable 5: Internal Refresh Endpoint

Add to `app/routers/internal.py`, following the exact same pattern as the `federal-contract-leads/refresh` endpoint.

#### Endpoint: `POST /api/internal/fmcsa-analytics/refresh`

Auth: `require_internal_key` (same as federal leads refresh).

**Request model:**

```python
class InternalFmcsaAnalyticsRefreshRequest(BaseModel):
    concurrent: bool = True
    views: str = "all"  # "all", "authority_grants", "insurance_cancellations"
```

**Handler:**
- If `views == "all"`: call `refresh_all_fmcsa_analytics(concurrent=...)`
- If `views == "authority_grants"`: call `refresh_fmcsa_authority_grants(concurrent=...)`
- If `views == "insurance_cancellations"`: call `refresh_fmcsa_insurance_cancellations(concurrent=...)`
- Else: return 400

Response: `DataEnvelope` wrapping the refresh result.

Import the service functions at call time (same lazy-import pattern as the federal leads refresh endpoint).

Commit standalone.

---

### Deliverable 6: Tests

Create `tests/test_fmcsa_analytics_refresh.py`.

**Refresh service tests (5):**
1. `refresh_fmcsa_authority_grants()` calls `REFRESH MATERIALIZED VIEW CONCURRENTLY` when `concurrent=True`
2. `refresh_fmcsa_authority_grants()` calls `REFRESH MATERIALIZED VIEW` (no CONCURRENTLY) when `concurrent=False`
3. `refresh_fmcsa_insurance_cancellations()` follows same pattern
4. `refresh_all_fmcsa_analytics()` calls both, returns combined result with `total_elapsed_ms`
5. All refresh functions set `statement_timeout = '1800s'`

**Updated analytics service tests (4):**
6. `get_fmcsa_monthly_summary()` queries `mv_fmcsa_authority_grants` (not the base table)
7. `get_fmcsa_monthly_summary()` queries `mv_fmcsa_insurance_cancellations` (not the base table)
8. `_new_authorities_by_month()` in consolidated analytics queries the MV
9. `_insurance_cancellations_by_month()` in consolidated analytics queries the MV, falls back to `fmcsa_carrier_signals`

**Endpoint tests (3):**
10. `POST /api/internal/fmcsa-analytics/refresh` with `views="all"` returns `DataEnvelope` with both results
11. `POST /api/internal/fmcsa-analytics/refresh` with `views="authority_grants"` returns only authority grants result
12. Auth required (returns 401 without internal key)

All tests mock database calls. Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No changes to the base tables** (`operating_authority_histories`, `insurance_policy_history_events`). No new columns, no backfills, no schema changes to existing tables.
- **No changes to FMCSA ingest code.** The ingest pipeline writes to the base tables. The MVs are refreshed separately.
- **No changes to existing endpoint paths or signatures.** The existing `/fmcsa/analytics/monthly-summary` and `/fmcsa-carriers/analytics` endpoints keep their paths and request/response shapes. Only the underlying SQL changes.
- **No scheduled/automated refresh.** The refresh is manual via the internal endpoint. Automated scheduling is future work.
- **No Trigger.dev tasks.**
- **No deploy commands.** Do not push.

## Migration Execution Notes

The executor should be aware of these production deployment concerns (but should NOT execute them — just document in the report):

1. **Initial MV population will be slow.** The `CREATE MATERIALIZED VIEW` statement scans the 29.7M-row base table. `SET statement_timeout = '0'` handles this, but it may take several minutes. This is a one-time cost.

2. **Migration must be run outside a transaction** (same as `033_mv_federal_contract_leads.sql`). Supabase's migration runner may need special handling — see the `NOTE` comment at the top of migration 033 for the pattern.

3. **Deploy order matters.** The migration must run first (creates the MVs and populates them). Then the code deploy can go out (analytics services switch to querying the MVs). If code deploys first, it will try to query MVs that don't exist yet. This is the reverse of the normal Railway-first/Trigger-second deploy order documented in CLAUDE.md — but since this is FastAPI-only code (no Trigger.dev changes), it's just: run migration → deploy Railway.

4. **First refresh after creation is free.** `CREATE MATERIALIZED VIEW` populates the view. The first `REFRESH CONCURRENTLY` only needs to happen after new data is ingested into the base tables.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Authority grants MV: row count from the `SELECT DISTINCT final_authority_action_description` discovery query, which action descriptions matched the `LIKE '%GRANT%'` pattern, final MV row count estimate
(b) Insurance cancellations MV: estimated row count (rows with non-null `cancel_effective_date`)
(c) Analytics service changes: confirm both `fmcsa_analytics.py` and `fmcsa_consolidated_analytics.py` now query MVs, confirm return shapes unchanged
(d) Refresh service: all 3 functions, confirm pattern matches `federal_leads_refresh.py`
(e) Internal endpoint: path, auth, request model
(f) Tests: total count, all passing
(g) Anything to flag — especially: whether the `LIKE '%GRANT%'` pattern matched unexpected action descriptions, estimated MV sizes, any concerns about refresh duration on the 29.7M row base table
