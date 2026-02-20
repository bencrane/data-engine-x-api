# Directive: Bright Data Job Validation Endpoint (HQ Repo)

**Context:** You are working on the HQ repo (revenueinfra). FastAPI + Modal. Database is Supabase Postgres.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have Bright Data Indeed and LinkedIn job listings stored in `raw.brightdata_indeed_job_listings` and `raw.brightdata_linkedin_job_listings`. Each has a `resolved_company_domain` column. We need an API endpoint that data-engine-x can call to check whether a job posting is confirmed active by Bright Data sources.

---

## Existing tables to understand:

### `raw.brightdata_indeed_job_listings`
Key columns for matching:
- `resolved_company_domain TEXT` — derived company domain (may be NULL)
- `job_title TEXT`
- `company_name TEXT`
- `is_expired BOOLEAN` — direct signal from Indeed
- `ingested_at TIMESTAMPTZ` — when we last saw this record

### `raw.brightdata_linkedin_job_listings`
Key columns for matching:
- `resolved_company_domain TEXT` — derived company domain (may be NULL)
- `job_title TEXT`
- `company_name TEXT`
- `ingested_at TIMESTAMPTZ` — when we last saw this record
- (no `is_expired` equivalent)

---

## Deliverable 1: Modal Function — Validate Job Posting

Create a Modal function:

```python
@app.function(...)
def validate_job_posting_active(
    company_domain: str,
    job_title: str,
    company_name: str | None = None,
) -> dict:
```

### Logic:

1. Query `raw.brightdata_indeed_job_listings` for matches:
   - Primary match: `resolved_company_domain = company_domain` AND `job_title ILIKE '%' || job_title || '%'`
   - If no match on domain and `company_name` is provided: fallback to `company_name ILIKE '%' || company_name || '%'` AND `job_title ILIKE '%' || job_title || '%'`
   - From matches, return: count, whether any are `is_expired = true`, most recent `ingested_at`

2. Query `raw.brightdata_linkedin_job_listings` for matches:
   - Same matching logic: domain first, company_name fallback
   - From matches: count, most recent `ingested_at`

3. Return:

```json
{
  "company_domain": "stripe.com",
  "job_title": "Senior Data Engineer",
  "indeed": {
    "found": true,
    "match_count": 2,
    "any_expired": false,
    "most_recent_ingested_at": "2026-02-19T...",
    "matched_by": "domain"
  },
  "linkedin": {
    "found": true,
    "match_count": 1,
    "most_recent_ingested_at": "2026-02-19T...",
    "matched_by": "domain"
  },
  "validation_result": "active",
  "confidence": "high"
}
```

### Validation result logic:

- `"active"` — found in at least one source AND not expired in Indeed
- `"likely_closed"` — found in Indeed but `is_expired = true`, OR not found in any source
- `"expired"` — found in Indeed and ALL matches are `is_expired = true`
- `"unknown"` — no matches in any source (could mean we don't have coverage, not necessarily closed)

### Confidence logic:

- `"high"` — found by domain match in at least one source
- `"medium"` — found by company_name fallback only
- `"low"` — no matches found

Use the same DB connection pattern as the existing Bright Data ingestion functions (`psycopg2`, `supabase-credentials` secret).

Commit standalone.

---

## Deliverable 2: FastAPI Endpoint

**File:** Add to the existing `brightdata_ingest.py` router (or create `brightdata_validation.py` if you prefer separation — your call).

### `POST /api/ingest/brightdata/validate-job`

Request body:
```json
{
  "company_domain": "stripe.com",
  "job_title": "Senior Data Engineer",
  "company_name": "Stripe"
}
```

- `company_domain` is required
- `job_title` is required
- `company_name` is optional (fallback matching)

Calls the Modal function, returns the result directly.

Use the same `x-api-key` auth guard as the ingestion endpoints.

Commit standalone.

---

## What is NOT in scope

- No changes to Bright Data tables (columns already added)
- No domain resolution logic (that's a separate concern)
- No data-engine-x changes
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push.

## When done

Report back with:
(a) Modal function signature
(b) FastAPI endpoint path and request/response shapes
(c) Matching logic summary (domain-first, company_name fallback)
(d) Validation result categories
(e) Anything to flag
