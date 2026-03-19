# Executor Directive: Federal Leads Query Endpoints (SBA Query, CSV Export, Company Detail, Verticals)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Three federal data sources are loaded and a materialized view (`entities.mv_federal_contract_leads`) joins USASpending to SAM.gov. We now need four additional read-only query endpoints: an SBA loan query, a CSV export for the federal leads view, a company detail endpoint that aggregates all three data sources by UEI, and a vertical summary endpoint.

All four endpoints are read-only — no writes, no ingestion, no data mutation.

---

## Reference Documents (Read Before Starting)

**Must read — existing query code (your primary pattern reference):**
- `app/services/federal_leads_query.py` — Query service with parameterized psycopg queries, `COUNT(*) OVER()` pagination, connection pool pattern
- `app/services/federal_leads_refresh.py` — Connection pool pattern, stats query
- `app/routers/entities_v1.py` — Endpoint wiring, `FederalContractLeadsQueryRequest` model, `_resolve_flexible_auth`, `DataEnvelope` response

**Must read — table schemas:**
- `supabase/migrations/032_sba_7a_loans.sql` — SBA table (43 TEXT columns + metadata)
- `supabase/migrations/034_mv_federal_contract_leads_agency_first_time.sql` — Materialized view definition (63 columns)

**Must read — column maps:**
- `app/services/sba_column_map.py` — SBA 43-column map with descriptions

---

## Deliverables

### Deliverable 1: SBA 7(a) Loans Query Service + Endpoint

Create `app/services/sba_query.py`.

Follow the exact same pattern as `app/services/federal_leads_query.py`:

**`query_sba_loans(*, filters: dict[str, Any], limit: int = 25, offset: int = 0) -> dict[str, Any]`**

- Dedicated `psycopg_pool.ConnectionPool` (same pattern: module-level singleton, threading lock)
- Queries `entities.sba_7a_loans` directly
- `COUNT(*) OVER() AS total_matched` window function
- `ORDER BY approvaldate DESC` default ordering
- `LIMIT` / `OFFSET` pagination
- Returns `{ items: [...], total_matched: int, limit: int, offset: int }`
- All filter values parameterized via `%s` — no string interpolation

Supported filters:

| Filter Key | Type | SQL Behavior |
|---|---|---|
| `naics_prefix` | `str` | `naicscode LIKE %s` with `{value}%` |
| `state` | `str` | `borrstate = %s` (2-letter) |
| `min_loan_amount` | `str` | `CAST(grossapproval AS NUMERIC) >= %s` |
| `max_loan_amount` | `str` | `CAST(grossapproval AS NUMERIC) <= %s` |
| `approval_date_from` | `str` | `approvaldate >= %s` (note: SBA dates are `MM/DD/YYYY` format stored as TEXT — cast to date for comparison: `TO_DATE(approvaldate, 'MM/DD/YYYY') >= %s::DATE`) |
| `approval_date_to` | `str` | `TO_DATE(approvaldate, 'MM/DD/YYYY') <= %s::DATE` |
| `business_age` | `str` | `businessage = %s` — values like `Existing or more than 2 years old`, `New Business or 2 years or less`, `Startup, Loan Funds will Open Business`, `Change of Ownership` |
| `business_type` | `str` | `businesstype = %s` — values like `CORPORATION`, `INDIVIDUAL`, `PARTNERSHIP`, `LLC` |
| `lender_name` | `str` | `bankname ILIKE %s` with `%{value}%` |
| `loan_status` | `str` | `loanstatus = %s` — values like `EXEMPT`, `PIF` (paid in full), `CHGOFF` (charged off) |
| `borrower_name` | `str` | `borrname ILIKE %s` with `%{value}%` |
| `min_jobs` | `str` | `CAST(jobssupported AS INTEGER) >= %s` |

Wire endpoint in `app/routers/entities_v1.py`:

**`POST /api/v1/sba-loans/query`**

Auth: `_resolve_flexible_auth` (tenant JWT or super-admin).

Request model:
```python
class SbaLoansQueryRequest(BaseModel):
    naics_prefix: str | None = None
    state: str | None = None
    min_loan_amount: str | None = None
    max_loan_amount: str | None = None
    approval_date_from: str | None = None
    approval_date_to: str | None = None
    business_age: str | None = None
    business_type: str | None = None
    lender_name: str | None = None
    loan_status: str | None = None
    borrower_name: str | None = None
    min_jobs: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
```

Response: `DataEnvelope` wrapping the query result.

Also add a stats endpoint:

**`POST /api/v1/sba-loans/stats`**

Returns aggregate stats: total rows, unique borrowers (distinct `borrname`), total loan volume (`SUM(CAST(grossapproval AS NUMERIC))`), distinct NAICS codes, distinct states.

Commit standalone.

---

### Deliverable 2: CSV Export Endpoint for Federal Contract Leads

Create `app/services/federal_leads_export.py`.

**`stream_federal_contract_leads_csv(*, filters: dict[str, Any]) -> Iterator[str]`**

- Uses the same filter logic as `query_federal_contract_leads()` to build the WHERE clause
- Does NOT use `LIMIT`/`OFFSET` — returns all matching rows
- Uses a server-side cursor (`cur.itersize = 5000` or `cur.execute()` with chunked fetching) to avoid loading all rows into memory
- Yields CSV lines: header row first, then one line per result row
- Include all columns from the materialized view (all 63 columns from migration 034)
- Values are raw TEXT — no transformation, no quoting beyond standard `csv.writer` behavior

Wire endpoint in `app/routers/entities_v1.py`:

**`POST /api/v1/federal-contract-leads/export`**

Auth: `_resolve_flexible_auth`.

Request model: Reuse `FederalContractLeadsQueryRequest` (same 15 filter parameters). Ignore `limit` and `offset` fields — export returns all matches.

Response: `StreamingResponse` with `media_type="text/csv"` and `Content-Disposition: attachment; filename="federal_contract_leads_export.csv"`.

Implementation:
```python
from fastapi.responses import StreamingResponse
import csv
import io

# In the endpoint:
def csv_generator():
    for line in stream_federal_contract_leads_csv(filters=filters):
        yield line

return StreamingResponse(
    csv_generator(),
    media_type="text/csv",
    headers={"Content-Disposition": "attachment; filename=federal_contract_leads_export.csv"},
)
```

**Safety:** Add a `max_rows` parameter (default 100,000) to the service function. If the query would return more rows than `max_rows`, raise a `ValueError` with the actual count. The endpoint should return 422 with a message like `"Export exceeds 100,000 rows. Add filters to narrow results."` The caller can override with a request body field `max_rows: int = 100_000`.

Commit standalone.

---

### Deliverable 3: Company Detail Endpoint

Create `app/services/federal_leads_company_detail.py`.

**`get_company_detail(*, uei: str) -> dict[str, Any] | None`**

This aggregates data from all three tables for a single company:

1. **SAM.gov registration:** Query `entities.sam_gov_entities` for the latest snapshot where `unique_entity_id = {uei}`. Return the full row (all 142 columns). If no match, this section is `null`.

2. **USASpending awards:** Query `entities.usaspending_contracts` for all rows where `recipient_uei = {uei}` (latest snapshot only — `DISTINCT ON (contract_transaction_unique_key)` ordered by `extract_date DESC`). Return as a list ordered by `action_date DESC`. Include: `contract_award_unique_key`, `award_type`, `action_date`, `federal_action_obligation`, `total_dollars_obligated`, `potential_total_value_of_award`, `awarding_agency_name`, `naics_code`, `naics_description`, `usaspending_permalink`. Also return summary stats: `total_awards` (distinct `contract_award_unique_key`), `total_obligated` (sum of `federal_action_obligation` cast to numeric), `earliest_action_date`, `latest_action_date`.

3. **SBA loans (fuzzy match):** Query `entities.sba_7a_loans` for rows where `borrstate` matches SAM.gov's `physical_address_province_or_state` (or USASpending's `recipient_state_code` if no SAM match) AND `borrname ILIKE '%{company_name}%'` using the first significant word(s) from the company name. This is a best-effort fuzzy match. Return as a list. If no fuzzy match found, this section is an empty list.

   **Fuzzy match approach:** Extract the company name from SAM.gov `legal_business_name` (preferred) or USASpending `recipient_name`. Strip common suffixes (`INC`, `LLC`, `CORP`, `CO`, `LTD`, `LP`, `GROUP`). Use the remaining core name for an ILIKE search. Example: `THE MATTHEWS GROUP INC` → search `borrname ILIKE '%MATTHEWS%'` with `borrstate = 'VA'`. This will produce false positives — that's acceptable for a best-effort match. The response should include a `sba_match_method: "fuzzy_name_state"` field so the caller knows the match is approximate.

4. **Return structure:**
```python
{
    "uei": "GHDAN1FNERA8",
    "sam_registration": { ... } | None,       # Full SAM.gov row
    "awards": {
        "items": [ ... ],                      # List of award transactions
        "total_awards": 3,
        "total_obligated": 1500000.00,
        "earliest_action_date": "2024-01-15",
        "latest_action_date": "2025-11-03",
    },
    "sba_loans": {
        "items": [ ... ],                      # List of fuzzy-matched SBA loans
        "match_method": "fuzzy_name_state",
        "search_name": "MATTHEWS",
        "search_state": "VA",
    },
}
```

Wire endpoint in `app/routers/entities_v1.py`:

**`GET /api/v1/federal-contract-leads/{uei}`**

Auth: `_resolve_flexible_auth`.

Path parameter: `uei` (string, 12-char alphanumeric).

Response: `DataEnvelope` wrapping the company detail dict. Return 404 if UEI not found in either SAM.gov or USASpending.

Commit standalone.

---

### Deliverable 4: Vertical Summary Endpoint

Create `app/services/federal_leads_verticals.py`.

**`get_vertical_summary() -> list[dict[str, Any]]`**

Queries `entities.mv_federal_contract_leads` with a single aggregation query that categorizes rows by broad NAICS vertical:

| Vertical Label | NAICS Prefix(es) |
|---|---|
| Manufacturing | `31`, `32`, `33` |
| Construction | `23` |
| IT & Professional Services | `54` |
| Healthcare & Social Assistance | `62` |
| Transportation & Warehousing | `48`, `49` |
| Admin & Staffing Services | `56` |
| All Other | Everything else |

SQL approach — use a `CASE WHEN` expression:
```sql
CASE
    WHEN naics_code LIKE '31%' OR naics_code LIKE '32%' OR naics_code LIKE '33%' THEN 'Manufacturing'
    WHEN naics_code LIKE '23%' THEN 'Construction'
    WHEN naics_code LIKE '54%' THEN 'IT & Professional Services'
    WHEN naics_code LIKE '62%' THEN 'Healthcare & Social Assistance'
    WHEN naics_code LIKE '48%' OR naics_code LIKE '49%' THEN 'Transportation & Warehousing'
    WHEN naics_code LIKE '56%' THEN 'Admin & Staffing Services'
    ELSE 'All Other'
END AS vertical
```

For each vertical, return:

| Field | Description |
|---|---|
| `vertical` | Label string |
| `total_rows` | Count of transaction rows |
| `unique_companies` | Count of distinct `recipient_uei` |
| `first_time_awardees` | Count of distinct `recipient_uei` WHERE `is_first_time_awardee = TRUE` |
| `repeat_awardees` | `unique_companies - first_time_awardees` |
| `total_obligated` | `SUM(CAST(federal_action_obligation AS NUMERIC))` |

Order results by `total_rows DESC`.

Uses its own connection pool (same pattern).

Wire endpoint in `app/routers/entities_v1.py`:

**`GET /api/v1/federal-contract-leads/verticals`**

Auth: `_resolve_flexible_auth`.

No request body or parameters.

Response: `DataEnvelope` wrapping `{ verticals: [...] }`.

**Note on routing:** FastAPI matches routes in order. `GET /api/v1/federal-contract-leads/verticals` must be registered **before** `GET /api/v1/federal-contract-leads/{uei}` — otherwise `verticals` would be interpreted as a UEI path parameter. Place the `verticals` endpoint registration above the `{uei}` endpoint in the file.

Commit standalone.

---

### Deliverable 5: Tests

Create `tests/test_federal_leads_endpoints.py`.

1. **SBA query service tests:**
   - Default query returns paginated results
   - `naics_prefix` filter generates LIKE clause
   - `state` filter generates exact match
   - `min_loan_amount` / `max_loan_amount` cast to numeric
   - `approval_date_from` / `approval_date_to` use `TO_DATE` casting
   - `business_age` exact match
   - `business_type` exact match
   - `lender_name` generates ILIKE
   - `borrower_name` generates ILIKE
   - `min_jobs` casts to integer
   - Multiple filters combine with AND
   - Pagination works correctly

2. **CSV export tests:**
   - Export returns iterator of CSV lines
   - First line is header row
   - Filters are applied correctly
   - `max_rows` limit raises ValueError when exceeded

3. **Company detail tests:**
   - Returns SAM + USASpending + SBA sections
   - Returns 404 when UEI not found
   - SBA fuzzy match strips common suffixes
   - Works when only USASpending data exists (no SAM match)

4. **Vertical summary tests:**
   - Returns all 7 verticals
   - NAICS categorization is correct (e.g., `311710` → Manufacturing)
   - Counts are non-negative integers
   - `repeat_awardees = unique_companies - first_time_awardees`

5. **Endpoint tests:**
   - All 5 new endpoints return correct response shapes
   - Auth required on all endpoints
   - CSV export returns `text/csv` content type
   - GET `/{uei}` accepts path parameter
   - Route ordering: `/verticals` doesn't collide with `/{uei}`

All tests mock database calls. Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No data ingestion.** These are read-only query endpoints.
- **No materialized view changes.** The existing view is sufficient.
- **No schema migrations.** All tables already exist.
- **No Trigger.dev tasks.**
- **No deploy commands.** Do not push.
- **No modifications to existing endpoints.** The existing `/query`, `/stats`, and `/refresh` endpoints stay as-is.
- **No caching layer.** The vertical summary could benefit from caching but that's future work.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) SBA query: filter count, parameterization approach, stats query fields
(b) CSV export: streaming approach, max_rows safety, column count in header
(c) Company detail: SAM/USASpending/SBA sections, fuzzy match approach, suffix stripping
(d) Vertical summary: number of verticals, NAICS mapping, aggregation fields
(e) Tests: total count, all passing
(f) Endpoint summary: all 5 new paths, auth on each, HTTP method
(g) Anything to flag — especially route ordering for GET paths
