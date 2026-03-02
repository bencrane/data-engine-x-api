# Job Title Matching: Situation & Plan

## Overview

We have raw job titles in `core.person_work_history` that need to be matched to cleaned/normalized job titles in `reference.job_title_lookup`. This document explains the current state, the problem, and two approaches to solving it.

---

## Current State

### Tables Involved

| Table | Row Count | Purpose |
|-------|-----------|---------|
| `core.person_work_history` | ~2.6M | Master table of all work history records |
| `reference.job_title_lookup` | ~1.2M | Reference table mapping raw → cleaned job titles |

### Relevant Columns

**core.person_work_history:**
```
title                      -- raw job title (e.g., "Sr. Software Engineer")
matched_cleaned_job_title  -- populated by matching to reference table (e.g., "Senior Software Engineer")
matched_job_function       -- e.g., "Engineering"
matched_seniority          -- e.g., "Senior"
```

**reference.job_title_lookup:**
```
raw_job_title      -- the raw title string to match against
cleaned_job_title  -- the normalized/cleaned version
seniority_level    -- e.g., "Senior", "Manager"
job_function       -- e.g., "Engineering", "Sales"
status             -- e.g., "cleaned"
```

### Current Indexes

**reference.job_title_lookup:**
- `idx_job_title_lookup` on `raw_job_title` (B-tree)

**core.person_work_history:**
- `idx_pwh_linkedin_url` on `linkedin_url`
- `idx_pwh_company_domain` on `company_domain`
- `idx_pwh_is_current` on `is_current`
- No index on `title`

---

## The Problem

### Scale
- ~450K unique raw job titles in work_history have no match in job_title_lookup
- ~850K total work_history records are unmatched
- ~180K records where `is_current = true` are unmatched

### Performance Issue
Matching requires comparing `person_work_history.title` to `job_title_lookup.raw_job_title`. Without proper indexes, this means:
- Full table scans on 2.6M rows
- Runtime `LOWER(TRIM(...))` computation if we want case-insensitive matching
- Queries timeout on large JOINs

---

## Option A: Quick Batched Updates (No Schema Changes)

This is what we've been doing. It works but is less efficient.

### How It Works

1. Identify newly added reference records by `created_at` timestamp
2. Run batched UPDATE with LIMIT to avoid timeout
3. Repeat until all matches are populated

### SQL

**Step 1: Find timestamp of recent batch**
```sql
SELECT created_at, COUNT(*)
FROM reference.job_title_lookup
GROUP BY created_at
ORDER BY created_at DESC
LIMIT 10;
```

**Step 2: Count how many will be updated**
```sql
WITH recent_batch AS (
  SELECT DISTINCT ON (raw_job_title)
    raw_job_title,
    cleaned_job_title
  FROM reference.job_title_lookup
  WHERE created_at >= '2026-02-25 16:29:52+00'  -- adjust timestamp
    AND cleaned_job_title IS NOT NULL
  ORDER BY raw_job_title, created_at DESC
)
SELECT COUNT(*)
FROM core.person_work_history pwh
JOIN recent_batch rb ON pwh.title = rb.raw_job_title
WHERE pwh.matched_cleaned_job_title IS NULL;
```

**Step 3: Run in batches of 30K until done**
```sql
WITH recent_batch AS (
  SELECT DISTINCT ON (raw_job_title)
    raw_job_title,
    cleaned_job_title
  FROM reference.job_title_lookup
  WHERE created_at >= '2026-02-25 16:29:52+00'  -- adjust timestamp
    AND cleaned_job_title IS NOT NULL
  ORDER BY raw_job_title, created_at DESC
),
to_update AS (
  SELECT pwh.id
  FROM core.person_work_history pwh
  JOIN recent_batch rb ON pwh.title = rb.raw_job_title
  WHERE pwh.matched_cleaned_job_title IS NULL
  LIMIT 30000
)
UPDATE core.person_work_history pwh
SET matched_cleaned_job_title = rb.cleaned_job_title
FROM recent_batch rb
WHERE pwh.title = rb.raw_job_title
  AND pwh.id IN (SELECT id FROM to_update);
```

### Pros
- No schema changes required
- Works immediately
- Good for one-off catches after CSV uploads

### Cons
- Slow for large datasets
- Requires exact case/whitespace matching (no `LOWER(TRIM(...))`)
- Must be re-run manually after each upload

---

## Option B: Generated Columns + Indexes (Recommended Long-Term)

This approach pre-computes normalized values and indexes them for fast lookups.

### Concept

Instead of computing `LOWER(TRIM(title))` at query time for 2.6M rows, we:
1. Add a "generated column" that stores the pre-computed value
2. Index that column
3. JOIN on the indexed columns

### What Are Generated Columns?

A generated column is automatically computed from other columns:

```sql
ALTER TABLE my_table
ADD COLUMN title_normalized TEXT
GENERATED ALWAYS AS (LOWER(TRIM(title))) STORED;
```

- `STORED` means the value is physically written to disk
- Postgres automatically updates it when the source column changes
- Can be indexed like any other column

---

## Option B: Implementation Phases

Each phase is independent. You can stop after any phase and continue later.

### Phase 1: Add Generated Column to reference.job_title_lookup

**What happens:** Postgres adds a new column and computes `LOWER(TRIM(raw_job_title))` for all 1.2M existing rows.

**Time estimate:** 2-5 minutes

```sql
-- Add the generated column
ALTER TABLE reference.job_title_lookup
ADD COLUMN raw_job_title_normalized TEXT
GENERATED ALWAYS AS (LOWER(TRIM(raw_job_title))) STORED;

-- Index it (CONCURRENTLY = non-blocking)
CREATE INDEX CONCURRENTLY idx_job_title_lookup_raw_normalized
ON reference.job_title_lookup(raw_job_title_normalized);
```

**Verification:**
```sql
SELECT raw_job_title, raw_job_title_normalized
FROM reference.job_title_lookup
LIMIT 5;
```

---

### Phase 2: Add Generated Column to core.person_work_history

**What happens:** Postgres adds a new column and computes `LOWER(TRIM(title))` for all 2.6M existing rows.

**Time estimate:** 3-7 minutes

```sql
-- Add the generated column
ALTER TABLE core.person_work_history
ADD COLUMN title_normalized TEXT
GENERATED ALWAYS AS (LOWER(TRIM(title))) STORED;

-- Index it (CONCURRENTLY = non-blocking)
CREATE INDEX CONCURRENTLY idx_person_work_history_title_normalized
ON core.person_work_history(title_normalized);
```

**Verification:**
```sql
SELECT title, title_normalized
FROM core.person_work_history
WHERE title IS NOT NULL
LIMIT 5;
```

---

### Phase 3: Batched Update Using Indexed Columns

**What happens:** UPDATE joins on the indexed normalized columns. Much faster than Option A.

**Time estimate:** 5-15 minutes total (run in batches)

**Count how many need updating:**
```sql
SELECT COUNT(*)
FROM core.person_work_history pwh
JOIN reference.job_title_lookup jt
  ON pwh.title_normalized = jt.raw_job_title_normalized
WHERE pwh.matched_cleaned_job_title IS NULL
  AND jt.cleaned_job_title IS NOT NULL;
```

**Run in batches of 50K:**
```sql
WITH to_update AS (
  SELECT pwh.id, jt.cleaned_job_title
  FROM core.person_work_history pwh
  JOIN reference.job_title_lookup jt
    ON pwh.title_normalized = jt.raw_job_title_normalized
  WHERE pwh.matched_cleaned_job_title IS NULL
    AND jt.cleaned_job_title IS NOT NULL
  LIMIT 50000
)
UPDATE core.person_work_history pwh
SET matched_cleaned_job_title = tu.cleaned_job_title
FROM to_update tu
WHERE pwh.id = tu.id;
```

Repeat until 0 rows affected.

---

### Phase 4 (Optional): Handle Duplicates in job_title_lookup

If the same `raw_job_title` appears multiple times with different `cleaned_job_title` values, the JOIN picks arbitrarily. For deterministic results, use DISTINCT ON:

```sql
WITH deduped AS (
  SELECT DISTINCT ON (raw_job_title_normalized)
    raw_job_title_normalized,
    cleaned_job_title
  FROM reference.job_title_lookup
  WHERE cleaned_job_title IS NOT NULL
  ORDER BY raw_job_title_normalized, created_at DESC  -- latest wins
)
...
```

Or create a materialized view for reuse:

```sql
CREATE MATERIALIZED VIEW reference.job_title_lookup_deduped AS
SELECT DISTINCT ON (raw_job_title_normalized)
  raw_job_title,
  raw_job_title_normalized,
  cleaned_job_title,
  seniority_level,
  job_function
FROM reference.job_title_lookup
WHERE cleaned_job_title IS NOT NULL
ORDER BY raw_job_title_normalized, created_at DESC;

CREATE INDEX idx_job_title_lookup_deduped_normalized
ON reference.job_title_lookup_deduped(raw_job_title_normalized);
```

---

## Comparison: Option A vs Option B

| Aspect | Option A (Quick Batches) | Option B (Generated Columns) |
|--------|--------------------------|------------------------------|
| Schema changes | None | Add 2 columns + 2 indexes |
| Setup time | 0 | ~10-15 minutes |
| Per-batch speed | Slower (no index on title) | Faster (indexed join) |
| Case-insensitive | No (exact match only) | Yes (normalized) |
| Future updates | Manual re-run | Same query, just faster |
| One-off CSV upload | Good | Overkill |
| Ongoing operations | Tedious | Efficient |

---

## Recommendation

- **For one-off catches** (e.g., just uploaded 40K cleaned titles): Use Option A
- **For ongoing operations** (regular syncs, large datasets): Implement Option B

Option B is a one-time investment that pays off every time you run a sync.

---

## Current Progress (as of 2026-02-25)

### What's Done
- `matched_cleaned_job_title` column exists on `core.person_work_history`
- Multiple batches of cleaned job titles uploaded to `reference.job_title_lookup`
- Option A batched updates run for recent uploads

### What's Not Done
- Generated columns not added
- Normalized indexes not created
- Full backfill of all matchable records not complete

### Stats
- ~180K current job records still unmatched
- ~450K unique raw titles have no reference entry yet
- ~850K total work_history records unmatched

---

## Related: person_experience → person_work_history Sync

The same timeout problem affects syncing `extracted.person_experience` to `core.person_work_history`. Similar solution would apply:

1. Add `experience_key` generated column (composite of linkedin_url + normalized company)
2. Index it on both tables
3. Fast indexed lookup for "what's not synced yet"

This is separate work but follows the same pattern.

---

## Appendix: Useful Queries

**Check how many work_history records are unmatched:**
```sql
SELECT COUNT(*)
FROM core.person_work_history
WHERE matched_cleaned_job_title IS NULL
  AND title IS NOT NULL;
```

**Check unmatched for current jobs only:**
```sql
SELECT COUNT(*)
FROM core.person_work_history
WHERE is_current = true
  AND matched_cleaned_job_title IS NULL;
```

**Top unmatched titles by frequency:**
```sql
SELECT
  title AS raw_job_title,
  COUNT(*) AS occurrence_count
FROM core.person_work_history
WHERE matched_cleaned_job_title IS NULL
  AND title IS NOT NULL
GROUP BY title
ORDER BY COUNT(*) DESC
LIMIT 100;
```

**Check if generated columns exist:**
```sql
SELECT column_name, data_type, generation_expression
FROM information_schema.columns
WHERE table_schema = 'core'
  AND table_name = 'person_work_history'
  AND column_name = 'title_normalized';
```
