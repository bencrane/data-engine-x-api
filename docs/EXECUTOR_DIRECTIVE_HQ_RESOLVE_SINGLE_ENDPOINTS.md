# Directive: Single-Record Resolution Endpoints (HQ Repo)

**Context:** You are working on the HQ repo (revenueinfra). FastAPI + Modal. Database is Supabase Postgres.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** The HQ API has batch workflow endpoints (e.g., `/api/workflows/resolve-company-name`) that operate on `record_ids` from `hq.clients_normalized_crm_data`. We need single-record variants of these endpoints that accept one record's fields and return the resolved value. These will be called by data-engine-x pipeline steps, which process one entity at a time with cumulative context chaining.

---

## Existing Code to Read

- `hq-api/routers/workflows.py` — existing batch workflow endpoint implementations. Each new single-record endpoint reuses the same DB lookup logic.
- `hq-api/routers/brightdata_ingest.py` — reference pattern for `x-api-key` auth guard (`_require_ingest_key`). Use the same auth pattern.
- The existing batch endpoints' descriptions in the OpenAPI spec (copied below for each) explain the lookup logic.

---

## Deliverable 1: `POST /api/workflows/resolve-domain-from-email/single`

**Input:**
```json
{"work_email": "jane@stripe.com"}
```

**Logic:**
1. If `work_email` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Try to match `work_email` against `reference.email_to_person` to get domain (same logic as batch endpoint)
3. If no match, extract domain from email: `work_email.split("@")[1]`
4. Filter out generic email providers (gmail.com, yahoo.com, hotmail.com, outlook.com, aol.com, icloud.com, protonmail.com, mail.com). If domain is generic → return `{"resolved": false, "reason": "generic_email_provider", "raw_domain": domain}`

**Output (success):**
```json
{
  "resolved": true,
  "domain": "stripe.com",
  "source": "email_extract"
}
```

If matched via `reference.email_to_person`, set `"source": "reference.email_to_person"`.

---

## Deliverable 2: `POST /api/workflows/resolve-domain-from-linkedin/single`

**Input:**
```json
{"company_linkedin_url": "https://www.linkedin.com/company/stripe"}
```

**Logic:**
1. If `company_linkedin_url` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Normalize the LinkedIn URL (extract the slug, handle variations like `linkedin.com/company/stripe/`, `www.linkedin.com/company/stripe`, etc.)
3. Match against `core.companies.linkedin_url` (same logic as batch endpoint)
4. If match → return domain from `core.companies.domain`

**Output (success):**
```json
{
  "resolved": true,
  "domain": "stripe.com",
  "source": "core.companies"
}
```

**Output (not found):**
```json
{
  "resolved": false,
  "reason": "not_found_in_core_companies"
}
```

---

## Deliverable 3: `POST /api/workflows/resolve-company-name/single`

**Input:**
```json
{"company_name": "Stripe Inc"}
```

**Logic:**
1. If `company_name` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Look up in `extracted.cleaned_company_names` for a match
3. If found → return domain and cleaned name
4. If not found → return `resolved: false`. No external API calls. No fallback. Pure DB lookup only.

**Output (success):**
```json
{
  "resolved": true,
  "domain": "stripe.com",
  "cleaned_company_name": "Stripe",
  "source": "extracted.cleaned_company_names"
}
```

**Output (not found):**
```json
{
  "resolved": false,
  "reason": "not_found_in_cleaned_company_names"
}
```

---

## Deliverable 4: `POST /api/workflows/resolve-linkedin-from-domain/single`

**Input:**
```json
{"domain": "stripe.com"}
```

**Logic:**
1. If `domain` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Normalize domain (strip protocol, www, trailing slash)
3. Match against `core.companies.domain`
4. If match → return `company_linkedin_url` from `core.companies.linkedin_url`

**Output (success):**
```json
{
  "resolved": true,
  "company_linkedin_url": "https://www.linkedin.com/company/stripe",
  "source": "core.companies"
}
```

**Output (not found):**
```json
{
  "resolved": false,
  "reason": "not_found_in_core_companies"
}
```

---

## Deliverable 5: `POST /api/workflows/resolve-person-linkedin-from-email/single`

**Input:**
```json
{"work_email": "jane@stripe.com"}
```

**Logic:**
1. If `work_email` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Match `work_email` against `reference.email_to_person.email`
3. If match → return `person_linkedin_url` from `reference.email_to_person.person_linkedin_url`

**Output (success):**
```json
{
  "resolved": true,
  "person_linkedin_url": "https://www.linkedin.com/in/jane-doe",
  "source": "reference.email_to_person"
}
```

**Output (not found):**
```json
{
  "resolved": false,
  "reason": "not_found_in_reference"
}
```

---

## Deliverable 6: `POST /api/workflows/resolve-company-location-from-domain/single`

**Input:**
```json
{"domain": "stripe.com"}
```

**Logic:**
1. If `domain` is missing or empty → return `{"resolved": false, "reason": "missing_input"}`
2. Normalize domain
3. Match against `core.company_locations.domain`
4. If match → return city, state, country

**Output (success):**
```json
{
  "resolved": true,
  "company_city": "San Francisco",
  "company_state": "CA",
  "company_country": "US",
  "source": "core.company_locations"
}
```

**Output (not found):**
```json
{
  "resolved": false,
  "reason": "not_found_in_core_company_locations"
}
```

---

## Implementation Notes

- **All 6 endpoints** go in a new router file: `hq-api/routers/workflows_single.py`. Do NOT modify the existing `hq-api/routers/workflows.py`.
- **Auth:** Use the same `x-api-key` guard pattern from `brightdata_ingest.py` (`_require_ingest_key` with `INGEST_API_KEY` env var). All endpoints require the `x-api-key` header.
- **Router prefix:** `/api/workflows` (same as existing, the `/single` suffix on each path distinguishes them).
- **Register the router** in `hq-api/main.py`.
- **DB access:** Use the same connection pattern as existing workflow endpoints (psycopg2, Supabase client, or whatever the batch endpoints use). Follow existing patterns exactly.
- **Every endpoint returns `resolved: true/false`** as the top-level signal. Callers check this field to decide whether to proceed.
- **Normalize all inputs:** strip whitespace, lowercase emails, normalize URLs. Defensive parsing — never crash on bad input.

---

## What is NOT in scope

- No changes to existing batch workflow endpoints
- No changes to data-engine-x
- No new database tables or migrations
- No deploy commands

## Commit convention

One commit per deliverable (6 endpoints + 1 router registration = 7 commits). Do not push.

## When done

Report back with:
(a) All 6 endpoint paths and HTTP methods
(b) Router file location
(c) Auth pattern used
(d) DB tables queried per endpoint
(e) Generic email provider filter list (for resolve-domain-from-email)
(f) Any existing helper functions you reused from the batch endpoints
(g) Anything to flag — especially if any DB table referenced doesn't exist or has a different schema than expected
