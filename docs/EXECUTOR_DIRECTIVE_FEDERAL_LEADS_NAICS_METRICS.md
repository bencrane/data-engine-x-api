# Executor Directive: Federal Contract Leads — NAICS Analytics & Sharp-Angle Data Endpoints

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We need a suite of aggregate analytics endpoints on the federal contract leads materialized view. The purpose is to surface compelling data points for outbound sales campaigns — e.g., "1,406 first-time manufacturing awardees won contracts this year — how are these companies finding you?" Every endpoint returns pre-aggregated metrics that power vertical analysis, campaign targeting, and sharp-angle messaging. All read-only, no writes.

The materialized view (`entities.mv_federal_contract_leads`) has 1.34M rows, 55K unique companies, and 63 columns including NAICS codes, award amounts, agency info, first-time awardee flags, competition data, set-aside types, and action dates. All columns are TEXT (cast at query time).

---

## Reference Documents (Read Before Starting)

**Must read — existing code (your primary pattern reference):**
- `app/services/federal_leads_verticals.py` — Existing vertical summary query, connection pool pattern, dict_row output, CTE approach, NULL/empty handling with `NULLIF`
- `app/services/federal_leads_query.py` — Parameterized query pattern, pagination with `COUNT(*) OVER()`
- `app/routers/entities_v1.py` — Endpoint wiring, `_resolve_flexible_auth`, `DataEnvelope` response, existing federal leads endpoints

**Must read — materialized view schema:**
- `supabase/migrations/034_mv_federal_contract_leads_agency_first_time.sql` — All 63 columns. Key columns for this directive: `naics_code`, `naics_description`, `recipient_uei`, `is_first_time_awardee`, `total_awards_count`, `federal_action_obligation`, `potential_total_value_of_award`, `awarding_agency_code`, `awarding_agency_name`, `action_date`, `type_of_set_aside`, `extent_competed`, `number_of_offers_received`, `recipient_state_code`, `contracting_officers_determination_of_business_size`, `contract_award_unique_key`

---

## Deliverables

### Deliverable 1: Core NAICS Metrics Service

Create `app/services/federal_leads_naics_metrics.py`.

Follow the same connection pool pattern as `federal_leads_verticals.py` (module-level singleton, threading lock). **All functions in this file share one pool.**

#### Function 1: `get_naics_metrics`

**`get_naics_metrics(*, filters: dict[str, Any] | None = None, limit: int = 100, offset: int = 0) -> dict[str, Any]`**

Queries `entities.mv_federal_contract_leads` and returns one row per distinct NAICS code.

**Output fields per row (12 fields):**

| Field | SQL | Description |
|---|---|---|
| `naics_code` | `naics_code` | The NAICS code (e.g., `541330`) |
| `naics_description` | `MAX(naics_description)` | Human-readable description |
| `total_companies` | `COUNT(DISTINCT recipient_uei)` | Unique companies that won contracts |
| `total_awards` | `COUNT(DISTINCT contract_award_unique_key)` | Total distinct awards |
| `total_transactions` | `COUNT(*)` | Total transaction rows |
| `total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | Total dollars obligated |
| `average_award_value` | `total_obligated / NULLIF(total_awards, 0)` | Average obligation per distinct award |
| `median_award_value` | `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | Median per-transaction obligation |
| `first_time_awardee_companies` | `COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE)` | Companies with exactly 1 award |
| `repeat_awardee_companies` | `total_companies - first_time_awardee_companies` | Companies with 2+ awards |
| `repeat_awardee_total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = FALSE)` | Dollars from repeat awardees |
| `repeat_awardee_avg_awards` | See CTE note below | Avg awards per repeat awardee company |

**SQL note on `repeat_awardee_avg_awards`:** The view has `total_awards_count` denormalized onto every transaction row. To get the average awards per repeat-awardee company within a NAICS, use a CTE that first deduplicates to one row per `(naics_code, recipient_uei)` for repeat awardees, then averages `total_awards_count` per NAICS. Do NOT average across transaction rows — that weights companies by transaction count.

```sql
WITH base AS (
    SELECT
        naics_code,
        MAX(naics_description) AS naics_description,
        COUNT(DISTINCT recipient_uei) AS total_companies,
        COUNT(DISTINCT contract_award_unique_key) AS total_awards,
        COUNT(*) AS total_transactions,
        SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS total_obligated,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) AS median_award_value,
        COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE) AS first_time_awardee_companies,
        SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC)) FILTER (WHERE is_first_time_awardee = FALSE) AS repeat_awardee_total_obligated
    FROM entities.mv_federal_contract_leads
    -- WHERE clauses from filters go here
    GROUP BY naics_code
),
repeat_avg AS (
    SELECT
        naics_code,
        AVG(total_awards_count) AS avg_awards_per_repeat_company
    FROM (
        SELECT DISTINCT naics_code, recipient_uei, total_awards_count
        FROM entities.mv_federal_contract_leads
        WHERE is_first_time_awardee = FALSE
        -- Same WHERE clauses from filters go here
    ) sub
    GROUP BY naics_code
)
SELECT
    base.*,
    base.total_obligated / NULLIF(base.total_awards, 0) AS average_award_value,
    base.total_companies - base.first_time_awardee_companies AS repeat_awardee_companies,
    repeat_avg.avg_awards_per_repeat_company AS repeat_awardee_avg_awards,
    COUNT(*) OVER() AS total_matched
FROM base
LEFT JOIN repeat_avg USING (naics_code)
ORDER BY total_obligated DESC
LIMIT %s OFFSET %s
```

**Filters:**

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `naics_prefix` | `str` | `naics_code LIKE %s` with `{value}%` — narrows to sector/subsector (e.g., `"31"` for manufacturing, `"2362"` for nonresidential construction) |
| `state` | `str` | `recipient_state_code = %s` |
| `min_companies` | `int` | `HAVING COUNT(DISTINCT recipient_uei) >= %s` — filter out tiny NAICS codes |
| `business_size` | `str` | `contracting_officers_determination_of_business_size = %s` |

**Important:** When filters are applied, they must be applied in BOTH the `base` CTE and the `repeat_avg` subquery so the numbers stay consistent.

**Pagination:** `COUNT(*) OVER()` for `total_matched`. Default `ORDER BY total_obligated DESC`. `LIMIT`/`OFFSET`.

**Return format:**
```python
{
    "items": [ ... ],
    "total_matched": 847,
    "limit": 100,
    "offset": 0,
}
```

All numeric fields: `float()` with `None` → `0.0` fallback. All filter values parameterized via `%s`.

#### Function 2: `get_naics_agency_breakdown`

**`get_naics_agency_breakdown(*, naics_code: str) -> list[dict[str, Any]]`**

For a single NAICS code, return one row per awarding agency (7 fields):

| Field | SQL | Description |
|---|---|---|
| `awarding_agency_code` | `awarding_agency_code` | 3-digit CGAC code |
| `awarding_agency_name` | `MAX(awarding_agency_name)` | Agency name |
| `total_companies` | `COUNT(DISTINCT recipient_uei)` | Unique companies |
| `total_awards` | `COUNT(DISTINCT contract_award_unique_key)` | Distinct awards |
| `total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | Dollars obligated |
| `first_time_awardee_companies` | `COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE)` | First-timers |
| `repeat_awardee_companies` | `total_companies - first_time_awardee_companies` | Repeaters |

`WHERE naics_code = %s`. Order by `total_obligated DESC`.

Commit standalone.

---

### Deliverable 2: Time Series Analytics Service

Create `app/services/federal_leads_analytics.py`.

Shares the same connection pool pattern. **All functions in Deliverables 2-4 go in this one file.**

#### Function 1: `get_time_series`

**`get_time_series(*, period: str = "quarter", filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Groups metrics by time period. The `period` parameter accepts `"month"` or `"quarter"`.

**Time bucketing from `action_date` (TEXT, YYYY-MM-DD format):**
- Month: `TO_CHAR(action_date::DATE, 'YYYY-MM')` → e.g., `"2025-11"`
- Quarter: `TO_CHAR(action_date::DATE, 'YYYY-"Q"Q')` → e.g., `"2025-Q4"`

**Output fields per row (9 fields):**

| Field | SQL | Description |
|---|---|---|
| `period` | Time bucket expression | `"2025-Q4"` or `"2025-11"` |
| `total_companies` | `COUNT(DISTINCT recipient_uei)` | Unique companies active in this period |
| `total_awards` | `COUNT(DISTINCT contract_award_unique_key)` | Distinct awards |
| `total_transactions` | `COUNT(*)` | Transaction rows |
| `total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | Dollars obligated |
| `average_award_value` | `total_obligated / NULLIF(total_awards, 0)` | Avg obligation per award |
| `first_time_awardee_companies` | `COUNT(DISTINCT recipient_uei) FILTER (WHERE is_first_time_awardee = TRUE)` | New entrants this period |
| `repeat_awardee_companies` | `total_companies - first_time_awardee_companies` | Repeaters |
| `new_entrant_pct` | `first_time_awardee_companies::NUMERIC / NULLIF(total_companies, 0) * 100` | % of companies that are first-timers |

Order by `period ASC`.

**Filters (same as NAICS metrics, applied as WHERE clauses):**

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `naics_prefix` | `str` | `naics_code LIKE %s` with `{value}%` |
| `state` | `str` | `recipient_state_code = %s` |
| `business_size` | `str` | `contracting_officers_determination_of_business_size = %s` |
| `awarding_agency_code` | `str` | `awarding_agency_code = %s` |

**Sharp angle this enables:** _"Manufacturing awards are up 23% quarter-over-quarter — 127 new companies won their first contract in Q1 2026."_

#### Function 2: `get_award_size_distribution`

**`get_award_size_distribution(*, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Groups by NAICS vertical (same 7-bucket CASE WHEN as `federal_leads_verticals.py`) AND award size bucket.

**Size buckets (on `federal_action_obligation` cast to NUMERIC):**

```sql
CASE
    WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 100000 THEN 'Under $100K'
    WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 500000 THEN '$100K–$500K'
    WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 1000000 THEN '$500K–$1M'
    WHEN CAST(NULLIF(federal_action_obligation, '') AS NUMERIC) < 5000000 THEN '$1M–$5M'
    ELSE '$5M+'
END AS size_bucket
```

**Output fields per row (7 fields):**

| Field | SQL | Description |
|---|---|---|
| `vertical` | CASE WHEN on naics_code (same 7 buckets) | Broad vertical label |
| `size_bucket` | CASE WHEN above | Dollar range label |
| `transaction_count` | `COUNT(*)` | Transactions in this bucket |
| `unique_companies` | `COUNT(DISTINCT recipient_uei)` | Companies in this bucket |
| `total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | Dollars in this bucket |
| `pct_of_vertical_transactions` | `COUNT(*)::NUMERIC / NULLIF(SUM(COUNT(*)) OVER (PARTITION BY vertical), 0) * 100` | % of vertical's transactions |
| `pct_of_vertical_dollars` | Similar window function on total_obligated | % of vertical's dollars |

Order by `vertical ASC, size_bucket` (use a CASE to get logical bucket ordering: Under $100K=1, $100K–$500K=2, etc.).

**Filters:** Same as time series (`naics_prefix`, `state`, `business_size`, `awarding_agency_code`).

**Sharp angle this enables:** _"68% of construction contract transactions are under $500K — the sweet spot for small business insurance."_

#### Function 3: `get_set_aside_breakdown`

**`get_set_aside_breakdown(*, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Groups by NAICS vertical AND `type_of_set_aside`.

**Output fields per row (6 fields):**

| Field | SQL | Description |
|---|---|---|
| `vertical` | CASE WHEN on naics_code | Broad vertical label |
| `set_aside_type` | `COALESCE(NULLIF(type_of_set_aside, ''), 'NONE')` | Set-aside type (e.g., `SBA`, `8A`, `HZC`, `SDVOSBC`, `WOSB`, `NONE`) |
| `transaction_count` | `COUNT(*)` | Transactions with this set-aside |
| `unique_companies` | `COUNT(DISTINCT recipient_uei)` | Companies |
| `total_obligated` | `SUM(...)` | Dollars |
| `pct_of_vertical_transactions` | Window function | % of vertical's transactions |

Order by `vertical ASC, total_obligated DESC`.

**Filters:** Same as above.

**Sharp angle this enables:** _"42% of IT services awards are set aside for small business — if you're not positioned as small business, you're missing nearly half the market."_

#### Function 4: `get_competition_metrics`

**`get_competition_metrics(*, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Groups by NAICS vertical. Analyzes competition level.

**Output fields per row (8 fields):**

| Field | SQL | Description |
|---|---|---|
| `vertical` | CASE WHEN | Broad vertical label |
| `total_awards` | `COUNT(DISTINCT contract_award_unique_key)` | Awards |
| `avg_offers_received` | `AVG(CAST(NULLIF(number_of_offers_received, '') AS NUMERIC))` | Average bids per award |
| `median_offers_received` | `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(number_of_offers_received, '') AS NUMERIC))` | Median bids |
| `sole_source_count` | `COUNT(*) FILTER (WHERE extent_competed IN ('NOT COMPETED UNDER SAP', 'NOT AVAILABLE FOR COMPETITION', 'NOT COMPETED'))` | Sole-source transactions |
| `sole_source_pct` | `sole_source_count::NUMERIC / NULLIF(COUNT(*), 0) * 100` | % sole-source |
| `full_competition_count` | `COUNT(*) FILTER (WHERE extent_competed = 'FULL AND OPEN COMPETITION')` | Fully competed transactions |
| `full_competition_pct` | Percentage | % fully competed |

Order by `total_awards DESC`.

**Filters:** Same as above.

**Note on `extent_competed` values:** The exact string values in USASpending may vary. The executor should check a `SELECT DISTINCT extent_competed` sample from the view (using a quick ad-hoc query against the DB or by inspecting the USASpending column docs) and adjust the FILTER conditions to match actual values. The categories above are directionally correct but may need literal adjustments.

**Sharp angle this enables:** _"31% of healthcare awards were sole-source — the relationships matter more than the bid."_

#### Function 5: `get_geographic_hotspots`

**`get_geographic_hotspots(*, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Groups by `recipient_state_code`. Returns per-state metrics.

**Output fields per row (7 fields):**

| Field | SQL | Description |
|---|---|---|
| `state` | `recipient_state_code` | 2-letter state code |
| `total_companies` | `COUNT(DISTINCT recipient_uei)` | Unique companies |
| `total_awards` | `COUNT(DISTINCT contract_award_unique_key)` | Awards |
| `total_obligated` | `SUM(...)` | Dollars |
| `first_time_awardee_companies` | `COUNT(DISTINCT ...) FILTER (...)` | First-timers |
| `pct_first_time` | Percentage | % first-timers |
| `avg_award_value` | `total_obligated / NULLIF(total_awards, 0)` | Avg award |

Order by `total_obligated DESC`.

**Filters:** `naics_prefix`, `business_size`, `awarding_agency_code` (no `state` filter — state IS the dimension here).

**Sharp angle this enables:** _"Texas had 340 first-time manufacturing awardees last year — that's 340 companies that just got their first government check and need new insurance/services/compliance."_

Commit standalone.

---

### Deliverable 3: Repeat Awardee Velocity Service

Add to `app/services/federal_leads_analytics.py`.

#### Function 6: `get_repeat_awardee_velocity`

**`get_repeat_awardee_velocity(*, filters: dict[str, Any] | None = None) -> dict[str, Any]`**

Computes the time gap between a company's first and second distinct award. This is a heavier query — it identifies repeat awardees, finds their two earliest distinct award dates, and computes the gap distribution.

**SQL approach:**

```sql
WITH company_awards AS (
    -- One row per (company, award) with the earliest action_date for that award
    SELECT
        recipient_uei,
        contract_award_unique_key,
        MIN(action_date::DATE) AS award_date
    FROM entities.mv_federal_contract_leads
    WHERE is_first_time_awardee = FALSE
      AND recipient_uei IS NOT NULL AND recipient_uei != ''
      AND action_date IS NOT NULL AND action_date != ''
      -- Filters go here
    GROUP BY recipient_uei, contract_award_unique_key
),
ranked AS (
    SELECT
        recipient_uei,
        award_date,
        ROW_NUMBER() OVER (PARTITION BY recipient_uei ORDER BY award_date) AS award_rank
    FROM company_awards
),
velocity AS (
    SELECT
        r1.recipient_uei,
        r1.award_date AS first_award_date,
        r2.award_date AS second_award_date,
        (r2.award_date - r1.award_date) AS days_between
    FROM ranked r1
    JOIN ranked r2 ON r1.recipient_uei = r2.recipient_uei
    WHERE r1.award_rank = 1 AND r2.award_rank = 2
)
SELECT
    COUNT(*) AS companies_measured,
    AVG(days_between)::NUMERIC AS avg_days_between,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY days_between) AS median_days_between,
    PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY days_between) AS p25_days_between,
    PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY days_between) AS p75_days_between,
    MIN(days_between) AS min_days_between,
    MAX(days_between) AS max_days_between,
    COUNT(*) FILTER (WHERE days_between <= 90) AS within_90_days,
    COUNT(*) FILTER (WHERE days_between BETWEEN 91 AND 180) AS within_91_180_days,
    COUNT(*) FILTER (WHERE days_between BETWEEN 181 AND 365) AS within_181_365_days,
    COUNT(*) FILTER (WHERE days_between > 365) AS over_365_days
FROM velocity
```

**Return format:**

```python
{
    "companies_measured": 12286,
    "avg_days_between": 147.3,
    "median_days_between": 98.0,
    "p25_days_between": 42.0,
    "p75_days_between": 213.0,
    "min_days_between": 0,
    "max_days_between": 1826,
    "distribution": {
        "within_90_days": 4102,
        "within_91_180_days": 3244,
        "within_181_365_days": 2891,
        "over_365_days": 2049,
    },
}
```

**Filters:** Same set (`naics_prefix`, `state`, `business_size`, `awarding_agency_code`). Applied inside the `company_awards` CTE.

**Performance note:** This query does a self-join on ranked results. On 1.34M rows it may take several seconds. Set statement timeout to 60s for this function. If the executor finds it's too slow, adding `LIMIT 50000` on the `company_awards` CTE (by most recent awards) is an acceptable tradeoff — document it in the return payload as `"scope": "latest_50k_awards"`.

**Sharp angle this enables:** _"The median time from first to second federal contract is 98 days — your window to get in front of new awardees is roughly 3 months."_

#### Function 7: `get_award_ceiling_gap`

**`get_award_ceiling_gap(*, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]`**

Compares `federal_action_obligation` (what's been spent) vs `potential_total_value_of_award` (the contract ceiling) per NAICS vertical. This shows how much expansion opportunity exists.

**Output fields per row (7 fields):**

| Field | SQL | Description |
|---|---|---|
| `vertical` | CASE WHEN | Broad vertical label |
| `total_obligated` | `SUM(CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` | What's been spent |
| `total_ceiling` | `SUM(CAST(NULLIF(potential_total_value_of_award, '') AS NUMERIC))` | Contract ceiling |
| `ceiling_to_obligation_ratio` | `total_ceiling / NULLIF(total_obligated, 0)` | How much runway (e.g., 3.2x) |
| `avg_obligation_per_company` | `total_obligated / NULLIF(COUNT(DISTINCT recipient_uei), 0)` | Avg spend per company |
| `avg_ceiling_per_company` | `total_ceiling / NULLIF(COUNT(DISTINCT recipient_uei), 0)` | Avg ceiling per company |
| `unique_companies` | `COUNT(DISTINCT recipient_uei)` | Companies |

Order by `ceiling_to_obligation_ratio DESC`.

**Filters:** Same set.

**Sharp angle this enables:** _"The average manufacturing contract has a $2.1M ceiling but only $340K obligated — that's 6x expansion runway. These companies are growing."_

Commit standalone.

---

### Deliverable 4: Wire All Endpoints

Add all new endpoints to `app/routers/entities_v1.py`.

**Shared request model for analytics endpoints (reuse across multiple endpoints):**

```python
class FederalAnalyticsFilters(BaseModel):
    naics_prefix: str | None = None
    state: str | None = None
    business_size: str | None = None
    awarding_agency_code: str | None = None
```

#### Endpoint List (8 total)

| # | Method | Path | Service Function | Request Model | Notes |
|---|---|---|---|---|---|
| 1 | POST | `/api/v1/federal-contract-leads/naics-metrics` | `get_naics_metrics` | `NaicsMetricsRequest` (filters + limit + offset) | Paginated |
| 2 | POST | `/api/v1/federal-contract-leads/naics-metrics/{naics_code}/agencies` | `get_naics_agency_breakdown` | None (path param only) | |
| 3 | POST | `/api/v1/federal-contract-leads/analytics/time-series` | `get_time_series` | `FederalAnalyticsFilters` + `period: str = "quarter"` | |
| 4 | POST | `/api/v1/federal-contract-leads/analytics/size-distribution` | `get_award_size_distribution` | `FederalAnalyticsFilters` | |
| 5 | POST | `/api/v1/federal-contract-leads/analytics/set-asides` | `get_set_aside_breakdown` | `FederalAnalyticsFilters` | |
| 6 | POST | `/api/v1/federal-contract-leads/analytics/competition` | `get_competition_metrics` | `FederalAnalyticsFilters` | |
| 7 | POST | `/api/v1/federal-contract-leads/analytics/geographic` | `get_geographic_hotspots` | `FederalAnalyticsFilters` (no `state`) | |
| 8 | POST | `/api/v1/federal-contract-leads/analytics/repeat-velocity` | `get_repeat_awardee_velocity` | `FederalAnalyticsFilters` | |
| 9 | POST | `/api/v1/federal-contract-leads/analytics/ceiling-gap` | `get_award_ceiling_gap` | `FederalAnalyticsFilters` | |

All endpoints: Auth via `_resolve_flexible_auth`. Response: `DataEnvelope` wrapping the service return value.

**Request models:**

```python
class NaicsMetricsRequest(BaseModel):
    naics_prefix: str | None = None
    state: str | None = None
    min_companies: int | None = None
    business_size: str | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

class FederalAnalyticsFilters(BaseModel):
    naics_prefix: str | None = None
    state: str | None = None
    business_size: str | None = None
    awarding_agency_code: str | None = None

class TimeSeriesRequest(FederalAnalyticsFilters):
    period: str = Field(default="quarter", pattern="^(month|quarter)$")

class GeographicRequest(BaseModel):
    """No state filter — state IS the dimension."""
    naics_prefix: str | None = None
    business_size: str | None = None
    awarding_agency_code: str | None = None
```

Commit standalone.

---

### Deliverable 5: Tests

Create `tests/test_federal_leads_naics_metrics.py`.

**NAICS metrics service tests (12):**
1. Default query returns paginated results with all 12 metric fields present
2. `naics_prefix` filter generates LIKE clause
3. `state` filter generates exact match
4. `min_companies` filter generates HAVING clause
5. `business_size` filter generates exact match
6. Multiple filters combine correctly
7. Pagination `limit` / `offset` / `total_matched` work correctly
8. NULL/empty `federal_action_obligation` values don't cause errors (return 0.0)
9. `repeat_awardee_avg_awards` is computed correctly (not weighted by transaction count)
10. `median_award_value` handles NULL values

**Agency breakdown tests (4):**
11. Returns list of agency dicts with all 7 fields
12. Results ordered by `total_obligated` DESC
13. `first_time_awardee_companies + repeat_awardee_companies = total_companies`
14. Empty NAICS code returns empty list

Create `tests/test_federal_leads_analytics.py`.

**Time series tests (4):**
15. Quarter period returns `YYYY-QN` format, ordered ASC
16. Month period returns `YYYY-MM` format, ordered ASC
17. `new_entrant_pct` is between 0 and 100
18. Filters narrow the result set

**Size distribution tests (4):**
19. Returns all 5 size buckets per vertical
20. `pct_of_vertical_transactions` sums to ~100 within each vertical
21. Buckets are in logical order (Under $100K first, $5M+ last)
22. NULL obligation values don't cause errors

**Set-aside tests (3):**
23. Returns rows grouped by vertical + set_aside_type
24. `NONE` category exists for awards with no set-aside
25. Percentages are non-negative

**Competition tests (3):**
26. `sole_source_pct + full_competition_pct` ≤ 100 (may not sum to 100 — other categories exist)
27. `avg_offers_received` is a positive number
28. Results ordered by total_awards DESC

**Geographic tests (3):**
29. Returns rows with 2-letter state codes
30. No `state` filter accepted (state IS the dimension)
31. `pct_first_time` is between 0 and 100

**Repeat velocity tests (4):**
32. Returns `companies_measured`, all percentile fields, and distribution buckets
33. `distribution` bucket counts sum to `companies_measured`
34. `p25 <= median <= p75`
35. Filters narrow the companies measured

**Ceiling gap tests (3):**
36. Returns one row per vertical
37. `ceiling_to_obligation_ratio` ≥ 0
38. `total_ceiling >= total_obligated` (generally true — edge cases with negative modifications are acceptable)

**Endpoint tests (5):**
39. All 9 endpoints return correct `DataEnvelope` response shape
40. Auth required on all endpoints
41. Time series rejects invalid `period` values
42. Geographic endpoint doesn't accept `state` filter
43. NAICS agency breakdown accepts path parameter

All tests mock database calls. Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No materialized view changes.** All needed columns already exist.
- **No schema migrations.**
- **No modifications to existing endpoints.** The existing `/verticals`, `/query`, `/stats`, `/export`, company detail endpoints stay as-is.
- **No Trigger.dev tasks.**
- **No deploy commands.** Do not push.
- **No caching layer.** Some of these queries are heavy — caching is future work.
- **No frontend/dashboard.** These are API-only data endpoints.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) NAICS metrics: field count per row, SQL approach for `repeat_awardee_avg_awards`, median handling, filter count
(b) Analytics service: all 7 function names, field counts per function, any `extent_competed` value adjustments made
(c) Repeat velocity: SQL approach, performance (did it need the 50K limit?), actual percentile values if you ran a quick check
(d) Endpoints: all 9 paths, auth on each, request model per endpoint
(e) Tests: total count across both test files, all passing
(f) Anything to flag — especially: query performance on heavy aggregations, any columns that had unexpected NULL/empty rates, and whether `extent_competed` values matched the directive or needed adjustment
