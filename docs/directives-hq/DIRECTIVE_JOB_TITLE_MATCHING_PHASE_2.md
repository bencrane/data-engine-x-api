# Directive: Job Title Matching — Phase 2 (Experience Key Hash + Dedup)

**Context:** You are working directly on the HQ Postgres database (Supabase). Phase 1 is complete — generated columns and indexes exist on both tables. This phase populates the `experience_key` column for deduplication and removes duplicate rows.

**Scope:** Do exactly what is specified below. Work in batches. Report back after each batch. Do not proceed to the next step without being told "continue."

---

## What You Are Doing

1. Populating the `experience_key` column on `core.person_work_history` with a composite hash that uniquely identifies each work experience record.
2. Removing duplicate rows (same person, same company, same title, same start date).
3. Adding a unique index on `experience_key` to prevent future duplicates.

---

## Step 1: Populate experience_key in batches

The `experience_key` column already exists on `core.person_work_history` (TEXT, nullable). Populate it with an MD5 hash of the composite key.

**First, count how many rows need the key:**

```sql
SELECT COUNT(*)
FROM core.person_work_history
WHERE experience_key IS NULL;
```

**Then run in batches of 50,000. Run this query, report the result, and wait for "continue":**

```sql
WITH to_update AS (
  SELECT id
  FROM core.person_work_history
  WHERE experience_key IS NULL
  LIMIT 50000
)
UPDATE core.person_work_history pwh
SET experience_key = MD5(
  COALESCE(pwh.linkedin_url, '') || '::' ||
  COALESCE(pwh.company_domain, pwh.company_name, '') || '::' ||
  COALESCE(LOWER(TRIM(pwh.title)), '') || '::' ||
  COALESCE(pwh.start_date::TEXT, '')
)
WHERE pwh.id IN (SELECT id FROM to_update);
```

**After each batch, report:**
- How many rows were updated
- How many rows still have `experience_key IS NULL` (run the count query again)

**Wait for "continue" before running the next batch.**

Repeat until 0 rows remain with NULL experience_key.

---

## Step 2: Identify duplicates

After ALL experience_key values are populated, check for duplicates:

```sql
SELECT experience_key, COUNT(*) AS cnt
FROM core.person_work_history
WHERE experience_key IS NOT NULL
GROUP BY experience_key
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 20;
```

**Report:**
- Total number of experience_key values that have duplicates
- The top 20 duplicate groups with their counts
- Total number of rows that would be deleted (sum of cnt - 1 for all duplicate groups)

**Wait for approval before deleting anything.**

---

## Step 3: Delete duplicates (only after approval)

For each group of duplicates, keep the row with the most recent `created_at` and delete the rest:

```sql
DELETE FROM core.person_work_history
WHERE id IN (
  SELECT id FROM (
    SELECT id,
      ROW_NUMBER() OVER (
        PARTITION BY experience_key
        ORDER BY created_at DESC
      ) AS rn
    FROM core.person_work_history
    WHERE experience_key IS NOT NULL
  ) ranked
  WHERE rn > 1
);
```

**If more than 100K rows would be deleted, run in batches:**

```sql
WITH to_delete AS (
  SELECT id FROM (
    SELECT id,
      ROW_NUMBER() OVER (
        PARTITION BY experience_key
        ORDER BY created_at DESC
      ) AS rn
    FROM core.person_work_history
    WHERE experience_key IS NOT NULL
  ) ranked
  WHERE rn > 1
  LIMIT 50000
)
DELETE FROM core.person_work_history
WHERE id IN (SELECT id FROM to_delete);
```

Report after each batch. Wait for "continue."

---

## Step 4: Add unique index on experience_key

After dedup is complete:

```sql
CREATE UNIQUE INDEX CONCURRENTLY idx_pwh_experience_key
ON core.person_work_history(experience_key);
```

**Verify:**

```sql
SELECT COUNT(*) AS total_rows,
       COUNT(DISTINCT experience_key) AS unique_keys
FROM core.person_work_history
WHERE experience_key IS NOT NULL;
```

These two numbers should be equal.

---

## When Done

Report back with:
1. Total rows that had experience_key populated
2. Number of duplicate groups found
3. Number of rows deleted
4. Verification that total_rows = unique_keys after dedup
5. Confirmation that unique index was created
6. Any errors

Do not proceed to any other work. Wait for instructions.
