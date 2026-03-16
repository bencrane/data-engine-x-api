# Executor Directive: USASpending + SAM.gov Federal Contract Leads View & Query Endpoint

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Three federal bulk data sources are now loaded in `entities` schema:

| Table | Rows | Key Field |
|---|---|---|
| `entities.sam_gov_entities` | 867,137 | `unique_entity_id` (UEI) |
| `entities.usaspending_contracts` | 1,340,862 | `recipient_uei` (UEI) |
| `entities.sba_7a_loans` | 356,386 | No UEI — standalone |

The join key between USASpending and SAM.gov is `recipient_uei` = `unique_entity_id` (12-char alphanumeric UEI). This directive creates a materialized view that joins them into queryable lead records for outbound campaigns, plus a FastAPI query endpoint with filter parameters.

SBA 7(a) has no shared identifier with the other two tables. It remains a separate, independently queryable lead pool and is **not part of this directive**.

---

## Reference Documents (Read Before Starting)

**Must read — table schemas:**
- `supabase/migrations/030_sam_gov_entities.sql` — SAM.gov table definition (142 TEXT columns)
- `supabase/migrations/031_usaspending_contracts.sql` — USASpending table definition (297 TEXT columns)

**Must read — column maps (for exact column names):**
- `app/services/sam_gov_column_map.py` — SAM.gov column definitions
- `app/services/usaspending_column_map.py` — USASpending column definitions

**Must read — schema comprehension docs:**
- `docs/USASPENDING_EXTRACT_SCHEMA_COMPREHENSION.md` — USASpending field descriptions, data types, business size fields
- `docs/SAM_GOV_ENTITY_EXTRACT_INGEST_REPORT.md` — SAM.gov field descriptions

**Must read — existing query patterns:**
- `app/services/leads_query.py` — Existing RPC-based leads query pattern
- `app/routers/entities_v1.py` — Existing query endpoint patterns (request models, auth, pagination)

---

## Join Specification

```sql
entities.usaspending_contracts u
LEFT JOIN entities.sam_gov_entities s
    ON u.recipient_uei = s.unique_entity_id
```

**LEFT JOIN, not INNER.** Some USASpending records may have UEIs that don't match SAM.gov (inactive registrations, expired entities). Those records still have value — they have recipient name, address, and award data from USASpending itself. SAM.gov enriches with POC names, entity URL, and business type details, but the lead record is useful even without that enrichment.

**Snapshot handling:** Both tables support multiple snapshots (`extract_date`). The view should use only the **latest snapshot** from each table:
- For SAM.gov: the row with `MAX(extract_date)` per `unique_entity_id`
- For USASpending: the row with `MAX(extract_date)` per `contract_transaction_unique_key`

Use CTEs or subqueries to select latest-snapshot rows before joining.

---

## Materialized View Design

### View name: `entities.mv_federal_contract_leads`

### Output columns

The view should produce these columns (all TEXT unless noted — cast at query time in the endpoint, not in the view):

**From USASpending (`u` alias):**

| Output Column | Source Column | Notes |
|---|---|---|
| `contract_transaction_unique_key` | `u.contract_transaction_unique_key` | Row identity |
| `contract_award_unique_key` | `u.contract_award_unique_key` | Award grouping |
| `recipient_uei` | `u.recipient_uei` | Join key / UEI |
| `recipient_name` | `u.recipient_name` | Company name (standardized) |
| `recipient_address_line_1` | `u.recipient_address_line_1` | Address |
| `recipient_city_name` | `u.recipient_city_name` | City |
| `recipient_state_code` | `u.recipient_state_code` | State (2-letter) |
| `recipient_zip_4_code` | `u.recipient_zip_4_code` | ZIP |
| `recipient_country_code` | `u.recipient_country_code` | Country |
| `recipient_phone_number` | `u.recipient_phone_number` | Phone |
| `award_type` | `u.award_type` | DEFINITIVE CONTRACT, BPA CALL, etc. |
| `action_date` | `u.action_date` | Award action date (YYYY-MM-DD) |
| `federal_action_obligation` | `u.federal_action_obligation` | Per-action dollar amount |
| `total_dollars_obligated` | `u.total_dollars_obligated` | Cumulative obligation |
| `potential_total_value_of_award` | `u.potential_total_value_of_award` | Contract ceiling |
| `awarding_agency_code` | `u.awarding_agency_code` | Agency code |
| `awarding_agency_name` | `u.awarding_agency_name` | Agency name |
| `awarding_sub_agency_name` | `u.awarding_sub_agency_name` | Sub-agency |
| `naics_code` | `u.naics_code` | 6-digit NAICS |
| `naics_description` | `u.naics_description` | NAICS description |
| `product_or_service_code` | `u.product_or_service_code` | PSC code |
| `product_or_service_code_description` | `u.product_or_service_code_description` | PSC description |
| `contracting_officers_determination_of_business_size` | `u.contracting_officers_determination_of_business_size` | `SMALL BUSINESS` or `OTHER THAN SMALL BUSINESS` |
| `type_of_set_aside` | `u.type_of_set_aside` | Set-aside designation |
| `extent_competed` | `u.extent_competed` | Competition type |
| `number_of_offers_received` | `u.number_of_offers_received` | Bid count |
| `usaspending_permalink` | `u.usaspending_permalink` | Direct link to award |
| `usaspending_extract_date` | `u.extract_date` | USASpending snapshot date |

**From SAM.gov (`s` alias) — NULLable (LEFT JOIN):**

| Output Column | Source Column | Notes |
|---|---|---|
| `legal_business_name` | `s.legal_business_name` | Official registered name |
| `dba_name` | `s.dba_name` | Doing-business-as |
| `physical_address_line_1` | `s.physical_address_line_1` | SAM registered address |
| `physical_address_city` | `s.physical_address_city` | SAM city |
| `physical_address_province_or_state` | `s.physical_address_province_or_state` | SAM state |
| `physical_address_zippostal_code` | `s.physical_address_zippostal_code` | SAM ZIP |
| `entity_url` | `s.entity_url` | Company website |
| `primary_naics` | `s.primary_naics` | SAM primary NAICS |
| `bus_type_string` | `s.bus_type_string` | SAM business type codes |
| `sba_business_types_string` | `s.sba_business_types_string` | SBA certification types |
| `cage_code` | `s.cage_code` | CAGE code |
| `registration_expiration_date` | `s.registration_expiration_date` | SAM registration expiry |
| `activation_date` | `s.activation_date` | SAM activation date |
| `entity_structure` | `s.entity_structure` | Legal structure code |
| `govt_bus_poc_first_name` | `s.govt_bus_poc_first_name` | Primary POC first name |
| `govt_bus_poc_last_name` | `s.govt_bus_poc_last_name` | Primary POC last name |
| `govt_bus_poc_title` | `s.govt_bus_poc_title` | Primary POC title |
| `alt_govt_bus_poc_first_name` | `s.alt_govt_bus_poc_first_name` | Alt POC first name |
| `alt_govt_bus_poc_last_name` | `s.alt_govt_bus_poc_last_name` | Alt POC last name |
| `alt_govt_bus_poc_title` | `s.alt_govt_bus_poc_title` | Alt POC title |
| `elec_bus_poc_first_name` | `s.elec_bus_poc_first_name` | E-Business POC first name |
| `elec_bus_poc_last_name` | `s.elec_bus_poc_last_name` | E-Business POC last name |
| `elec_bus_poc_title` | `s.elec_bus_poc_title` | E-Business POC title |
| `sam_extract_date` | `s.extract_date` | SAM snapshot date |

**Computed columns:**

| Output Column | Derivation | Notes |
|---|---|---|
| `is_first_time_awardee` | `BOOLEAN` — TRUE if this `recipient_uei` has exactly 1 distinct `contract_award_unique_key` across the full USASpending table | Highest-value signal for outbound |
| `total_awards_count` | `INTEGER` — count of distinct `contract_award_unique_key` per `recipient_uei` | Award history depth |
| `has_sam_match` | `BOOLEAN` — TRUE if the LEFT JOIN found a SAM.gov match | Data completeness indicator |

---

## First-Time Awardee Logic

This is the most important signal. A "first-time awardee" is a company whose UEI appears on only **one distinct award** (`contract_award_unique_key`) in the entire USASpending dataset. A single award may have multiple transaction rows (modifications), so count distinct awards, not rows.

Compute this as a window function or a pre-aggregated CTE:

```sql
-- Pseudocode
WITH award_counts AS (
    SELECT recipient_uei,
           COUNT(DISTINCT contract_award_unique_key) AS total_awards
    FROM entities.usaspending_contracts
    WHERE recipient_uei IS NOT NULL AND recipient_uei != ''
    GROUP BY recipient_uei
)
-- Then join: is_first_time_awardee = (total_awards = 1)
```

---

## Deliverables

### Deliverable 1: Migration — Materialized View

Create `supabase/migrations/033_mv_federal_contract_leads.sql`.

1. Create the materialized view `entities.mv_federal_contract_leads` with all columns defined above.

2. Use CTEs to:
   - Select latest-snapshot SAM.gov rows (latest `extract_date` per `unique_entity_id`)
   - Select latest-snapshot USASpending rows (latest `extract_date` per `contract_transaction_unique_key`)
   - Compute per-UEI award counts
   - JOIN and project output columns

3. Create indexes on the materialized view:
   - `UNIQUE (contract_transaction_unique_key)` — enables `REFRESH MATERIALIZED VIEW CONCURRENTLY`
   - `(recipient_uei)`
   - `(recipient_state_code)`
   - `(naics_code)`
   - `(action_date)`
   - `(awarding_agency_code)`
   - `(is_first_time_awardee)` — WHERE TRUE partial index
   - `(contracting_officers_determination_of_business_size)`
   - `(federal_action_obligation)` — for amount threshold filtering (cast to numeric at query time, but index on text is fine for now)

4. Wrap in `BEGIN; ... COMMIT;`

5. **Include a refresh command at the end:** `REFRESH MATERIALIZED VIEW entities.mv_federal_contract_leads;` — this populates the view on first creation.

**Important:** The initial refresh will take time (joining 1.34M × 867K). Expect 2-10 minutes depending on hardware. This is a one-time cost. Subsequent concurrent refreshes will be faster.

Commit standalone.

---

### Deliverable 2: Materialized View Refresh Utility

Create `app/services/federal_leads_refresh.py`.

1. **`refresh_federal_contract_leads(*, concurrent: bool = True) -> dict[str, Any]`**
   - Runs `REFRESH MATERIALIZED VIEW CONCURRENTLY entities.mv_federal_contract_leads` (or without CONCURRENTLY if `concurrent=False`)
   - Uses `psycopg_pool` connection pool (create a dedicated one, same pattern as SAM.gov/USASpending)
   - Statement timeout: `1800s` (30 minutes — the full refresh can be slow)
   - Returns `{ refreshed_at, concurrent, elapsed_ms }`
   - Logs start/end with timing

2. **`get_federal_leads_view_stats() -> dict[str, Any]`**
   - Runs `SELECT COUNT(*) as total_rows, COUNT(DISTINCT recipient_uei) as unique_companies, COUNT(*) FILTER (WHERE is_first_time_awardee) as first_time_awardees FROM entities.mv_federal_contract_leads`
   - Returns the stats dict

Commit standalone.

---

### Deliverable 3: Query Service

Create `app/services/federal_leads_query.py`.

Follow the pattern in `app/services/leads_query.py` but query the materialized view directly (no RPC needed — the view is already flat).

**`query_federal_contract_leads(*, filters: dict[str, Any], limit: int = 25, offset: int = 0) -> dict[str, Any]`**

Supported filters (all optional):

| Filter Key | Type | Behavior |
|---|---|---|
| `naics_prefix` | `str` | Matches `naics_code LIKE '{prefix}%'` — e.g., `"31"` matches all manufacturing codes starting with 31 |
| `state` | `str` | Exact match on `recipient_state_code` (2-letter) |
| `action_date_from` | `str` | `action_date >= '{value}'` (YYYY-MM-DD) |
| `action_date_to` | `str` | `action_date <= '{value}'` (YYYY-MM-DD) |
| `min_obligation` | `str` | `CAST(federal_action_obligation AS NUMERIC) >= {value}` |
| `business_size` | `str` | Exact match on `contracting_officers_determination_of_business_size` — values: `SMALL BUSINESS` or `OTHER THAN SMALL BUSINESS` |
| `first_time_only` | `bool` | If true, `is_first_time_awardee = TRUE` |
| `awarding_agency_code` | `str` | Exact match on `awarding_agency_code` |
| `has_sam_match` | `bool` | If true, `has_sam_match = TRUE` |
| `recipient_uei` | `str` | Exact match — look up a specific company |
| `recipient_name` | `str` | `ILIKE '%{value}%'` — partial name search |

Implementation:
- Use `psycopg` to build a parameterized query against `entities.mv_federal_contract_leads`
- Build WHERE clauses dynamically based on provided filters
- Add `ORDER BY action_date DESC` default ordering
- Add `LIMIT` and `OFFSET` for pagination
- Return `{ items: [...], total_matched: int, limit: int, offset: int }`
- Use `COUNT(*) OVER()` window function for total_matched (same pattern as existing leads query)
- All filter values must be parameterized — no string interpolation

Commit standalone.

---

### Deliverable 4: Query Endpoint

Wire a new endpoint in `app/routers/entities_v1.py`:

**`POST /api/v1/federal-contract-leads/query`**

Auth: Use `_resolve_flexible_auth` (same as other entity query endpoints — supports both tenant JWT and super-admin).

Request body (Pydantic model):
```python
class FederalContractLeadsQueryRequest(BaseModel):
    naics_prefix: str | None = None
    state: str | None = None
    action_date_from: str | None = None
    action_date_to: str | None = None
    min_obligation: str | None = None
    business_size: str | None = None
    first_time_only: bool | None = None
    awarding_agency_code: str | None = None
    has_sam_match: bool | None = None
    recipient_uei: str | None = None
    recipient_name: str | None = None
    limit: int = Field(default=25, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
```

Response: `DataEnvelope` wrapping the query result dict.

Also wire a stats endpoint:

**`POST /api/v1/federal-contract-leads/stats`**

Auth: same as above.

No request body needed. Returns `DataEnvelope` wrapping the stats dict from `get_federal_leads_view_stats()`.

Also wire a refresh endpoint (internal only):

**`POST /api/internal/federal-contract-leads/refresh`**

Auth: `require_internal_key`.

Optional request body:
```python
class InternalFederalLeadsRefreshRequest(BaseModel):
    concurrent: bool = True
```

Returns `DataEnvelope` wrapping the refresh result.

Commit standalone.

---

### Deliverable 5: Tests

Create `tests/test_federal_leads.py`.

1. **Query service tests (mock DB):**
   - Default query (no filters) returns paginated results
   - `naics_prefix` filter generates correct LIKE clause
   - `state` filter generates exact match
   - `action_date_from` + `action_date_to` generates range
   - `min_obligation` filter casts to numeric
   - `business_size` filter exact match
   - `first_time_only=True` filters on boolean
   - `recipient_name` generates ILIKE
   - Multiple filters combine with AND
   - Pagination (limit/offset) works correctly
   - All filter values are parameterized (no SQL injection)

2. **Endpoint tests (mock service):**
   - Query endpoint returns DataEnvelope
   - Stats endpoint returns DataEnvelope
   - Auth required on all endpoints
   - Invalid filter values return 422

All tests mock database calls. Use `pytest`.

Commit standalone.

---

## What is NOT in scope

- **No SBA 7(a) data.** SBA has no shared identifier — it is a separate lead pool.
- **No Trigger.dev task.** View refresh is manual or via internal endpoint for now.
- **No scheduled refresh.** Periodic refresh automation is future work.
- **No deploy commands.** Do not push.
- **No modifications to SAM.gov or USASpending ingestion code.**
- **No modifications to existing entity tables or views.**
- **No data transformation beyond what's in the view definition.** Raw values are preserved.
- **No entity resolution or fuzzy matching.**

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Migration: view name, output column count, index count, initial refresh time
(b) Refresh utility: concurrent/non-concurrent support, timeout setting
(c) Query service: filter count, parameterization approach, pagination pattern
(d) Endpoints: paths (3 total), auth on each, request/response shapes
(e) Tests: total count, all passing
(f) View stats after initial refresh: total rows, unique companies, first-time awardees count
(g) Sample query result: run `first_time_only=True, state='VA', limit=5` and show the 5 rows (company name, UEI, award amount, agency, NAICS, POC name if available)
(h) Anything to flag — especially: how many USASpending records had no SAM.gov match? How long did the initial refresh take?
