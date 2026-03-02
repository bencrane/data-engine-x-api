# Directive: Job Title Matching — Phase 1 (Schema Work)

**Context:** You are working directly on the HQ Postgres database (Supabase). You have access to run SQL via the Supabase SQL editor or psql. This directive involves schema changes only — no data updates, no batch processing.

**Scope:** Do exactly what is specified below. Do not do anything beyond these steps. Do not optimize queries, do not restructure tables, do not add columns not listed here. If something is unclear, stop and ask.

---

## What You Are Doing

Adding generated columns and indexes to two tables so that future job title matching queries can use indexed lookups instead of runtime `LOWER(TRIM(...))` on millions of rows.

---

## Tables Involved

**`core.person_work_history`** (~2.6M rows)
- Has column `title` (raw job title, e.g., "Sr. Software Engineer")
- Needs a generated column that stores `LOWER(TRIM(title))`

**`reference.job_title_lookup`** (~1.2M rows)
- Has column `raw_job_title` (raw title string to match against)
- Needs a generated column that stores `LOWER(TRIM(raw_job_title))`

---

## Step 1: Add generated column to `reference.job_title_lookup`

Run this SQL:

```sql
ALTER TABLE reference.job_title_lookup
ADD COLUMN raw_job_title_normalized TEXT
GENERATED ALWAYS AS (LOWER(TRIM(raw_job_title))) STORED;
```

Then create the index (CONCURRENTLY so it doesn't lock the table):

```sql
CREATE INDEX CONCURRENTLY idx_job_title_lookup_raw_normalized
ON reference.job_title_lookup(raw_job_title_normalized);
```

**Verify by running:**

```sql
SELECT raw_job_title, raw_job_title_normalized
FROM reference.job_title_lookup
LIMIT 5;
```

---

## Step 2: Add generated column to `core.person_work_history`

Run this SQL:

```sql
ALTER TABLE core.person_work_history
ADD COLUMN title_normalized TEXT
GENERATED ALWAYS AS (LOWER(TRIM(title))) STORED;
```

Then create the index:

```sql
CREATE INDEX CONCURRENTLY idx_person_work_history_title_normalized
ON core.person_work_history(title_normalized);
```

**Verify by running:**

```sql
SELECT title, title_normalized
FROM core.person_work_history
WHERE title IS NOT NULL
LIMIT 5;
```

---

## When Done

Report back with:
1. The verification output from Step 1 (5 rows showing raw_job_title and raw_job_title_normalized)
2. The verification output from Step 2 (5 rows showing title and title_normalized)
3. Confirmation that both indexes were created successfully
4. If any errors occurred, the exact error message

Do not proceed to any other work after this. Wait for instructions.
