# Executor Directive: Operational Reality Check Refresh (2026-03-18)

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The production-truth audit `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` is now 8 days old and materially stale. Since March 10, significant infrastructure has shipped (FMCSA COPY bulk writes, gzip compression, connection pooling, FMCSA query endpoints, signal detection, analytics materialized views, and more). The system's `CLAUDE.md`, architecture doc, and chief agent workflow docs all point to the March 10 report as the authoritative production baseline. A fresh audit is needed so that all downstream decisions are grounded in current reality.

---

## Existing code to read

Before starting any investigative work, read these files carefully:

- `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md` — **your structural template**. The new report must follow the same section structure, methodology, table formats, and level of evidence rigor. Study every section, every query pattern, every table. Your report must be at least as thorough.
- `CLAUDE.md` — understand the "Production State (as of 2026-03-10)" section you will update, and all other references to the March 10 report filename.
- `docs/WRITING_EXECUTOR_DIRECTIVES.md` — contains cross-references to the March 10 report that need updating.
- `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md` — contains cross-references to the March 10 report that need updating.
- `docs/DATA_ENGINE_X_ARCHITECTURE.md` — contains cross-references to the March 10 report that need updating.
- `docs/STRATEGIC_DIRECTIVE.md` — contains cross-references to the March 10 report that need updating.
- `docs/CHIEF_AGENT_DIRECTIVE.md` — contains cross-references to the March 10 report that need updating.

---

## Methodology

**Every claim in the new report must be grounded in a live production SQL query result.** Do not infer production state from code, docs, directives, or repo contents. The report is a production audit, not a code review.

Run all queries against the production database using:

```bash
doppler run -p data-engine-x-api -c prd -- psql
```

Or for individual queries:

```bash
doppler run -p data-engine-x-api -c prd -- psql -c "YOUR SQL HERE"
```

If a query fails or a table does not exist, that is a finding — document it.

---

## Deliverable 1: Production Reality Check Report

Create `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md`.

Follow the exact same structure as the March 10 report. The new report must stand alone — it is not a diff document. A reader should be able to understand the full production state without reading the March 10 report.

### Required sections

#### Header

```markdown
# Operational Reality Check

**Last updated:** 2026-03-18 [time in UTC when you finish, e.g. 2026-03-18T14:30:00Z]

As of `2026-03-18`.

This report is based on:

- Live production SQL run against the production `DATABASE_URL` via `doppler run -p data-engine-x-api -c prd -- psql`.
- [any other sources used]
```

#### Changes since 2026-03-10

**This is a new section that the March 10 report did not have.** Place it immediately after the executive summary. Summarize material movements since the last audit:

- New submissions, pipeline runs, or step results created since March 10
- New blueprints used for the first time
- Previously broken tables that now have data (or vice versa)
- Stuck runs that resolved or new ones that appeared
- Row count changes in key tables (entity tables, dedicated tables, operations tables)
- Any new tables or schemas that appeared in production
- Any tables that disappeared from production

Keep this section factual and concise. Do not editorialize.

#### Section 1: What's Actually Running?

Same as March 10 report:

- Live schema reality (which schemas exist, where application tables live)
- Full row counts for all application tables (same table list as March 10, plus any new tables discovered)
- Status breakdowns for `submissions`, `pipeline_runs`, `step_results`
- Most recent submission, pipeline run, step result
- `operation_runs` and `operation_attempts` counts and status breakdowns

#### Section 2: Which Blueprints Exist and Have Been Used?

Same table format as March 10: org, blueprint name, used (yes/no), submission count, completed submission count, last run timestamp.

#### Section 3: Which Operations Have Actually Been Called?

Same structure as March 10:

- FastAPI-backed operations from `operation_runs` — full table with call count, failure count, failure rate, last called
- Trigger-direct operations from `step_results` joined to blueprint snapshots — same format
- Combined "actually called in production" set with count
- Never-called operations list (compare against the current `app/routers/execute_v1.py` operation catalog and Trigger-direct operations)

**Important:** The operation catalog may have changed since March 10. Check the current `SUPPORTED_OPERATION_IDS` in `app/routers/execute_v1.py` and the current Trigger-direct operations in `trigger/src/tasks/run-pipeline.ts` to get the accurate total executable operation count. Also check for any new FMCSA-specific operations that may have been added (e.g., in `app/routers/fmcsa_v1.py`).

#### Section 4: Entity Data Quality

Same metrics as March 10 for `company_entities`, `person_entities`, `job_posting_entities`.

#### Section 5: Auto-Persist Health

Same dedicated-table audit as March 10. For each dedicated table (`icp_job_titles`, `company_intel_briefings`, `person_intel_briefings`, `company_customers`, `gemini_icp_job_titles`, `company_ads`, `salesnav_prospects`, `extracted_icp_job_title_details`, `entity_relationships`):

- Current row count
- Upstream step evidence (successful steps that should have produced rows)
- Verdict: healthy, broken, unused, or improved since March 10

If `company_ads` still does not exist in production, document that.

#### Section 6: What's Broken or Stale?

Same structure as March 10:

- Tables with zero rows that should have data
- Tables missing entirely
- Stale `running` pipeline runs (age, trigger run IDs)
- Stale `running` or `queued` step results
- Legacy vs operation-native state
- Evidence of deploy-timing class failures

#### Section 7: Trigger.dev State

Same as March 10 where possible:

- Current deployed worker version
- Registered tasks on the current prod worker
- Any observable scheduled trigger state

**Note:** If you cannot access Trigger.dev state directly from psql, document what you can observe and note what you cannot.

#### Section 8: FMCSA Tables (New Section)

**This section is new — the March 10 report predates FMCSA infrastructure.**

Query the `entities` schema for all 18 FMCSA canonical tables. For each table, report:

- Whether the table exists in production
- Row count
- Most recent `feed_date` (if the table has one) or most recent `source_observed_at`/`last_observed_at`

The 18 FMCSA tables to check:

1. `entities.operating_authority_histories`
2. `entities.operating_authority_revocations`
3. `entities.insurance_policies`
4. `entities.insurance_policy_filings`
5. `entities.insurance_policy_history_events`
6. `entities.carrier_registrations`
7. `entities.process_agent_filings`
8. `entities.insurance_filing_rejections`
9. `entities.carrier_safety_basic_measures`
10. `entities.carrier_safety_basic_percentiles`
11. `entities.carrier_inspection_violations`
12. `entities.carrier_inspections`
13. `entities.motor_carrier_census_records`
14. `entities.commercial_vehicle_crashes`
15. `entities.vehicle_inspection_units`
16. `entities.vehicle_inspection_special_studies`
17. `entities.out_of_service_orders`
18. `entities.vehicle_inspection_citations`

Also check for:
- `entities.fmcsa_carrier_signals` (signal detection table)
- Any materialized views (`entities.mv_fmcsa_authority_grants`, `entities.mv_fmcsa_insurance_cancellations`)

Present results in a table format:

```markdown
| Table | Exists | Rows | Latest feed_date or observation |
|---|---:|---:|---|
```

If an entire schema does not exist, document that.

#### Bottom Line

Same closing section as March 10 — summarize the production baseline that any future work must protect, and the known-broken items that are pre-existing rather than regressions.

### Evidence standard

- Every row count must come from a `SELECT COUNT(*) FROM ...` query.
- Every status breakdown must come from a `GROUP BY` query.
- Every "most recent" claim must come from a `MAX()` or `ORDER BY ... LIMIT 1` query.
- If a table or schema does not exist, the error message from the failed query is the evidence.
- Do not round or estimate. Use exact numbers.

Commit standalone.

---

## Deliverable 2: Update CLAUDE.md

Update `CLAUDE.md` to reflect the new report:

1. **Update the "Production State" section header** from `(as of 2026-03-10)` to `(as of 2026-03-18)`.

2. **Update the section content** to reflect any material changes discovered in Deliverable 1. Specifically update:
   - "What Works End-to-End" — update row counts, blueprint completion counts, and healthy auto-persist paths based on new data
   - "What Is Broken" — update with current state of each broken item (fixed, still broken, newly broken)
   - "What Has Never Been Used" — update the never-called operations list and count, unused blueprints, zero-row tables
   - "Known Architectural Problems" — update only if the new audit reveals that any listed problem has been resolved or a new one has appeared

3. **Update all filename references** throughout `CLAUDE.md`: change every occurrence of `OPERATIONAL_REALITY_CHECK_2026-03-10` to `OPERATIONAL_REALITY_CHECK_2026-03-18`. This includes references in the "Documentation Authority" section, "Diagnostic Reports" section, and anywhere else the filename appears.

4. **Add a last-updated timestamp** at the very top of `CLAUDE.md`, before the `# CLAUDE.md` header:

```markdown
<!-- Last updated: 2026-03-18T[HH:MM:SS]Z -->
```

Use the actual UTC time when you finish editing.

Commit standalone.

---

## Deliverable 3: Update Cross-Reference Documents

Update the following documents to point to the new report filename. For each file:

- Replace every occurrence of `OPERATIONAL_REALITY_CHECK_2026-03-10` with `OPERATIONAL_REALITY_CHECK_2026-03-18`
- Replace every occurrence of `2026-03-10` that specifically refers to the operational reality check date (not other dates) with `2026-03-18`
- Add a last-updated timestamp at the top of each file, immediately after the `#` title line:

```markdown
**Last updated:** 2026-03-18T[HH:MM:SS]Z
```

Use the actual UTC time when you finish editing each file.

**Files to update:**

1. `docs/WRITING_EXECUTOR_DIRECTIVES.md`
2. `docs/CHIEF_AGENT_DOC_AUTHORITY_MAP.md`
3. `docs/DATA_ENGINE_X_ARCHITECTURE.md`
4. `docs/STRATEGIC_DIRECTIVE.md`
5. `docs/CHIEF_AGENT_DIRECTIVE.md`

**Important:** Do NOT update other `docs/EXECUTOR_DIRECTIVE_*.md` files. Those are historical scope documents and their references to the March 10 report are correct for their historical context. Only update the active truth-hierarchy and workflow documents listed above.

Commit standalone.

---

## What is NOT in scope

- **No code changes.** This is a documentation-only directive.
- **No schema changes.** No migrations.
- **No deploy commands.** Do not push.
- **No fixes to any broken state discovered.** Document it, do not fix it.
- **No changes to `docs/EXECUTOR_DIRECTIVE_*.md` files** (except this directive itself). Those are historical scope documents.
- **No changes to `docs/SYSTEM_OVERVIEW.md`, `docs/ARCHITECTURE.md`, `docs/AGENT_HANDOFF.md`, or `docs/COMPREHENSION.md`.** Those are lower-authority historical documents and updating them is not worth the effort.
- **Do not delete `docs/OPERATIONAL_REALITY_CHECK_2026-03-10.md`.** The old report is retained as historical reference.

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) New report: full path, section count, total SQL queries run, any queries that failed or tables that did not exist
(b) Key deltas from March 10: top 5 most significant changes discovered (new row counts, fixed tables, new breakage, new tables, etc.)
(c) CLAUDE.md updates: list of sections changed, number of filename references updated
(d) Cross-reference updates: list of files updated, number of references changed per file
(e) FMCSA tables: how many of the 18 tables exist, how many have data, total FMCSA row count across all tables
(f) Anything to flag — especially: any surprising findings, any tables or schemas that appeared or disappeared unexpectedly, any evidence of new failure classes not documented in the March 10 report
