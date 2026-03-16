# Sales Nav Prospects: Broken Auto-Persist & Data Gap Report

**Date:** 2026-03-15
**Status:** Production broken — 0 rows persisted despite 349 emitted prospects

---

## The Problem

`salesnav_prospects` has **0 rows in production** despite 17 successful `person.search.sales_nav_url` step results emitting 349 prospect records. The data is generated correctly by the RapidAPI adapter but never reaches the database.

**Root cause:** The Trigger.dev auto-persist branch in `run-pipeline.ts` requires `source_company_domain` in the step's cumulative context to fire the salesnav-prospects upsert path. Successful `person.search.sales_nav_url` steps do not carry a usable `source_company_domain` in their context shape, so the persist condition is never satisfied and the data is silently dropped.

This is documented in `CLAUDE.md` under "What Is Broken" and confirmed by `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`.

## What Works

- **RapidAPI adapter** (`app/providers/rapidapi_salesnav.py`): correctly calls the scraper, maps 20 person fields, preserves full raw response in `attempt.raw_response`
- **Service function** (`app/services/salesnav_operations.py`): correctly accumulates paginated results (up to 50 pages), returns combined output
- **Internal upsert endpoint** (`POST /api/internal/salesnav-prospects/upsert`): exists and is functional
- **Query endpoint** (`POST /api/v1/salesnav-prospects/query`): exists and is functional (would work if the table had data)
- **DB schema** (migration 020): table exists with correct columns, unique constraint on `(org_id, source_company_domain, linkedin_url)`

## What's Broken

The auto-persist path in `run-pipeline.ts` (around lines 2363-2384) checks for `source_company_domain` in the step context before calling the upsert endpoint. The two-step Sales Nav workflow is:

1. `company.derive.salesnav_url` → builds the encoded LinkedIn Sales Nav URL (via RevenueInfra HQ)
2. `person.search.sales_nav_url` → scrapes results from that URL (via RapidAPI)

Step 1's output is a `sales_nav_url` string. Step 2's cumulative context inherits this URL but NOT the originating company's domain. The pipeline context never explicitly carries `source_company_domain` forward, so the persist condition fails silently.

## Impact

- **349 prospect records** from 17 successful steps are in `step_results` (as output JSON) but NOT in the `salesnav_prospects` dedicated table
- The query endpoint returns empty results
- Downstream workflows that depend on `salesnav_prospects` data have nothing to work with
- The data IS recoverable — it's in `step_results.output` — but requires a backfill script

## Fix Options

**Option A: Fix the context shape (preferred)**
Ensure `source_company_domain` is propagated through the pipeline context. This likely means:
- The blueprint step config for `company.derive.salesnav_url` should output `source_company_domain` (derived from the input company domain)
- OR the `person.search.sales_nav_url` service function should extract the company domain from the sales_nav_url itself (it's encoded in the URL)
- OR the Trigger workflow should explicitly inject `source_company_domain` into the context before calling the persist path

**Option B: Migrate to dedicated workflow (preferred long-term)**
The auto-persist in `run-pipeline.ts` is legacy and known to silently swallow failures. A dedicated Sales Nav workflow (like the existing company-enrichment and person-enrichment dedicated workflows) would use confirmed writes and surface failures explicitly.

**Option C: Backfill + fix forward**
1. Write a backfill script that reads the 349 prospect records from `step_results.output` and inserts them into `salesnav_prospects`
2. Fix the context shape (Option A) so future runs persist correctly

## Related Issues

This is the same class of bug as the other broken auto-persist paths documented in CLAUDE.md:
- `company_customers`: 0 rows despite 331 emitted items
- `gemini_icp_job_titles`: 0 rows despite 20 successful upstream steps
- All caused by context shape failures in `run-pipeline.ts` auto-persist branches

## Files

| File | Role |
|------|------|
| `app/providers/rapidapi_salesnav.py` | RapidAPI adapter — works correctly |
| `app/services/salesnav_operations.py` | Service function — works correctly |
| `app/services/salesnav_prospects.py` | Persistence / query service — works correctly |
| `app/providers/revenueinfra/salesnav_url.py` | URL builder (Step 1) — works correctly |
| `trigger/src/tasks/run-pipeline.ts` | Auto-persist branch — **broken context check** |
| `supabase/migrations/020_salesnav_prospects.sql` | Table schema — exists and correct |
| `app/contracts/sales_nav.py` | Output contracts — correct |
