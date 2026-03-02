Implemented the directive across SQL, FastAPI, Trigger task code, and tests (without pushing/deploying).
What I changed
Added migration supabase/migrations/013_job_posting_entities.sql
Extended job entity state logic in app/services/entity_state.py
Wired job upserts into app/routers/internal.py
Added job entity-type support in trigger/src/tasks/run-pipeline.ts
Added job-postings query endpoint in app/routers/entities_v1.py
Added tests in tests/test_job_posting_entity.py
Also updated app/services/entity_timeline.py and app/routers/execute_v1.py to avoid runtime rejection of job entity type (critical compatibility fix)
Requested report
(a) job_posting_entities column count + names
Count: 35
Columns: org_id, company_id, entity_id, theirstack_job_id, job_url, job_title, normalized_title, company_name, company_domain, location, short_location, state_code, country_code, remote, hybrid, seniority, employment_statuses, date_posted, discovered_at, salary_string, min_annual_salary_usd, max_annual_salary_usd, description, technology_slugs, hiring_team, posting_status, enrichment_confidence, last_enriched_at, last_operation_id, last_run_id, source_providers, record_version, canonical_payload, created_at, updated_at
(b) Index list
idx_job_posting_entities_org_theirstack_id
idx_job_posting_entities_org_company_domain
idx_job_posting_entities_org_company_name
idx_job_posting_entities_org_job_title
idx_job_posting_entities_org_posting_status
idx_job_posting_entities_org_country_code
idx_job_posting_entities_org_seniority
idx_job_posting_entities_org_company_id
idx_job_posting_entities_org_remote
(c) Entity ID resolution natural key priority chain
explicit entity_id (if valid UUID)
theirstack_job_id
job_url
(job_title + company_domain)
stable JSON fallback (_stable_identity_fallback("job", ...))
(d) check_entity_freshness identifier used for job
Uses theirstack_job_id (or job_id alias), then lookup via _lookup_job_posting_by_theirstack_id(org_id, theirstack_job_id).
(e) TypeScript changes in run-pipeline.ts (all locations)
blueprint_snapshot.entity.entity_type union now includes "job".
callExecuteV1 entityType union now includes "job".
callEntityStateFreshnessCheck entityType union now includes "job".
emitStepTimelineEvent payload entityType union now includes "job".
entityTypeFromOperationId return union now includes "job" and has job. branch.
Snapshot entity-type normalization now accepts "job".
(f) Entity query endpoint path + supported filters
Path: POST /api/v1/entities/job-postings
Filters: company_id, company_domain, company_name, job_title, seniority, country_code, remote, posting_status
Pagination: page, per_page
Ordering: created_at DESC
Supports tenant auth and super-admin auth (_resolve_flexible_auth), with org_id required for super-admin requests.
(g) Test count + names
Count: 8
test_resolve_job_posting_entity_id_by_theirstack_id
test_resolve_job_posting_entity_id_by_url
test_resolve_job_posting_entity_id_by_title_domain
test_resolve_job_posting_entity_id_deterministic
test_job_posting_fields_from_context_full
test_job_posting_fields_from_context_minimal
test_job_posting_fields_boolean_handling
test_entity_type_from_job_operation_id
(h) Flags / assumptions still limited to company|person not changed
app/routers/entities_v1.py timeline/snapshots validators still only allow "company"/"person" (existing behavior retained).
app/services/change_detection.py still restricts to "company"/"person".
app/routers/registry_v1.py request model defaults/limits entity type to company/person.
These were left untouched since not required by your directive’s scope.
Validation notes
Lint diagnostics on edited files: no issues.
Could not execute pytest in this environment (pytest not installed / no runnable test env detected), so tests are added but not executed here.
If you want, I can now split this into the six standalone commits exactly matching your commit-message convention.