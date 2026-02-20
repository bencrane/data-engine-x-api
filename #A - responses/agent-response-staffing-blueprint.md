Implemented the full directive in 6 standalone commits (not pushed), matching the requested commit messages:
0911470 add revenueinfra provider adapter for job posting validation
4bf7bed add job validation contract
cbbaa96 add job.validate.is_active operation service
589617c wire job.validate.is_active into config and execute router
2ca4641 add tests for job.validate.is_active operation
d5ea608 add staffing enrichment blueprint definition and job.validate.is_active operation
(a) Provider adapter signature + endpoint
Function:
validate_job_active(*, base_url: str, api_key: str | None, company_domain: str, job_title: str, company_name: str | None = None) -> ProviderAdapterResult
Endpoint called:
POST {base_url}/api/ingest/brightdata/validate-job
File:
app/providers/revenueinfra/validate_job.py
Export wired in:
app/providers/revenueinfra/__init__.py
(b) Contract field count
JobValidationOutput has 10 fields total in app/contracts/job_validation.py.
(c) Operation service input extraction logic
In execute_job_validate_is_active (app/services/research_operations.py):
company_domain from:
input_data.company_domain
else cumulative_context.company_domain
else cumulative_context.company_object.domain
job_title from:
input_data.job_title
else cumulative_context.job_title
company_name from:
input_data.company_name
else cumulative_context.company_name
else cumulative_context.company_object.name
Missing company_domain or job_title returns status: "failed" with missing_inputs.
(d) Config env var name for HQ API key
Added settings field:
revenueinfra_ingest_api_key: str | None = None
Env var:
REVENUEINFRA_INGEST_API_KEY
File:
app/config.py
(e) Router wiring confirmation
In app/routers/execute_v1.py:
Added to SUPPORTED_OPERATION_IDS:
"job.validate.is_active"
Imported:
execute_job_validate_is_active
Added dispatch branch that executes, persists via persist_operation_execution, and returns DataEnvelope.
(f) Test count and names
Added tests/test_job_validate.py with 9 tests:
test_validate_job_active_missing_domain
test_validate_job_active_missing_title
test_validate_job_active_success_active
test_validate_job_active_success_expired
test_validate_job_active_success_unknown
test_validate_job_active_api_error
test_validate_job_active_timeout
test_validate_job_active_reads_from_cumulative_context
test_validate_job_active_reads_from_company_object
(g) Blueprint step count and fan-out positions
Added docs/blueprints/staffing_enrichment_v1.json
Step count: 7
fan_out: true positions: 1 (job.search) and 4 (person.search)
(h) Anything to flag
Lint check on edited files: no linter errors.
Could not run tests in this shell because pytest is unavailable (No module named pytest in current runtime).
Working tree still contains unrelated pre-existing changes/untracked files outside this directive; none were modified by these commits.