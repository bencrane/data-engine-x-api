# Executor Directive: Add Average/Median Obligation and Award Ceiling Metrics

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The vertical summary and stats endpoints already compute `total_obligated` and row/company counts. We need three additional aggregate metrics on both endpoints to give users better contract value signals: average obligation per company, median obligation, and average award ceiling (from `potential_total_value_of_award` — the contract ceiling, which better represents full contract value vs per-action obligation).

---

## Existing Code to Read and Modify

- `app/services/federal_leads_verticals.py` — `get_vertical_summary()` — vertical NAICS aggregation query
- `app/services/federal_leads_refresh.py` — `get_federal_leads_view_stats()` — global stats query
- `tests/test_federal_leads.py` — existing tests (add new test cases, do not break existing)

---

## Deliverable 1: Add Metrics to Vertical Summary

Modify `app/services/federal_leads_verticals.py`:

Add three new fields to the SQL aggregation in `get_vertical_summary()`:

1. **`average_obligation`** — `SUM(CAST(federal_action_obligation AS NUMERIC)) / NULLIF(COUNT(DISTINCT recipient_uei), 0)` — average total obligation per unique company in the vertical.

2. **`median_obligation`** — Use `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(federal_action_obligation AS NUMERIC))` — the median per-transaction obligation amount. Note: `PERCENTILE_CONT` is an ordered-set aggregate and cannot be used inside a `CASE WHEN` grouping directly. You'll need to compute the median in a separate CTE or subquery that first assigns each row its vertical label, then aggregates per vertical.

3. **`average_award_ceiling`** — `SUM(CAST(potential_total_value_of_award AS NUMERIC)) / NULLIF(COUNT(DISTINCT recipient_uei), 0)` — average contract ceiling per unique company.

Add these three fields to the return dict for each row. Use `float()` conversion with a `None` → `0.0` fallback, same pattern as the existing `total_obligated`.

**Important for median:** `federal_action_obligation` and `potential_total_value_of_award` are stored as TEXT and can be empty strings or NULL. Cast to NUMERIC and filter out NULLs/empty strings in the median calculation. Empty string cast will error — use `NULLIF(federal_action_obligation, '')` before casting.

Commit standalone.

---

## Deliverable 2: Add Metrics to Stats Endpoint

Modify `app/services/federal_leads_refresh.py`:

Add three new fields to the SQL in `get_federal_leads_view_stats()`:

1. **`average_obligation`** — total obligation / unique companies (same formula as vertical, but across entire dataset)
2. **`median_obligation`** — `PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(NULLIF(federal_action_obligation, '') AS NUMERIC))` — can be used directly here since there's no GROUP BY
3. **`average_award_ceiling`** — total ceiling / unique companies

Add these three fields to the return dict. Use `float()` conversion with `None` → `0.0` fallback.

Commit standalone.

---

## Deliverable 3: Tests

Add test cases to `tests/test_federal_leads.py`:

1. **Vertical summary** — verify the three new fields (`average_obligation`, `median_obligation`, `average_award_ceiling`) are present in each vertical dict returned by `get_vertical_summary()`
2. **Stats** — verify the three new fields are present in the dict returned by `get_federal_leads_view_stats()`
3. **Null handling** — verify that verticals/stats with NULL or empty `federal_action_obligation` or `potential_total_value_of_award` values don't cause errors (return 0.0)

All tests mock database calls. Do not break existing tests.

Commit standalone.

---

## What is NOT in scope

- No new endpoints. These are additions to existing SQL aggregations.
- No materialized view changes. The view already has `federal_action_obligation` and `potential_total_value_of_award`.
- No deploy commands. Do not push.
- No modifications to the query endpoint or export endpoint.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Vertical summary: the 3 new fields, SQL approach for median (CTE vs subquery), null handling
(b) Stats: the 3 new fields, SQL approach
(c) Tests: new test count, all passing (existing + new)
(d) Anything to flag — especially: did the median calculation require restructuring the vertical query significantly?
