# Directive: Phase 3 — Migrate person_experience → person_work_history

**Context:** You are working directly on the HQ Postgres database (Supabase). Phases 1 and 2 are complete — generated columns, indexes, experience_key hash, dedup, and unique index are all in place on `core.person_work_history`. This phase pushes records from `extracted.person_experience` into `core.person_work_history`.

**Scope:** Do exactly what is specified below. Work in batches. Report back after each batch. Do not proceed without being told "continue." Do NOT do any job title matching — that is separate work.

---

## What You Are Doing

Inserting records from `extracted.person_experience` into `core.person_work_history`. Using `ON CONFLICT` on the `experience_key` to skip records that already exist (dedup). Only inserting records that have a `company_domain` value.

---

## Step 1: Count records to migrate

**Total eligible records in person_experience (have company_domain):**

```sql
SELECT COUNT(*)
FROM extracted.person_experience
WHERE company_domain IS NOT NULL;
```

**Records already in person_work_history (for reference):**

```sql
SELECT COUNT(*)
FROM core.person_work_history;
```

**Report both numbers and wait for "continue."**

---

## Step 2: Insert in batches of 50,000

```sql
WITH to_insert AS (
  SELECT
    pe.linkedin_url,
    pe.company_domain,
    pe.company AS company_name,
    pe.company_linkedin_url,
    pe.title,
    pe.matched_job_function,
    pe.matched_seniority,
    pe.start_date,
    pe.end_date,
    pe.is_current,
    pe.experience_order,
    pe.id AS source_id,
    pe.matched_cleaned_job_title,
    pe.matched_company_domain,
    MD5(
      COALESCE(pe.linkedin_url, '') || '::' ||
      COALESCE(pe.company_domain, pe.company, '') || '::' ||
      COALESCE(LOWER(TRIM(pe.title)), '') || '::' ||
      COALESCE(pe.start_date::TEXT, '')
    ) AS experience_key
  FROM extracted.person_experience pe
  WHERE pe.company_domain IS NOT NULL
  ORDER BY pe.created_at ASC
  LIMIT 50000
  OFFSET {OFFSET}
)
INSERT INTO core.person_work_history (
  linkedin_url,
  company_domain,
  company_name,
  company_linkedin_url,
  title,
  matched_job_function,
  matched_seniority,
  start_date,
  end_date,
  is_current,
  experience_order,
  source_id,
  matched_cleaned_job_title,
  matched_company_domain,
  experience_key
)
SELECT
  linkedin_url,
  company_domain,
  company_name,
  company_linkedin_url,
  title,
  matched_job_function,
  matched_seniority,
  start_date,
  end_date,
  is_current,
  experience_order,
  source_id,
  matched_cleaned_job_title,
  matched_company_domain,
  experience_key
FROM to_insert
ON CONFLICT (experience_key) DO NOTHING;
```

**Replace `{OFFSET}` with 0 for the first batch, 50000 for the second, 100000 for the third, etc.**

**After each batch, report:**
- How many rows were inserted (INSERT count)
- How many were skipped (conflicts / already existed)
- Current OFFSET value
- Current total in person_work_history:

```sql
SELECT COUNT(*) FROM core.person_work_history;
```

**Wait for "continue" before running the next batch.**

Repeat until a batch inserts 0 new rows (all remaining are duplicates or you've passed the total eligible count).

---

## When Done

Report back with:
1. Total eligible records in person_experience (from Step 1)
2. Total new rows inserted across all batches
3. Total rows skipped (already existed)
4. Final row count in person_work_history
5. Any errors

Do not proceed to any other work. Wait for instructions.
