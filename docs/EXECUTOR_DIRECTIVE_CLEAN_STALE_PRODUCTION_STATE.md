# Directive: Priority 1 — Clean Stale Production State

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** Production contains schema drift (a missing table) and stale pipeline state (orphaned running/queued rows from dead Trigger.dev runs). These make it impossible to reason accurately about system health. This cleanup clears the noise before we begin the pipeline rewrite. This is database-only work — no application code changes, no commits, no deploys.

**How to connect to the production database:**

```bash
doppler run -p data-engine-x-api -c prd -- psql
```

**Existing files to read before starting:**

- `CLAUDE.md` — project conventions, production state summary
- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — the audit this cleanup is based on; contains row counts, stuck run IDs, and status breakdowns
- `supabase/migrations/019_company_ads.sql` — the migration to apply

---

## Deliverable 1: Apply migration 019 (company_ads table)

The `company_ads` table does not exist in production. The migration file is at `supabase/migrations/019_company_ads.sql`. The application code and auto-persist logic already expect this table.

Apply the migration file against production. Verify the table exists and all indexes defined in the migration were created.

---

## Deliverable 2: Mark stale pipeline_runs and step_results as terminal

As of the 2026-03-10 audit:

- `8` `pipeline_runs` are stuck in `running` (oldest for 14+ days). Their Trigger.dev runs are dead.
- `7` `step_results` are stuck in `running`.
- `190` `step_results` are stuck in `queued`.

All are orphaned. Nothing will ever advance them.

**Before each update, run a SELECT count to confirm the number matches the audit.** If the count is materially different (more than a few off), STOP and report the discrepancy before updating.

- Mark all `running` pipeline_runs as `failed`.
- Mark all `running` step_results as `failed`.
- Mark all `queued` step_results as `cancelled`.

After the updates, check whether the two parent submissions (`0921f10b-890b-47ab-8ceb-b1986df51cbb` and `2b333f02-903c-46bf-80ff-b25e9e1b92fa`) are still in non-terminal status with no remaining `running` pipeline_runs. If so, mark them as `failed`.

---

## Deliverable 3: Verify the cleanup

Re-run status breakdowns for `pipeline_runs`, `step_results`, and `submissions`.

**Acceptance criteria:**

- Zero `running` pipeline_runs.
- Zero `running` step_results. Zero `queued` step_results.
- Zero `running` or `queued` submissions (unless new legitimate submissions were created after the audit).
- `company_ads` table exists and has zero rows.

---

## What is NOT in scope

- No application code changes
- No changes to any file in the repo
- No git commits
- No deploys (Railway or Trigger.dev)
- No changes to tables other than `pipeline_runs`, `step_results`, `submissions`, and the new `company_ads` table
- No backfill of data into `company_customers`, `gemini_icp_job_titles`, `salesnav_prospects`, or `company_ads`
- No schema modifications beyond applying migration 019 exactly as written

## When done

Report back with:
(a) Confirmation that `company_ads` table and its indexes exist
(b) Update counts: pipeline_runs marked failed, step_results marked failed, step_results marked cancelled
(c) Before and after status for the 2 parent submissions
(d) Full status breakdown tables for pipeline_runs, step_results, and submissions after cleanup
(e) Anything unexpected — count mismatches, errors, or new stale rows not covered by the audit
