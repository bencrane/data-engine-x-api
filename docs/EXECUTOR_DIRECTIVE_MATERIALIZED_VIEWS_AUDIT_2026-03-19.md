# Executor Directive: Materialized Views Audit and Expansion

**Last updated:** 2026-03-19T00:00:00Z

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, apply migrations to production, or take actions not covered by this directive. Within scope — including MV design choices, SQL authorship, and index selection — use your best judgment.

**Background:** The `entities` schema has 9 materialized views today: 6 FMCSA views, 2 USASpending analytical views, and the federal contract leads view. `entities.sam_gov_entities` (867K rows) and `entities.sba_7a_loans` (356K rows) have no MVs at all. Cross-vertical joins — SAM.gov entities with their USASpending contract history, FMCSA carriers with their insurance posture — have no pre-computed form. This directive produces a complete picture of what exists, what is missing, and the actual SQL to build it. The deliverable is an inventory document, a migration file, and an updated refresh script. Nothing is applied to production.

---

## Files to read before starting

Read these in order before writing anything:

1. `CLAUDE.md` — current production state and architecture overview
2. `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` — live row counts, confirmed table state, confirmed MV state
3. `docs/DEPLOY_PROTOCOL.md` — migration numbering (next is **042**)
4. `supabase/migrations/038_mv_usaspending_analytical.sql` — canonical MV migration pattern (structure, `SET statement_timeout`, `DROP IF EXISTS ... CASCADE`, indexes, unique index for `CONCURRENTLY` support)
5. `supabase/migrations/039_mv_fmcsa_analytical.sql` — second MV migration pattern reference
6. `supabase/migrations/036_mv_fmcsa_authority_grants.sql` — authority grants MV pattern
7. `supabase/migrations/037_mv_fmcsa_insurance_cancellations.sql` — insurance cancellations MV pattern
8. `scripts/refresh_analytical_views.sql` — current refresh script (all existing MVs, dependency order, frequency comments)
9. `app/services/fmcsa_carrier_query.py` — which FMCSA columns are actually queried and filtered
10. `app/services/federal_leads_query.py` — which federal data columns are actually queried and filtered

---

## Deliverable 1: Audit Phase (no commit — investigative only)

Run the following SQL queries against production using the correct Doppler wrapper. Do not skip any query. Record every result — you will use them to write the inventory document and design the migration.

**Production database access pattern:**
```bash
doppler run -p data-engine-x-api -c prd -- bash -c 'psql "$DATABASE_URL" -c "YOUR SQL"'
```

Always use the `bash -c` wrapper. `$DATABASE_URL` must expand inside Doppler's environment, not before.

### 1a. Enumerate all existing materialized views

```sql
SELECT
    schemaname,
    matviewname,
    definition,
    ispopulated
FROM pg_matviews
WHERE schemaname = 'entities'
ORDER BY matviewname;
```

For each MV, also run:

```sql
SELECT COUNT(*) FROM entities.<matviewname>;
```

And:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'entities' AND tablename = '<matviewname>'
ORDER BY indexname;
```

### 1b. Enumerate all non-MV tables in entities with more than 10K rows

```sql
SELECT
    relname AS table_name,
    reltuples::BIGINT AS estimated_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_matviews mv ON mv.matviewname = c.relname AND mv.schemaname = n.nspname
WHERE n.nspname = 'entities'
  AND c.relkind = 'r'
  AND mv.matviewname IS NULL
  AND c.reltuples > 10000
ORDER BY reltuples DESC;
```

### 1c. SAM.gov entities — column inventory and type distribution

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'entities' AND table_name = 'sam_gov_entities'
ORDER BY ordinal_position;
```

Then sample 5 rows to see actual values:

```sql
SELECT * FROM entities.sam_gov_entities LIMIT 5;
```

Then check key distribution columns:

```sql
SELECT
    registration_status,
    COUNT(*) AS cnt
FROM entities.sam_gov_entities
GROUP BY registration_status
ORDER BY cnt DESC
LIMIT 20;
```

```sql
SELECT
    physical_state_or_province,
    COUNT(*) AS cnt
FROM entities.sam_gov_entities
GROUP BY physical_state_or_province
ORDER BY cnt DESC
LIMIT 20;
```

```sql
SELECT
    naics_code_highest,
    COUNT(*) AS cnt
FROM entities.sam_gov_entities
GROUP BY naics_code_highest
ORDER BY cnt DESC
LIMIT 20;
```

**If column names differ from the above** (e.g., if the column is `state` not `physical_state_or_province`), use the actual column names from the `information_schema.columns` result. Do not assume column names — look them up first.

Also check whether `sam_gov_entities` has a snapshot/feed_date pattern:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'entities' AND table_name = 'sam_gov_entities'
  AND column_name ILIKE '%date%' OR column_name ILIKE '%feed%' OR column_name ILIKE '%snapshot%'
ORDER BY ordinal_position;
```

And check existing indexes:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'entities' AND tablename = 'sam_gov_entities'
ORDER BY indexname;
```

### 1d. SBA 7(a) Loans — column inventory and type distribution

```sql
SELECT
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'entities' AND table_name = 'sba_7a_loans'
ORDER BY ordinal_position;
```

Sample rows:

```sql
SELECT * FROM entities.sba_7a_loans LIMIT 5;
```

Distribution check:

```sql
SELECT
    borrower_state,
    COUNT(*) AS cnt,
    SUM(gross_approval::NUMERIC) AS total_gross_approval
FROM entities.sba_7a_loans
WHERE gross_approval ~ '^\d'
GROUP BY borrower_state
ORDER BY cnt DESC
LIMIT 20;
```

**If `gross_approval` or `borrower_state` columns do not exist under those names**, use the actual column names from the information_schema result. The loan amount column and borrower geography column may have different names — discover them from the schema, then query against the actual names.

Also check the date/snapshot pattern:

```sql
SELECT column_name
FROM information_schema.columns
WHERE table_schema = 'entities' AND table_name = 'sba_7a_loans'
  AND (column_name ILIKE '%date%' OR column_name ILIKE '%feed%' OR column_name ILIKE '%year%')
ORDER BY ordinal_position;
```

Existing indexes:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'entities' AND tablename = 'sba_7a_loans'
ORDER BY indexname;
```

### 1e. FMCSA gap check — confirm what the 6 existing FMCSA MVs cover

For each FMCSA materialized view (authority grants, insurance cancellations, latest census, latest safety percentiles, crash counts 12mo, carrier master), record:
- Source table(s)
- What it pre-computes (join, aggregation, latest-snapshot filter, type cast)
- Whether a "latest insurance policies snapshot" or "latest carrier registrations snapshot" MV exists. If not, note the gap.
- Whether the carrier master MV already joins the insurance posture.

Check whether these tables exist and their row counts (for MV gap assessment):

```sql
SELECT relname, reltuples::BIGINT AS estimated_rows
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'entities'
  AND c.relkind = 'r'
  AND c.relname IN (
    'insurance_policies',
    'insurance_policy_filings',
    'insurance_policy_history_events',
    'carrier_registrations',
    'operating_authority_histories',
    'operating_authority_revocations'
  )
ORDER BY c.relname;
```

---

## Deliverable 2: Inventory Document

**File:** `docs/MATERIALIZED_VIEWS_INVENTORY.md`

Create this document using the audit results from Deliverable 1. It must be factual and grounded in what the audit actually found — do not fill in placeholder values.

Structure:

```markdown
# Materialized Views Inventory

**Last updated:** 2026-03-19
**Production state:** as of this audit date. Row counts from live production SQL.

## Summary

[Table: every MV in entities schema — name, source table(s), row count, refresh frequency, status (existing / proposed)]

## Existing Materialized Views

For each existing MV, one subsection:

### entities.<matviewname>
- **Source table(s):** ...
- **Row count:** ... (verified production)
- **Pre-computes:** [what join, aggregation, type cast, or filter it applies]
- **Indexes:** [list of index names and columns]
- **Recommended refresh:** DAILY / WEEKLY / ON_DEMAND
- **Migration:** [migration number that created it]

## Proposed Materialized Views

For each proposed MV:

### entities.<proposed_name>
- **Source table(s):** ...
- **Estimated row count:** ...
- **Pre-computes:** [exact description]
- **Proposed indexes:** [name and column for each]
- **Recommended refresh:** DAILY / WEEKLY / ON_DEMAND
- **Rationale:** [one sentence on why this is high-value]
- **Migration:** 042

## Tables Without MVs (>10K rows)

[Table: table name, row count, has_feed_date_pattern, has_snapshot_pattern, has_typed_MV, proposed_MV_name or "none recommended"]

## Cross-Vertical Joins

[For each proposed cross-vertical MV: which tables it joins, join key(s), what it enables]
```

**Required proposed MVs** — the inventory must include proposals for at least these, if the audit confirms the data supports them. If the audit reveals that a specific column does not exist or the data makes a proposal impractical, state that and propose an alternative or drop it with an explanation.

1. `mv_sam_gov_entities_typed` — typed base view for sam_gov_entities with date and numeric columns cast from TEXT. Modeled after `mv_usaspending_contracts_typed`. If sam_gov_entities uses native types (not TEXT), note that and propose a curated-column subset view instead.

2. `mv_sam_gov_entities_by_state` — aggregate by registration state: entity count, count by registration status. Useful for geographic targeting. Only propose if the geographic column exists and has reasonable cardinality.

3. `mv_sam_gov_entities_by_naics` — aggregate by NAICS code prefix: entity count. Useful for vertical targeting. Only propose if a NAICS column exists.

4. `mv_sba_loans_typed` — typed base view for sba_7a_loans with loan amount columns cast to NUMERIC and date columns cast to DATE. Modeled after `mv_usaspending_contracts_typed`.

5. `mv_sba_loans_by_state` — aggregate by borrower state: loan count, total gross approval, average loan size. For geographic outbound targeting.

6. `mv_sam_usaspending_bridge` — cross-vertical: sam_gov_entities joined to mv_usaspending_contracts_typed on `recipient_uei` (or equivalent UEI column in SAM.gov if named differently). Pre-computes: total award count, total obligated dollars, first and latest contract dates, top NAICS. Only propose if the join key exists in both tables — confirm column name from audit. This is the highest-value cross-vertical view.

7. Any additional FMCSA MVs the audit reveals as missing gaps — for example: latest insurance policy snapshot per carrier, latest carrier registration snapshot per carrier, new carriers (first seen within last 90 days based on `add_date` or equivalent), or carriers with deteriorating safety scores (requires `carrier_safety_basic_percentiles` data). Only propose MVs where the source data supports the computation. If an FMCSA gap exists but the source data cannot support it (e.g., no usable timestamp column), state that explicitly.

Commit standalone: `"Add MATERIALIZED_VIEWS_INVENTORY.md — audit and proposals"`

---

## Deliverable 3: Migration File

**File:** `supabase/migrations/042_mv_analytical_expansion.sql`

Write every proposed MV from Deliverable 2 as production-ready SQL in this single migration file. Follow the pattern from `supabase/migrations/038_mv_usaspending_analytical.sql` exactly:

- Start with `SET statement_timeout = '0';`
- End with `RESET statement_timeout;`
- No `BEGIN`/`COMMIT` wrapper
- For each MV:
  - `DROP MATERIALIZED VIEW IF EXISTS entities.<name> CASCADE;`
  - `CREATE MATERIALIZED VIEW entities.<name> AS ...`
  - A **unique index** on the natural key (required for `REFRESH MATERIALIZED VIEW CONCURRENTLY`)
  - Additional indexes on commonly filtered/joined columns
- Comment each MV with: source table(s), refresh frequency, purpose
- If two MVs have a dependency (e.g., a cross-vertical view depends on a typed base view), create the base view first and note the dependency in a comment

**Index naming convention:** `idx_mv_<short_mv_name>_<column>` — follow the existing convention from migration 038.

**Do NOT apply this migration to production.** Commit the file only.

If a proposed MV from the inventory turns out to be impractical to implement in SQL given the actual column types discovered in the audit (e.g., no join key exists), drop it from the migration and document the reason in the inventory doc instead.

Commit standalone: `"Add migration 042: analytical MV expansion — SAM.gov, SBA, cross-vertical, FMCSA gaps"`

---

## Deliverable 4: Update Refresh Script

**File:** `scripts/refresh_analytical_views.sql`

Add `REFRESH MATERIALIZED VIEW CONCURRENTLY` statements for every new MV in migration 042. Follow the existing format:

- Group by frequency: DAILY, WEEKLY, ON_DEMAND
- Respect dependency order: base views before derived views (e.g., `mv_sam_gov_entities_typed` before `mv_sam_usaspending_bridge`)
- Add a comment above each new block identifying the migration that created it

Do NOT modify existing entries in the refresh script. Only append new entries.

Update the header frequency guide if new frequencies are introduced.

Commit standalone: `"Update refresh_analytical_views.sql to include migration 042 MVs"`

---

## Final Deliverable: Work Log Entry

Append an entry to `docs/EXECUTOR_WORK_LOG.md` following the format defined in that file.

Include:
- Which MVs were found to exist in production (names + row counts from audit)
- Which MVs were proposed and written into migration 042 (names)
- Any proposals from the directive that were dropped after the audit revealed they were impractical, and why
- Any surprising findings (e.g., SAM.gov columns are already native types and don't need casting, or no UEI join key exists in SAM.gov)

This is your final commit.

---

## What is NOT in scope

- **No production migrations.** Do not run `psql` to apply migration 042 to production. Commit the file only.
- **No changes to FastAPI routers, services, or provider adapters.** This directive is data-layer only.
- **No changes to existing migration files** (001–041). Read them for reference; do not edit them.
- **No changes to `docs/OPERATIONAL_REALITY_CHECK_2026-03-18.md` or `CLAUDE.md`.** Documentation updates of that type are a separate deliverable class.
- **No pushing.** Commit locally only.

---

## Commit convention

Each deliverable is one commit. Four commits total (inventory doc, migration file, refresh script, work log). Do not push.

---

## When done

Report back with:

**(a) Audit findings summary:**
- Total MVs found in production (names + row counts)
- SAM.gov: actual column types for the most important columns (registration status, state, NAICS, UEI/EIN key, date columns). Note whether columns are TEXT or native types.
- SBA: actual column types for loan amount and borrower geography columns. Note whether loan amount columns are TEXT or NUMERIC.
- FMCSA gap: list any missing snapshot MVs that would be high-value (or confirm all gaps are covered)
- Cross-vertical: confirm whether a UEI join key exists in both sam_gov_entities and usaspending_contracts

**(b) Proposed MVs built into migration 042:** list each MV name

**(c) Proposed MVs dropped after audit:** list each with reason

**(d) Refresh script:** confirm all new MVs added with correct dependency order

**(e) Anything to flag:** column names that differ from what the directive assumed, data quality issues that make a proposed MV impractical, estimated migration runtime warnings (flag any MV that will scan >5M rows for the chief agent's awareness)
