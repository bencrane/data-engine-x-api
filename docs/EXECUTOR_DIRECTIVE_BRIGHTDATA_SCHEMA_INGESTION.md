# Directive: Bright Data Job Listings — Schema + Ingestion (HQ Repo)

**Context:** You are working on the HQ repo (revenueinfra). This repo uses FastAPI + Modal functions. Modal functions handle data ingestion. FastAPI wraps Modal functions via thin endpoints. Database owns all business logic. Database is Supabase Postgres.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We are building a staffing agency revenue activation product. Bright Data delivers job listing snapshots from Indeed and LinkedIn. These are used as validation sources — we compare them against TheirStack job postings to determine whether a job is still active. This directive builds the database tables and ingestion layer that stores Bright Data payloads in the HQ warehouse. The delivery mechanism (how data arrives from Bright Data) is a separate concern wired later.

---

## Sample Payloads

The sample payloads below are the exact shapes Bright Data delivers. Every field must be stored — both as structured columns for querying and as a `raw_payload` JSONB column for auditability.

### Indeed Job Listing (per record)

```json
{
  "jobid": "4c54d0a12f9acd42",
  "company_name": "Cleveland-Cliffs",
  "date_posted_parsed": null,
  "job_title": "Accountant",
  "description_text": "Cleveland-Cliffs Steel Corporation has an opening for an Accountant...",
  "benefits": ["Tuition reimbursement", "Health insurance", "Retirement plan", "Paid time off"],
  "qualifications": null,
  "job_type": "Full-time",
  "location": "Butler, PA",
  "salary_formatted": null,
  "company_rating": 3.3,
  "company_reviews_count": 752,
  "country": "US",
  "date_posted": "30+ days ago",
  "description": "Cleveland-Cliffs Steel Corporation has an opening for an Accountant...",
  "region": "PA",
  "company_link": "https://www.indeed.com/cmp/Cleveland--cliffs-1?campaignid=mobvjcmp&...",
  "company_website": null,
  "domain": "https://www.indeed.com",
  "apply_link": null,
  "srcname": null,
  "url": "https://www.indeed.com/viewjob?jk=6c28c98586a858da",
  "is_expired": true,
  "discovery_input": null,
  "job_location": "Butler, PA",
  "job_description_formatted": "<div>...</div>",
  "logo_url": "https://d2q79iu7y748jz.cloudfront.net/s/_squarelogo/256x256/...",
  "shift_schedule": ["Day shift"]
}
```

**Key notes on Indeed data:**
- `jobid` is the natural key (hex hash string)
- `date_posted` is relative ("30+ days ago"), NOT an ISO date — unreliable for time-based queries
- `date_posted_parsed` is often null
- `domain` is always "indeed.com" (source site), NOT the company's domain
- `is_expired` is the critical field for validation — direct signal that a job is no longer active
- `description` and `description_text` appear to contain the same content (store both)
- `location` and `job_location` are similar but formatted differently (store both)

### LinkedIn Job Listing (per record)

```json
{
  "url": "https://www.linkedin.com/jobs/view/accountant-at-workday-4304285112?_l=en",
  "job_posting_id": "4304285112",
  "job_title": "Accountant",
  "company_name": "Workday",
  "company_id": "17719",
  "job_location": "Heredia, Heredia, Costa Rica",
  "job_summary": "Your work days are brighter here. At Workday, it all began with...",
  "job_seniority_level": "Not Applicable",
  "job_function": "Accounting/Auditing and Finance",
  "job_employment_type": "Full-time",
  "job_industries": "Software Development",
  "job_base_pay_range": null,
  "company_url": "https://www.linkedin.com/company/workday?trk=public_jobs_topcard-org-name",
  "job_posted_time": "4 months ago",
  "job_num_applicants": 25,
  "discovery_input": {
    "experience_level": null,
    "job_type": null,
    "remote": null,
    "selective_search": null,
    "time_range": null
  },
  "apply_link": null,
  "country_code": null,
  "title_id": "40",
  "company_logo": "https://media.licdn.com/dms/image/v2/...",
  "job_posted_date": "2025-10-20T18:26:28.963Z",
  "job_poster": {
    "name": null,
    "title": null,
    "url": null
  },
  "application_availability": false,
  "job_description_formatted": "<section class=\"show-more-less-html\">...</section>",
  "base_salary": {
    "currency": null,
    "max_amount": null,
    "min_amount": null,
    "payment_period": null
  },
  "salary_standards": null,
  "is_easy_apply": false
}
```

**Key notes on LinkedIn data:**
- `job_posting_id` is the natural key (numeric string)
- `job_posted_date` is ISO 8601 — reliable timestamp
- `job_posted_time` is relative ("4 months ago") — store but don't rely on
- `country_code` is often null in practice
- `job_poster` is an object with name/title/url — often all null but sometimes populated (hiring manager data)
- `base_salary` is an object — often all null but structured when present
- `discovery_input` is an object — search parameters used, usually all null

---

## Deliverable 1: SQL Migration — Create Tables

Create a SQL migration file. The `raw` schema should already exist; if not, create it with `CREATE SCHEMA IF NOT EXISTS raw;`.

### Table: `raw.brightdata_indeed_job_listings`

```sql
CREATE TABLE IF NOT EXISTS raw.brightdata_indeed_job_listings (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_batch_id        UUID NOT NULL,
    first_seen_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Natural key
    jobid                     TEXT NOT NULL,

    -- Job details
    job_title                 TEXT,
    job_type                  TEXT,
    description_text          TEXT,
    description               TEXT,
    job_description_formatted TEXT,
    benefits                  JSONB,
    qualifications            TEXT,
    salary_formatted          TEXT,
    shift_schedule            JSONB,

    -- Company
    company_name              TEXT,
    company_rating            DOUBLE PRECISION,
    company_reviews_count     INTEGER,
    company_link              TEXT,
    company_website           TEXT,

    -- Location
    location                  TEXT,
    job_location              TEXT,
    country                   TEXT,
    region                    TEXT,

    -- Dates
    date_posted               TEXT,
    date_posted_parsed        TEXT,

    -- URLs
    url                       TEXT,
    apply_link                TEXT,
    domain                    TEXT,
    logo_url                  TEXT,

    -- Status
    is_expired                BOOLEAN,

    -- Metadata
    srcname                   TEXT,
    discovery_input           JSONB,

    -- Raw payload
    raw_payload               JSONB NOT NULL,

    CONSTRAINT uq_brightdata_indeed_jobid UNIQUE (jobid)
);

CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_company_name
    ON raw.brightdata_indeed_job_listings (company_name);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_job_title
    ON raw.brightdata_indeed_job_listings (job_title);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_is_expired
    ON raw.brightdata_indeed_job_listings (is_expired);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_ingestion_batch
    ON raw.brightdata_indeed_job_listings (ingestion_batch_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_ingested_at
    ON raw.brightdata_indeed_job_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_country
    ON raw.brightdata_indeed_job_listings (country);
CREATE INDEX IF NOT EXISTS idx_brightdata_indeed_region
    ON raw.brightdata_indeed_job_listings (region);
```

### Table: `raw.brightdata_linkedin_job_listings`

```sql
CREATE TABLE IF NOT EXISTS raw.brightdata_linkedin_job_listings (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ingestion_batch_id        UUID NOT NULL,
    first_seen_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    ingested_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Natural key
    job_posting_id            TEXT NOT NULL,

    -- Job details
    job_title                 TEXT,
    job_summary               TEXT,
    job_seniority_level       TEXT,
    job_function              TEXT,
    job_employment_type       TEXT,
    job_industries            TEXT,
    job_base_pay_range        TEXT,
    job_description_formatted TEXT,
    is_easy_apply             BOOLEAN,

    -- Salary (structured)
    base_salary_currency      TEXT,
    base_salary_min_amount    DOUBLE PRECISION,
    base_salary_max_amount    DOUBLE PRECISION,
    base_salary_payment_period TEXT,
    salary_standards          TEXT,

    -- Company
    company_name              TEXT,
    company_id                TEXT,
    company_url               TEXT,
    company_logo              TEXT,

    -- Location
    job_location              TEXT,
    country_code              TEXT,

    -- Dates
    job_posted_date           TIMESTAMPTZ,
    job_posted_time           TEXT,

    -- URLs
    url                       TEXT,
    apply_link                TEXT,

    -- Applicant info
    job_num_applicants        INTEGER,

    -- Job poster (structured)
    job_poster_name           TEXT,
    job_poster_title          TEXT,
    job_poster_url            TEXT,

    -- Application
    application_availability  BOOLEAN,

    -- Metadata
    title_id                  TEXT,
    discovery_input           JSONB,

    -- Raw payload
    raw_payload               JSONB NOT NULL,

    CONSTRAINT uq_brightdata_linkedin_job_posting_id UNIQUE (job_posting_id)
);

CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_company_name
    ON raw.brightdata_linkedin_job_listings (company_name);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_company_id
    ON raw.brightdata_linkedin_job_listings (company_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_job_title
    ON raw.brightdata_linkedin_job_listings (job_title);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_ingestion_batch
    ON raw.brightdata_linkedin_job_listings (ingestion_batch_id);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_ingested_at
    ON raw.brightdata_linkedin_job_listings (ingested_at);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_job_posted_date
    ON raw.brightdata_linkedin_job_listings (job_posted_date);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_country_code
    ON raw.brightdata_linkedin_job_listings (country_code);
CREATE INDEX IF NOT EXISTS idx_brightdata_linkedin_seniority
    ON raw.brightdata_linkedin_job_listings (job_seniority_level);
```

### Table: `raw.brightdata_ingestion_batches`

Tracks each ingestion run for auditability.

```sql
CREATE TABLE IF NOT EXISTS raw.brightdata_ingestion_batches (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,
    record_count    INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata        JSONB
);

CREATE INDEX IF NOT EXISTS idx_brightdata_batches_source
    ON raw.brightdata_ingestion_batches (source);
CREATE INDEX IF NOT EXISTS idx_brightdata_batches_created_at
    ON raw.brightdata_ingestion_batches (created_at);
```

`source` values: `"indeed"`, `"linkedin"`.
`metadata` stores optional context: snapshot_id, filename, delivery method, etc.

Commit standalone.

---

## Deliverable 2: Modal Ingestion Function — Indeed

Create a Modal function that accepts a list of Indeed job listing records (JSON array) and upserts them into `raw.brightdata_indeed_job_listings`.

### Function signature:

```python
@app.function(...)
def ingest_brightdata_indeed_jobs(records: list[dict], metadata: dict | None = None) -> dict:
```

### Logic:

1. Generate a `batch_id` (UUID4).
2. Insert a row into `raw.brightdata_ingestion_batches` with `source="indeed"`, `record_count=len(records)`, and `metadata`.
3. For each record:
   - Extract all structured fields from the record (see Indeed field mapping below).
   - Set `raw_payload` to the entire record as JSONB.
   - Upsert on `jobid` conflict:
     - **On insert:** set `first_seen_at = now()`, `ingested_at = now()`.
     - **On conflict (jobid):** update `ingested_at = now()`, update ALL structured fields and `raw_payload` with new values, update `ingestion_batch_id`. Do NOT update `first_seen_at`.
4. Return `{"batch_id": str, "records_processed": int, "source": "indeed"}`.

### Indeed field mapping (record key → column):

| Record key | Column | Transform |
|---|---|---|
| `jobid` | `jobid` | text, required |
| `job_title` | `job_title` | text |
| `job_type` | `job_type` | text |
| `description_text` | `description_text` | text |
| `description` | `description` | text |
| `job_description_formatted` | `job_description_formatted` | text |
| `benefits` | `benefits` | store as JSONB (it's already an array) |
| `qualifications` | `qualifications` | text |
| `salary_formatted` | `salary_formatted` | text |
| `shift_schedule` | `shift_schedule` | store as JSONB (it's already an array) |
| `company_name` | `company_name` | text |
| `company_rating` | `company_rating` | float |
| `company_reviews_count` | `company_reviews_count` | int |
| `company_link` | `company_link` | text |
| `company_website` | `company_website` | text |
| `location` | `location` | text |
| `job_location` | `job_location` | text |
| `country` | `country` | text |
| `region` | `region` | text |
| `date_posted` | `date_posted` | text (store as-is, it's relative like "30+ days ago") |
| `date_posted_parsed` | `date_posted_parsed` | text |
| `url` | `url` | text |
| `apply_link` | `apply_link` | text |
| `domain` | `domain` | text |
| `logo_url` | `logo_url` | text |
| `is_expired` | `is_expired` | bool |
| `srcname` | `srcname` | text |
| `discovery_input` | `discovery_input` | store as JSONB |

Use batch upsert (not one-at-a-time). Use `psycopg2` or `asyncpg` or whatever DB driver the HQ repo already uses. Follow existing patterns in the repo.

Commit standalone.

---

## Deliverable 3: Modal Ingestion Function — LinkedIn

Same pattern as Indeed. Create a Modal function:

```python
@app.function(...)
def ingest_brightdata_linkedin_jobs(records: list[dict], metadata: dict | None = None) -> dict:
```

### Logic:

Same as Indeed: generate batch_id, insert batch record, upsert on `job_posting_id` conflict. Same `first_seen_at` / `ingested_at` semantics.

### LinkedIn field mapping (record key → column):

| Record key | Column | Transform |
|---|---|---|
| `job_posting_id` | `job_posting_id` | text, required |
| `job_title` | `job_title` | text |
| `job_summary` | `job_summary` | text |
| `job_seniority_level` | `job_seniority_level` | text |
| `job_function` | `job_function` | text |
| `job_employment_type` | `job_employment_type` | text |
| `job_industries` | `job_industries` | text |
| `job_base_pay_range` | `job_base_pay_range` | text |
| `job_description_formatted` | `job_description_formatted` | text |
| `is_easy_apply` | `is_easy_apply` | bool |
| `base_salary.currency` | `base_salary_currency` | text (extract from nested object) |
| `base_salary.min_amount` | `base_salary_min_amount` | float (extract from nested object) |
| `base_salary.max_amount` | `base_salary_max_amount` | float (extract from nested object) |
| `base_salary.payment_period` | `base_salary_payment_period` | text (extract from nested object) |
| `salary_standards` | `salary_standards` | text |
| `company_name` | `company_name` | text |
| `company_id` | `company_id` | text |
| `company_url` | `company_url` | text |
| `company_logo` | `company_logo` | text |
| `job_location` | `job_location` | text |
| `country_code` | `country_code` | text |
| `job_posted_date` | `job_posted_date` | parse as timestamptz (ISO 8601 input) |
| `job_posted_time` | `job_posted_time` | text (relative, store as-is) |
| `url` | `url` | text |
| `apply_link` | `apply_link` | text |
| `job_num_applicants` | `job_num_applicants` | int |
| `job_poster.name` | `job_poster_name` | text (extract from nested object) |
| `job_poster.title` | `job_poster_title` | text (extract from nested object) |
| `job_poster.url` | `job_poster_url` | text (extract from nested object) |
| `application_availability` | `application_availability` | bool |
| `title_id` | `title_id` | text |
| `discovery_input` | `discovery_input` | store as JSONB (it's already an object) |

Commit standalone.

---

## Deliverable 4: FastAPI Endpoints

Create two thin endpoints that wrap the Modal ingestion functions.

### `POST /api/ingest/brightdata/indeed`

Request body:
```json
{
  "records": [...],
  "metadata": {"snapshot_id": "snap_xxx", "source_file": "indeed_jobs_20260219.json"}
}
```

- `records` is required (list of Indeed job listing objects).
- `metadata` is optional (passed through to the batch record).
- Calls `ingest_brightdata_indeed_jobs(records, metadata)`.
- Returns the function result: `{"batch_id": "...", "records_processed": N, "source": "indeed"}`.

### `POST /api/ingest/brightdata/linkedin`

Same shape:
```json
{
  "records": [...],
  "metadata": {"snapshot_id": "snap_xxx"}
}
```

- Calls `ingest_brightdata_linkedin_jobs(records, metadata)`.
- Returns the function result.

### Auth:

Follow whatever auth pattern the HQ repo already uses for internal/admin endpoints. If unsure, use a simple API key check via environment variable (`INGEST_API_KEY`).

Commit standalone.

---

## Deliverable 5: Query Views (optional but recommended)

Create two convenience views for quick cross-source comparison:

### `raw.brightdata_indeed_active_jobs`

```sql
CREATE OR REPLACE VIEW raw.brightdata_indeed_active_jobs AS
SELECT *
FROM raw.brightdata_indeed_job_listings
WHERE is_expired IS NOT TRUE;
```

### `raw.brightdata_job_listings_summary`

```sql
CREATE OR REPLACE VIEW raw.brightdata_job_listings_summary AS
SELECT
    'indeed' AS source,
    COUNT(*) AS total_records,
    COUNT(*) FILTER (WHERE is_expired IS TRUE) AS expired_count,
    COUNT(*) FILTER (WHERE is_expired IS NOT TRUE) AS active_count,
    MIN(ingested_at) AS earliest_ingestion,
    MAX(ingested_at) AS latest_ingestion,
    COUNT(DISTINCT ingestion_batch_id) AS batch_count
FROM raw.brightdata_indeed_job_listings
UNION ALL
SELECT
    'linkedin' AS source,
    COUNT(*) AS total_records,
    NULL AS expired_count,
    NULL AS active_count,
    MIN(ingested_at) AS earliest_ingestion,
    MAX(ingested_at) AS latest_ingestion,
    COUNT(DISTINCT ingestion_batch_id) AS batch_count
FROM raw.brightdata_linkedin_job_listings;
```

Commit standalone.

---

## What is NOT in scope

- No Bright Data API integration (trigger, download, webhook). That is a separate directive.
- No cross-source matching or TheirStack comparison logic.
- No company domain resolution.
- No job posting entity model in data-engine-x.
- No deploy commands.
- No changes to data-engine-x-api repo.

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Table names and column counts for each table
(b) Ingestion function signatures
(c) Upsert conflict keys for each table
(d) FastAPI endpoint paths
(e) Index list for each table
(f) Any schema or pattern decisions you made that differed from existing HQ conventions
(g) Anything to flag
