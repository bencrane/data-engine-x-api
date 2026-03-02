pplied. resolve-company-name/single is now pure DB lookup only (no Parallel call, no external API calls, no writeback on miss).
Implemented all scoped endpoints in hq-api/routers/workflows_single.py and registered router in hq-api/main.py.
Endpoints Added
POST /api/workflows/resolve-domain-from-email/single
POST /api/workflows/resolve-domain-from-linkedin/single
POST /api/workflows/resolve-company-name/single (DB-only per your update)
POST /api/workflows/resolve-linkedin-from-domain/single
POST /api/workflows/resolve-person-linkedin-from-email/single
POST /api/workflows/resolve-company-location-from-domain/single
Requested Report
(a) Methods/paths: all six are POST, listed above.
(b) Router file: hq-api/routers/workflows_single.py
(c) Auth pattern used: same x-api-key guard pattern as brightdata_ingest:
_require_ingest_key(x_api_key)
compares against INGEST_API_KEY env var
header parsed with Header(..., alias="x-api-key")
(d) DB tables queried per endpoint:
resolve-domain-from-email/single → reference.email_to_person
resolve-domain-from-linkedin/single → core.companies
resolve-company-name/single → extracted.cleaned_company_names
resolve-linkedin-from-domain/single → core.companies
resolve-person-linkedin-from-email/single → reference.email_to_person
resolve-company-location-from-domain/single → core.company_locations
(e) Generic provider filter list: gmail.com, yahoo.com, hotmail.com, outlook.com, aol.com, icloud.com, protonmail.com, mail.com
(f) Reused helper functions from batch router (workflows.py):
normalize_email
normalize_domain
normalize_linkedin_company_url
extract_domain_from_email
(g) Flags / schema risk:
core.company_locations migration history shows matched_city/matched_state/matched_country in older DDL, while batch workflow code (and this new single endpoint, by design) query city/state/country.
If current DB actually lacks city/state/country, both batch and single location resolvers will fail at runtime. This should be verified against live schema.
Commits Made (no push)
ed14f8d deliverable 1
c6e1b0a deliverable 2
07307d7 deliverable 3 (initial)
5f0fdb2 deliverable 3 update: removed Parallel fallback (your instruction)
fbda84c deliverable 4
5b04ff3 deliverable 5
0579a9a deliverable 6
73a5b0e router registration in main.py
If you want, I can add explicit response models (pydantic) for each endpoint so the OpenAPI docs are strongly typed and callers get strict contract visibility.