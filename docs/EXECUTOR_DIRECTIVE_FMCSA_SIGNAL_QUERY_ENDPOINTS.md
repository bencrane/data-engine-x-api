# Executor Directive: FMCSA Signal Query Endpoints

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The FMCSA signal detection engine (built by a prior directive) writes detected business signals to `entities.fmcsa_carrier_signals`. This directive builds the read-side API — the endpoints that frontends, dashboards, and outbound automation consume to answer: what happened today? what's the signal history for this carrier? how many new carriers appeared this week?

---

## Reference Documents (Read Before Starting)

**Must read — project conventions:**
- `CLAUDE.md` — project conventions, auth model, endpoint patterns

**Must read — existing FMCSA query patterns (follow these exactly):**
- `app/routers/fmcsa_v1.py` — the FMCSA router with request models, `_resolve_flexible_auth`, response patterns, lazy imports. New endpoints go here.
- `app/services/fmcsa_carrier_query.py` — connection pool pattern, `_get_pool()`, parameterized queries with `_build_*_where()` helpers, `COUNT(*) OVER()` for pagination, `_conditions_to_where()`
- `app/services/fmcsa_carrier_detail.py` — multi-query aggregation pattern, Decimal coercion

**Must read — the signal table schema:**
- `supabase/migrations/035_fmcsa_carrier_signals.sql` — the table this directive queries (created by the detection engine directive). Key columns: `signal_type`, `feed_date`, `dot_number`, `docket_number`, `entity_key`, `severity`, `legal_name`, `physical_state`, `power_unit_count`, `driver_total`, `before_values`, `after_values`, `signal_details`, `source_table`, `source_feed_name`, `created_at`. Unique on `(signal_type, feed_date, entity_key)`.

**Must read — response envelope:**
- `app/routers/_responses.py` — `DataEnvelope`, `ErrorEnvelope`

---

## Endpoints

Three new endpoints, all added to the existing `fmcsa_router` in `app/routers/fmcsa_v1.py`.

### 1. `POST /fmcsa-signals/query`

**Purpose:** Filter and paginate detected signals. The primary search endpoint for signal consumers.

**Auth:** `_resolve_flexible_auth` (same as all FMCSA endpoints — accepts both tenant and super-admin tokens).

**Request model:** `FmcsaSignalQueryRequest`

| Field | Type | Default | Description |
|---|---|---|---|
| `signal_type` | `str \| None` | None | Filter to one signal type (e.g., `"new_carrier"`, `"insurance_lapsed"`) |
| `signal_types` | `list[str] \| None` | None | Filter to multiple signal types (OR). Mutually exclusive with `signal_type` — if both provided, `signal_types` wins. |
| `severity` | `str \| None` | None | Filter by severity: `"info"`, `"warning"`, `"critical"` |
| `min_severity` | `str \| None` | None | Minimum severity: `"warning"` returns warning + critical. `"critical"` returns only critical. |
| `dot_number` | `str \| None` | None | Exact DOT number match |
| `state` | `str \| None` | None | Filter by `physical_state` |
| `feed_date` | `str \| None` | None | Exact feed date (ISO, e.g., `"2026-03-17"`) |
| `feed_date_from` | `str \| None` | None | Feed date range start (inclusive) |
| `feed_date_to` | `str \| None` | None | Feed date range end (inclusive) |
| `min_power_units` | `int \| None` | None | Minimum fleet size |
| `legal_name_contains` | `str \| None` | None | ILIKE search on `legal_name` |
| `limit` | `int` | 25 | 1–500 |
| `offset` | `int` | 0 | >= 0 |

**Response:** `DataEnvelope` wrapping:
```
{
  "items": [ { signal row as dict, all columns } ],
  "total_matched": <int>,
  "limit": <int>,
  "offset": <int>
}
```

**Sort order:** `feed_date DESC, detected_at DESC, dot_number`.

**Severity ordering for `min_severity`:** info < warning < critical. A `min_severity` of `"warning"` should match both `"warning"` and `"critical"`.

### 2. `GET /fmcsa-signals/summary`

**Purpose:** Dashboard-level view — counts by signal type for a date or date range. Powers "what happened today" widgets.

**Auth:** `_resolve_flexible_auth`.

**Query parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `feed_date` | `str \| None` | None | Exact date. If omitted and no range provided, defaults to the most recent `feed_date` in the signals table. |
| `feed_date_from` | `str \| None` | None | Range start |
| `feed_date_to` | `str \| None` | None | Range end |
| `state` | `str \| None` | None | Filter by physical_state |

**Response:** `DataEnvelope` wrapping:
```
{
  "feed_date": "<date or range description>",
  "total_signals": <int>,
  "by_type": {
    "new_carrier": { "count": <int>, "critical": <int>, "warning": <int>, "info": <int> },
    "disappeared_carrier": { ... },
    "authority_granted": { ... },
    "authority_revoked": { ... },
    "insurance_added": { ... },
    "insurance_lapsed": { ... },
    "safety_worsened": { ... },
    "new_crash": { ... },
    "new_oos_order": { ... }
  },
  "by_severity": {
    "critical": <int>,
    "warning": <int>,
    "info": <int>
  }
}
```

**Implementation:** A single query with `GROUP BY signal_type, severity` and aggregate in Python. If no date filters provided, auto-detect the latest `feed_date` from `fmcsa_carrier_signals`. Always include all 9 signal types in the response even if count is 0 (fill missing types with zeros).

### 3. `GET /fmcsa-carriers/{dot_number}/signals`

**Purpose:** All signals for a specific carrier. Powers the carrier detail signal timeline.

**Auth:** `_resolve_flexible_auth`.

**Query parameters:**
| Param | Type | Default | Description |
|---|---|---|---|
| `signal_type` | `str \| None` | None | Filter to one signal type |
| `feed_date_from` | `str \| None` | None | Range start |
| `feed_date_to` | `str \| None` | None | Range end |
| `limit` | `int` | 50 | 1–500 |
| `offset` | `int` | 0 | >= 0 |

**Response:** `DataEnvelope` wrapping:
```
{
  "dot_number": "<dot_number>",
  "items": [ { signal row as dict } ],
  "total_matched": <int>,
  "limit": <int>,
  "offset": <int>
}
```

**Sort order:** `feed_date DESC, detected_at DESC`.

**404 behavior:** Do NOT return 404 if the DOT number has no signals — return an empty items list. The DOT number may be valid but simply have no detected signals yet.

---

## File Structure

Create these new files:

| File | Purpose |
|---|---|
| `app/services/fmcsa_signal_query.py` | Query service for signal endpoints |
| `tests/test_fmcsa_signal_query_endpoints.py` | Tests for query service + endpoints |

Modify this existing file:

| File | Change |
|---|---|
| `app/routers/fmcsa_v1.py` | Add 3 new endpoints + request models |

---

## Deliverable 1: Signal Query Service

Create `app/services/fmcsa_signal_query.py`.

Follow the connection pool pattern from `app/services/fmcsa_carrier_query.py`: lazy `_get_pool()`, `psycopg` with `dict_row`, parameterized queries.

**Functions:**

1. **`query_fmcsa_signals(*, filters: dict, limit: int, offset: int) -> dict`**
   - Builds WHERE clause from filters dict (signal_type, signal_types, severity, min_severity, dot_number, state, feed_date, feed_date_from, feed_date_to, min_power_units, legal_name_contains).
   - `min_severity` maps to: `severity IN ('warning', 'critical')` for min_severity='warning', `severity = 'critical'` for min_severity='critical'.
   - Uses `COUNT(*) OVER()` for total_matched (same pattern as `query_fmcsa_carriers`).
   - Returns `{items, total_matched, limit, offset}`.

2. **`get_fmcsa_signal_summary(*, filters: dict) -> dict`**
   - Runs `SELECT signal_type, severity, COUNT(*) FROM entities.fmcsa_carrier_signals WHERE ... GROUP BY signal_type, severity`.
   - If no date filters and no data, returns all-zeros summary.
   - If no date filters provided, auto-detects latest feed_date: `SELECT MAX(feed_date) FROM entities.fmcsa_carrier_signals`.
   - Assembles the nested response structure with all 9 signal types always present.

3. **`query_carrier_signals(*, dot_number: str, filters: dict, limit: int, offset: int) -> dict`**
   - Queries signals filtered by `dot_number` plus optional signal_type and date range.
   - Returns `{dot_number, items, total_matched, limit, offset}`.

**All queries target `entities.fmcsa_carrier_signals` explicitly.** All use parameterized queries (never string interpolation for values).

Commit standalone.

---

## Deliverable 2: Router Endpoints

Add to `app/routers/fmcsa_v1.py`:

**Request models** (add to the existing model section):
- `FmcsaSignalQueryRequest` — fields as specified above
- No model needed for GET endpoints (use FastAPI Query parameters)

**Endpoints** (add to the existing `fmcsa_router`):

1. `POST /fmcsa-signals/query` — calls `query_fmcsa_signals`. Lazy import of the service function inside the handler.

2. `GET /fmcsa-signals/summary` — calls `get_fmcsa_signal_summary`. Use FastAPI `Query()` for parameters. Lazy import.

3. `GET /fmcsa-carriers/{dot_number}/signals` — calls `query_carrier_signals`. Use `Query()` for optional params. Lazy import.

**All endpoints use `_resolve_flexible_auth` (same as existing FMCSA endpoints).**

**Response:** All return `DataEnvelope(data=result)`.

**Important:** Do not modify or remove any existing endpoints in `fmcsa_v1.py`. Only add new ones.

Commit standalone.

---

## Deliverable 3: Tests

Create `tests/test_fmcsa_signal_query_endpoints.py`.

All tests mock database calls. Use `pytest`. Do not hit real databases.

**1. Query service tests:**
- `query_fmcsa_signals` with no filters returns paginated results with total_matched.
- `query_fmcsa_signals` with `signal_type="new_carrier"` filters correctly.
- `query_fmcsa_signals` with `signal_types=["new_carrier", "new_crash"]` returns both types.
- `query_fmcsa_signals` with `min_severity="warning"` returns warning + critical, not info.
- `query_fmcsa_signals` with `feed_date_from` and `feed_date_to` applies date range.
- `query_fmcsa_signals` with `min_power_units` filters on fleet size.
- `query_fmcsa_signals` with `legal_name_contains` uses ILIKE.
- `query_fmcsa_signals` with `state` filters on physical_state.
- `get_fmcsa_signal_summary` returns all 9 signal types even when some have 0 count.
- `get_fmcsa_signal_summary` with no date filter auto-detects latest feed_date.
- `get_fmcsa_signal_summary` with `state` filter scopes correctly.
- `query_carrier_signals` filters by dot_number and returns paginated results.
- `query_carrier_signals` with no signals returns empty items, not error.

**2. Endpoint tests (via TestClient):**
- `POST /api/v1/fmcsa-signals/query` with valid auth returns 200 + DataEnvelope.
- `POST /api/v1/fmcsa-signals/query` without auth returns 401.
- `GET /api/v1/fmcsa-signals/summary` returns 200 + DataEnvelope with by_type and by_severity.
- `GET /api/v1/fmcsa-carriers/12345/signals` returns 200 + DataEnvelope with dot_number in response.
- `GET /api/v1/fmcsa-carriers/99999/signals` with no signals returns 200 + empty items (not 404).

**3. Filter building tests:**
- Severity ordering: `min_severity="warning"` produces correct SQL condition.
- `signal_types` list produces correct IN clause.
- All filter combinations produce valid parameterized SQL (no injection possible).

Commit standalone.

---

## What is NOT in scope

- **No changes to the signal detection engine** (`fmcsa_signal_detection.py`, `internal.py` detect endpoint, Trigger.dev task). This directive only reads from the signals table.
- **No schema changes.** No migrations. The signals table already exists.
- **No changes to existing FMCSA query endpoints.** Only add new endpoints.
- **No changes to `app/main.py`.**
- **No deploy commands.** Do not push.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Query service: function count, connection pool config, filter count per function
(b) Router: endpoint count added, request model count added, confirm no existing endpoints modified
(c) Response shapes: confirm all 3 endpoints return the documented response structure
(d) Summary endpoint: confirm all 9 signal types always present in response, confirm auto-detection of latest feed_date when no date filter
(e) Tests: total test count, all passing, confirm endpoint path coverage
(f) Anything to flag — especially: any concern about query performance on large signal tables, any ambiguity in filter semantics that required a judgment call, any JSONB column serialization concerns
