This is already implemented and committed in two standalone commits on your current branch:
699a75c — Modal function (validate_job_posting_active)
da628cc — FastAPI wrapper endpoint (/api/ingest/brightdata/validate-job)
(a) Modal function signature
In modal-functions/src/ingest/brightdata_validate_job.py:
def validate_job_posting_active(company_domain: str, job_title: str, company_name: str | None = None) -> dict
(b) FastAPI endpoint path + request/response shapes
In hq-api/routers/brightdata_ingest.py:
POST /api/ingest/brightdata/validate-job
Uses the same x-api-key guard (_require_ingest_key) as the Bright Data ingest routes.
Request body:
company_domain: str (required)
job_title: str (required)
company_name: str | None (optional)
Response body: pass-through from Modal function, including:
top-level: company_domain, job_title, company_name, validation_result, confidence
nested indeed: found, match_count, any_expired, most_recent_ingested_at, matched_by
nested linkedin: found, match_count, most_recent_ingested_at, matched_by
(c) Matching logic summary
Domain-first with company-name fallback, independently per source:
First attempt: resolved_company_domain = company_domain and job_title ILIKE '%job_title%'
Fallback only if no domain matches and company_name provided:
company_name ILIKE '%company_name%' and job_title ILIKE '%job_title%'
(d) Validation result categories
Implemented categories:
active — at least one source found and Indeed not expired
expired — Indeed found and all Indeed matches expired
likely_closed — residual non-active/non-expired found state (e.g. mixed/expired Indeed signal)
unknown — no matches in either source
Confidence:
high — domain match in at least one source
medium — only fallback (company_name) matches
low — no matches
(e) Anything to flag
Your spec text has one contradiction:
likely_closed includes “not found in any source”
unknown also says “no matches in any source”
Current implementation resolves this by using unknown for no matches (safer, avoids false closure labeling). If you want, I can change this behavior explicitly to your preferred interpretation in a follow-up commit.