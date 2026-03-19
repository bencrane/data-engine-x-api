# Executor Directive: Federal Contract Leads + FMCSA — Consolidated Analytics Endpoints

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have row-level query endpoints for both federal contract leads and FMCSA carriers, plus scattered analytics endpoints across `federal_leads_insights.py`, `federal_leads_analytics.py`, `federal_leads_naics_metrics.py`, and `fmcsa_analytics.py`. What's missing is a single, consolidated analytics endpoint per domain that accepts a `query_type` parameter and answers specific business intelligence questions. The purpose is to surface compelling data points for outbound sales campaigns — e.g., "1,406 companies won their first federal manufacturing contract this quarter — how are they finding you?"

**Critical distinction — temporal "first-time" definition:** The existing `is_first_time_awardee` flag on the materialized view means "this company has exactly 1 distinct award across all time." That is NOT what we want. We need a temporal definition: a company is a "first-time awardee" in a given date range when its **earliest `action_date` across all of our data** falls within that range. This means a company that won its first-ever contract in Q1 2025 and its second in Q2 2025 was a "first-time awardee" in Q1 2025 but a "repeat awardee" in Q2 2025 — even though it has 2 awards total. This temporal definition powers time-series questions like "how many new entrants this quarter?" and comparisons like "first-time vs repeat awardee average award value in Q4."

---

## Reference Documents (Read Before Starting)

**Must read — existing code (your primary pattern reference):**
- `app/services/federal_leads_insights.py` — Current insights service with `get_vertical_insights()`, `get_agency_insights()`, `get_repeat_awardee_cumulative()`. Study the `_build_where()` helper, `VERTICAL_CASE` expression, and `_float()` helper. You will reuse these patterns but NOT import from this file.
- `app/services/federal_leads_analytics.py` — Current analytics with 7 functions (time series, size distribution, set-aside, competition, geographic, repeat velocity, ceiling gap). Study the `_build_analytics_where()` helper. You will reuse these patterns but NOT import from this file.
- `app/services/fmcsa_analytics.py` — Current FMCSA monthly summary. Study the query patterns against `operating_authority_histories` and `insurance_policy_history_events`.
- `app/routers/entities_v1.py` — Endpoint wiring. Study the `_resolve_flexible_auth` pattern, `DataEnvelope` response wrapping, and filter extraction pattern.

**Must read — schemas:**
- `supabase/migrations/034_mv_federal_contract_leads_agency_first_time.sql` — Materialized view columns including `naics_code`, `naics_description`, `recipient_uei`, `is_first_time_awardee`, `total_awards_count`, `federal_action_obligation`, `potential_total_value_of_award`, `awarding_agency_code`, `awarding_agency_name`, `action_date`, `contract_award_unique_key`, `recipient_state_code`, `contracting_officers_determination_of_business_size`
- `supabase/migrations/022_fmcsa_top5_daily_diff_tables.sql` — `operating_authority_histories` (columns: `final_authority_action_description`, `final_authority_decision_date`, `usdot_number`) and `insurance_policy_history_events` (columns: `cancel_effective_date`, `usdot_number`)
- `supabase/migrations/023_fmcsa_snapshot_history_tables.sql` — `feed_date` + `row_position` patterns on FMCSA tables
- `supabase/migrations/035_fmcsa_carrier_signals.sql` — `fmcsa_carrier_signals` (columns: `signal_type`, `severity`, `feed_date`, `dot_number`, `legal_name`, `physical_state`, `power_unit_count`, `driver_total`, `before_values`, `after_values`, `signal_details`)

---

## Deliverables

### Deliverable 1: Federal Contract Leads — Consolidated Analytics Service

Create `app/services/federal_leads_consolidated_analytics.py`.

Follow the same connection pool pattern as `federal_leads_insights.py` (module-level singleton, threading lock).

**This file contains ONE public entry function and several private query functions.**

#### Public function: `run_federal_analytics`

```python
def run_federal_analytics(
    *,
    query_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

Dispatches to the appropriate private query function based on `query_type`. Returns the query result dict. Raises `ValueError` for unknown query types.

`params` is a flat dict of query-type-specific parameters. Each query type defines which params it accepts.

#### Query Type 1: `first_time_awardees_by_naics`

**Question answered:** "How many unique companies won their first-ever federal contract in a given date range, broken down by NAICS vertical? Top N by count."

**Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `date_from` | `str` (YYYY-MM-DD) | Yes | — | Start of date range |
| `date_to` | `str` (YYYY-MM-DD) | Yes | — | End of date range |
| `limit` | `int` | No | `20` | Top N verticals |

**SQL approach — temporal first-time definition:**

```sql
WITH company_first_dates AS (
    -- Find each company's earliest action_date across ALL data
    SELECT
        recipient_uei,
        MIN(action_date::DATE) AS first_action_date
    FROM entities.mv_federal_contract_leads
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND action_date IS NOT NULL AND action_date != ''
    GROUP BY recipient_uei
),
new_entrants AS (
    -- Companies whose first-ever action_date falls in the specified range
    SELECT recipient_uei
    FROM company_first_dates
    WHERE first_action_date BETWEEN %s AND %s
)
SELECT
    {VERTICAL_CASE} AS vertical,
    COUNT(DISTINCT m.recipient_uei) AS first_time_companies,
    COUNT(DISTINCT m.contract_award_unique_key) AS first_time_awards,
    SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS first_time_total_obligated,
    SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC))
        / NULLIF(COUNT(DISTINCT m.contract_award_unique_key), 0) AS first_time_avg_award_value
FROM entities.mv_federal_contract_leads m
JOIN new_entrants ne ON m.recipient_uei = ne.recipient_uei
WHERE m.action_date::DATE BETWEEN %s AND %s
GROUP BY vertical
ORDER BY COUNT(DISTINCT m.recipient_uei) DESC
LIMIT %s
```

**Note:** The date range appears twice — once to identify which companies are "new entrants" (their global first action_date is in the range), and once to scope the transaction data to the same range. The `%s` params for both ranges use the same `date_from`/`date_to` values.

**Return format:**
```python
{
    "query_type": "first_time_awardees_by_naics",
    "date_range": {"from": "2025-10-01", "to": "2025-12-31"},
    "items": [
        {
            "vertical": "Manufacturing",
            "first_time_companies": 1406,
            "first_time_awards": 1823,
            "first_time_total_obligated": 284500000.0,
            "first_time_avg_award_value": 156050.0,
        },
        ...
    ],
}
```

#### Query Type 2: `first_time_avg_award_by_naics`

**Question answered:** "For each vertical — what's the average award value for first-time awardees specifically?"

**Parameters:** Same as query type 1 (`date_from`, `date_to`, `limit`).

**SQL approach:** Same CTE structure as query type 1. The output focuses on award value metrics:

**Output fields per row (6 fields):**

| Field | Description |
|---|---|
| `vertical` | NAICS vertical label |
| `first_time_companies` | Unique first-time companies |
| `first_time_awards` | Distinct awards by first-timers |
| `first_time_avg_award_value` | total_obligated / total_awards for first-timers |
| `first_time_median_award_value` | `PERCENTILE_CONT(0.5)` on obligation for first-timer transactions |
| `first_time_total_obligated` | Sum of obligations by first-timers |

Order by `first_time_avg_award_value DESC`.

#### Query Type 3: `total_by_naics`

**Question answered:** "For each vertical — total companies (first-time + repeat within the date range), total awards, total dollars obligated."

**Parameters:** `date_from`, `date_to`, `limit`.

**SQL approach:** Same `company_first_dates` CTE to classify companies, then aggregate ALL transactions in the date range (not just first-timers):

**Output fields per row (10 fields):**

| Field | Description |
|---|---|
| `vertical` | NAICS vertical label |
| `total_companies` | All unique companies with transactions in range |
| `total_awards` | All distinct awards in range |
| `total_obligated` | Sum of obligations in range |
| `avg_award_value` | total_obligated / total_awards |
| `first_time_companies` | Companies whose first-ever action_date is in this range |
| `repeat_companies` | total_companies - first_time_companies |
| `first_time_total_obligated` | Obligations from first-timers |
| `repeat_total_obligated` | Obligations from repeat awardees |
| `first_time_pct` | first_time_companies / total_companies * 100 |

This uses a LEFT JOIN to `new_entrants` so all companies appear, and a CASE WHEN on the join to split metrics:

```sql
-- Inside the SELECT, after the CTE:
COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NOT NULL) AS first_time_companies,
COUNT(DISTINCT m.recipient_uei) FILTER (WHERE ne.recipient_uei IS NULL) AS repeat_companies,
```

Order by `total_obligated DESC`.

#### Query Type 4: `sub_naics_breakdown`

**Question answered:** "For a given NAICS prefix (e.g., manufacturing 31-33) — break it down by sub-NAICS. First-time awardee counts and average award value per sub-vertical."

**Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `naics_prefix` | `str` | Yes | — | NAICS prefix (e.g., `"31"`, `"23"`, `"541"`) |
| `date_from` | `str` | Yes | — | Start of date range |
| `date_to` | `str` | Yes | — | End of date range |
| `limit` | `int` | No | `50` | Top N sub-NAICS codes |

**SQL approach:** Same temporal CTE structure. Group by individual `naics_code` instead of vertical bucket. Filter with `naics_code LIKE %s` using `{naics_prefix}%`.

**Output fields per row (9 fields):**

| Field | Description |
|---|---|
| `naics_code` | Full NAICS code (e.g., `541330`) |
| `naics_description` | `MAX(naics_description)` |
| `total_companies` | All companies in range |
| `first_time_companies` | First-timers in range |
| `total_awards` | Distinct awards |
| `total_obligated` | Dollars obligated |
| `first_time_total_obligated` | First-timer dollars |
| `avg_award_value` | total_obligated / total_awards |
| `first_time_avg_award_value` | First-timer dollars / first-timer awards |

Order by `first_time_companies DESC`.

**Note for manufacturing NAICS prefix:** Manufacturing spans `31xxxx`, `32xxxx`, and `33xxxx`. The caller should call this endpoint three times (with `"31"`, `"32"`, `"33"`) or the endpoint should accept a list. Design decision for the executor: accept `naics_prefix` as a single string. The caller handles multi-prefix by making multiple calls. Keep it simple.

#### Query Type 5: `first_time_by_agency`

**Question answered:** "For all first-time awardees in a date range — breakdown by awarding agency."

**Parameters:** `date_from`, `date_to`, `limit` (default `20`).

**SQL approach:** Same temporal CTE. Join to `new_entrants`, group by `awarding_agency_code`.

**Output fields per row (7 fields):**

| Field | Description |
|---|---|
| `awarding_agency_code` | 3-digit CGAC code |
| `awarding_agency_name` | `MAX(awarding_agency_name)` |
| `first_time_companies` | Unique first-time companies funded by this agency |
| `first_time_awards` | Distinct awards |
| `first_time_total_obligated` | Dollars from first-timers |
| `first_time_avg_award_value` | Average award value for first-timers |
| `pct_of_all_first_timers` | This agency's first-time companies / total first-time companies * 100 |

The `pct_of_all_first_timers` uses `COUNT(DISTINCT ...) / NULLIF(SUM(COUNT(DISTINCT ...)) OVER(), 0) * 100` as a window function.

Order by `first_time_companies DESC`.

#### Query Type 6: `repeat_awardee_avg_by_naics`

**Question answered:** "For repeat awardees in a date range — average cumulative total obligated per company, by vertical."

**Parameters:** `date_from`, `date_to`.

**SQL approach:** Use the same temporal CTE. A "repeat awardee" in this context is a company whose `first_action_date` is BEFORE the `date_from` (i.e., they had at least one prior award). Then aggregate their transactions within the date range.

```sql
WITH company_first_dates AS (
    SELECT recipient_uei, MIN(action_date::DATE) AS first_action_date
    FROM entities.mv_federal_contract_leads
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
      AND action_date IS NOT NULL AND action_date != ''
    GROUP BY recipient_uei
),
repeat_awardees AS (
    -- Companies whose first action_date is BEFORE our date range
    SELECT recipient_uei
    FROM company_first_dates
    WHERE first_action_date < %s  -- date_from
),
per_company AS (
    SELECT
        {VERTICAL_CASE} AS vertical,
        m.recipient_uei,
        SUM(CAST(NULLIF(m.federal_action_obligation, '') AS NUMERIC)) AS company_total_obligated,
        COUNT(DISTINCT m.contract_award_unique_key) AS company_awards
    FROM entities.mv_federal_contract_leads m
    JOIN repeat_awardees ra ON m.recipient_uei = ra.recipient_uei
    WHERE m.action_date::DATE BETWEEN %s AND %s
    GROUP BY vertical, m.recipient_uei
)
SELECT
    vertical,
    COUNT(*) AS repeat_companies,
    AVG(company_total_obligated) AS avg_cumulative_obligated,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY company_total_obligated) AS median_cumulative_obligated,
    AVG(company_awards) AS avg_awards_per_company,
    SUM(company_total_obligated) AS total_obligated
FROM per_company
GROUP BY vertical
ORDER BY AVG(company_total_obligated) DESC
```

**Output fields per row (6 fields):**

| Field | Description |
|---|---|
| `vertical` | NAICS vertical label |
| `repeat_companies` | Unique repeat awardees active in range |
| `avg_cumulative_obligated` | Average total obligated per repeat company in range |
| `median_cumulative_obligated` | Median |
| `avg_awards_per_company` | Average distinct awards per repeat company in range |
| `total_obligated` | Total dollars from repeat awardees in range |

#### Shared patterns across all query types

- **`VERTICAL_CASE`**: Copy the same 7-bucket CASE expression from `federal_leads_insights.py`. Do NOT import it — keep this service self-contained.
- **`_float()` helper**: Same null-safe float conversion.
- **Parameterized queries**: All values via `%s`. No string interpolation ever.
- **Schema-qualified**: All queries against `entities.mv_federal_contract_leads`.
- **Statement timeout**: Set `SET statement_timeout = '30s'` at connection level for all queries. These are aggregate queries on 1.34M rows — 30s is generous but prevents runaway queries.
- **Date validation**: Validate `date_from` and `date_to` are valid `YYYY-MM-DD` strings before passing to SQL. Raise `ValueError` if invalid.

Commit standalone.

---

### Deliverable 2: FMCSA — Consolidated Analytics Service

Create `app/services/fmcsa_consolidated_analytics.py`.

Same connection pool pattern.

#### Public function: `run_fmcsa_analytics`

```python
def run_fmcsa_analytics(
    *,
    query_type: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
```

Dispatches to the appropriate private query function. Raises `ValueError` for unknown query types.

#### Query Type 1: `new_authorities_by_month`

**Question answered:** "How many new operating authorities were granted per month over the last N months?"

**Parameters:**

| Param | Type | Required | Default | Description |
|---|---|---|---|---|
| `months` | `int` | No | `6` | How many months back (max 24) |
| `date_from` | `str` | No | — | Override: explicit start date (YYYY-MM-DD) |
| `date_to` | `str` | No | — | Override: explicit end date (YYYY-MM-DD) |

If `date_from`/`date_to` are provided, they take precedence over `months`. Otherwise, compute cutoff as `date.today() - timedelta(days=months * 31)`.

**SQL:**

```sql
SELECT
    TO_CHAR(final_authority_decision_date, 'YYYY-MM') AS month,
    COUNT(*) AS new_authorities,
    COUNT(DISTINCT usdot_number) AS unique_carriers
FROM entities.operating_authority_histories
WHERE final_authority_decision_date >= %s
  AND final_authority_decision_date <= %s
  AND final_authority_action_description IS NOT NULL
  AND UPPER(final_authority_action_description) LIKE '%%GRANT%%'
GROUP BY month
ORDER BY month ASC
```

**Return format:**
```python
{
    "query_type": "new_authorities_by_month",
    "date_range": {"from": "2025-09-01", "to": "2026-03-17"},
    "items": [
        {"month": "2025-09", "new_authorities": 342, "unique_carriers": 298},
        {"month": "2025-10", "new_authorities": 415, "unique_carriers": 371},
        ...
    ],
}
```

**Note:** The existing `fmcsa_analytics.py` queries `operating_authority_histories` with `LIKE '%GRANT%'`. This is the same approach. The improvement is: we also return `unique_carriers` (distinct `usdot_number`) since one carrier can receive multiple authority grants in a month.

#### Query Type 2: `insurance_cancellations_by_month`

**Question answered:** "How many insurance cancellations per month over the last N months?"

**Parameters:** Same as query type 1 (`months`, `date_from`, `date_to`).

**SQL — primary source: `insurance_policy_history_events`:**

```sql
SELECT
    TO_CHAR(cancel_effective_date, 'YYYY-MM') AS month,
    COUNT(*) AS cancellations,
    COUNT(DISTINCT usdot_number) AS unique_carriers
FROM entities.insurance_policy_history_events
WHERE cancel_effective_date >= %s
  AND cancel_effective_date <= %s
  AND cancel_effective_date IS NOT NULL
GROUP BY month
ORDER BY month ASC
```

**Secondary source — signal detection fallback:** If the primary query returns no rows (possible if `insurance_policy_history_events` has no recent data), fall back to:

```sql
SELECT
    TO_CHAR(feed_date, 'YYYY-MM') AS month,
    COUNT(*) AS cancellations,
    COUNT(DISTINCT dot_number) AS unique_carriers
FROM entities.fmcsa_carrier_signals
WHERE signal_type = 'insurance_lapsed'
  AND feed_date >= %s
  AND feed_date <= %s
GROUP BY month
ORDER BY month ASC
```

Include a `source` field in the return (`"insurance_policy_history_events"` or `"fmcsa_carrier_signals"`) so the caller knows which table was used.

**Return format:**
```python
{
    "query_type": "insurance_cancellations_by_month",
    "date_range": {"from": "2025-09-01", "to": "2026-03-17"},
    "source": "insurance_policy_history_events",
    "items": [
        {"month": "2025-09", "cancellations": 1203, "unique_carriers": 987},
        ...
    ],
}
```

Commit standalone.

---

### Deliverable 3: Wire Both Endpoints

Add to `app/routers/entities_v1.py`.

#### Endpoint 1: `POST /api/v1/federal-contract-leads/analytics`

Auth: `_resolve_flexible_auth` (tenant JWT or super-admin).

**Request model:**

```python
class FederalAnalyticsRequest(BaseModel):
    query_type: str  # One of the 6 query types
    date_from: str | None = None  # YYYY-MM-DD
    date_to: str | None = None    # YYYY-MM-DD
    naics_prefix: str | None = None
    limit: int = Field(default=20, ge=1, le=500)
```

**Validation:** `date_from` and `date_to` are required for all query types. Return 400 if missing. `naics_prefix` is required only for `sub_naics_breakdown`. Return 400 if the query type is `sub_naics_breakdown` and `naics_prefix` is missing.

**Handler:** Build the params dict from the request, call `run_federal_analytics(query_type=..., params=...)`, wrap in `DataEnvelope`. Catch `ValueError` and return 400.

Response: `DataEnvelope` wrapping the service return value.

#### Endpoint 2: `POST /api/v1/fmcsa-carriers/analytics`

**Important routing note:** This endpoint path starts with `/fmcsa-carriers/` but the existing FMCSA endpoints are on a DIFFERENT router (`fmcsa_v1.py` with prefix `/api/v1`). Check which router already handles `/api/v1/fmcsa-carriers/*` — it may be `fmcsa_v1.py`, not `entities_v1.py`. Wire the new endpoint onto the correct existing router so the path prefix is consistent. If FMCSA carrier endpoints are on `fmcsa_v1.py`, add the analytics endpoint there. If they're on `entities_v1.py`, add it there.

Auth: `_resolve_flexible_auth`.

**Request model:**

```python
class FmcsaAnalyticsRequest(BaseModel):
    query_type: str  # "new_authorities_by_month" or "insurance_cancellations_by_month"
    months: int = Field(default=6, ge=1, le=24)
    date_from: str | None = None  # YYYY-MM-DD, overrides months
    date_to: str | None = None    # YYYY-MM-DD, overrides months
```

**Handler:** Build the params dict, call `run_fmcsa_analytics(query_type=..., params=...)`, wrap in `DataEnvelope`. Catch `ValueError` and return 400.

Response: `DataEnvelope`.

Commit standalone.

---

### Deliverable 4: Tests

Create `tests/test_federal_consolidated_analytics.py`.

**Query type 1 — `first_time_awardees_by_naics` (4 tests):**
1. Returns items with all fields (`vertical`, `first_time_companies`, `first_time_awards`, `first_time_total_obligated`, `first_time_avg_award_value`)
2. `date_from`/`date_to` are required — raises `ValueError` if missing
3. `limit` parameter caps the result set
4. Companies whose first action_date is outside the range are excluded from first-time counts

**Query type 2 — `first_time_avg_award_by_naics` (2 tests):**
5. Returns `first_time_median_award_value` field (handles NULLs)
6. Results ordered by `first_time_avg_award_value` DESC

**Query type 3 — `total_by_naics` (3 tests):**
7. `first_time_companies + repeat_companies = total_companies`
8. `first_time_total_obligated + repeat_total_obligated` approximately equals `total_obligated` (within float precision)
9. `first_time_pct` is between 0 and 100

**Query type 4 — `sub_naics_breakdown` (3 tests):**
10. `naics_prefix` is required — raises `ValueError` if missing
11. All returned `naics_code` values start with the requested prefix
12. Returns `naics_description` for each code

**Query type 5 — `first_time_by_agency` (2 tests):**
13. `pct_of_all_first_timers` values sum to approximately 100
14. Results ordered by `first_time_companies` DESC

**Query type 6 — `repeat_awardee_avg_by_naics` (2 tests):**
15. `avg_cumulative_obligated >= median_cumulative_obligated` is not guaranteed but both are positive floats
16. `repeat_companies` count is consistent with `total_obligated`

**Unknown query type (1 test):**
17. `run_federal_analytics(query_type="nonexistent")` raises `ValueError`

Create `tests/test_fmcsa_consolidated_analytics.py`.

**Query type 1 — `new_authorities_by_month` (3 tests):**
18. Returns items with `month` (YYYY-MM format), `new_authorities`, `unique_carriers`
19. `months` parameter controls date range
20. `date_from`/`date_to` override `months`

**Query type 2 — `insurance_cancellations_by_month` (3 tests):**
21. Returns items with `month`, `cancellations`, `unique_carriers`
22. Includes `source` field indicating which table was queried
23. Falls back to `fmcsa_carrier_signals` when primary source returns empty

**Unknown query type (1 test):**
24. `run_fmcsa_analytics(query_type="nonexistent")` raises `ValueError`

**Endpoint tests (4 tests):**
25. `POST /api/v1/federal-contract-leads/analytics` returns `DataEnvelope` shape
26. `POST /api/v1/federal-contract-leads/analytics` returns 400 for missing required params
27. `POST /api/v1/fmcsa-carriers/analytics` returns `DataEnvelope` shape
28. Auth required on both endpoints

All tests mock database calls. Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No materialized view changes.** All needed columns already exist on `entities.mv_federal_contract_leads`.
- **No schema migrations.** All FMCSA tables already exist.
- **No modifications to existing endpoints.** The existing `/analytics/*`, `/insights/*`, `/naics-metrics`, and `/fmcsa/analytics/monthly-summary` endpoints stay as-is. This directive adds new consolidated endpoints alongside them.
- **No modifications to existing service files.** Do not edit `federal_leads_insights.py`, `federal_leads_analytics.py`, `federal_leads_naics_metrics.py`, or `fmcsa_analytics.py`. Create new files.
- **No Trigger.dev tasks.**
- **No deploy commands.** Do not push.
- **No caching layer.** Some of these queries scan large tables — caching is future work.
- **No index creation.** If any query needs a composite index to perform well, document the recommendation in your report but do not create migrations.

## Performance Considerations

The temporal "first-time" definition requires a full scan to compute `MIN(action_date::DATE)` per company across 1.34M rows. This CTE is used by 5 of the 6 federal query types. Potential mitigations the executor should be aware of (but should NOT implement — just flag if queries are slow):

1. A materialized view or table storing `(recipient_uei, first_action_date)` would eliminate the repeated CTE scan.
2. An index on `(recipient_uei, action_date)` would speed up the MIN() aggregation.
3. The `company_first_dates` CTE could be extracted into a shared helper that the query functions call, keeping the SQL DRY.

The executor SHOULD extract the `company_first_dates` CTE into a reusable SQL fragment (a Python string constant) rather than duplicating it in every query function.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Federal analytics: all 6 query types implemented, confirm the temporal first-time CTE approach, field counts per query type
(b) FMCSA analytics: both query types, confirm which tables are queried, confirm the signal fallback logic
(c) Endpoints: both paths, auth pattern, request models, which router each endpoint is wired to
(d) Tests: total count across both test files, all passing
(e) Performance: did you observe any slow queries during testing? Any index recommendations?
(f) Anything to flag — especially: any columns that had unexpected NULL/empty rates, any ambiguity in the `GRANT` pattern matching for operating authorities, whether `insurance_policy_history_events` vs `insurance_policies.is_removal_signal` was the right source for cancellation data
