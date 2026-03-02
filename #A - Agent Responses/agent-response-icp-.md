Implemented end-to-end in 6 standalone commits (not pushed), exactly scoped:
8465f81 add 015_icp_job_titles migration for raw Parallel ICP output per company
5aa64f9 add icp_job_titles service with upsert and query functions
5bbd235 add internal endpoint for upserting ICP job titles
8b00e3f add ICP job titles query endpoint
dcebee5 add backfill script to extract ICP job titles from step results into dedicated table
d5646f6 update documentation for ICP job titles table and endpoints
(a) Migration file path and table name
Path: supabase/migrations/015_icp_job_titles.sql
Table: icp_job_titles
(b) Service function signatures
From app/services/icp_job_titles.py:
def upsert_icp_job_titles(    *,    org_id: str,    company_domain: str,    company_name: str | None = None,    company_description: str | None = None,    raw_parallel_output: dict[str, Any],    parallel_run_id: str | None = None,    processor: str | None = None,    source_submission_id: str | None = None,    source_pipeline_run_id: str | None = None,) -> dict[str, Any]
def query_icp_job_titles(    *,    org_id: str,    company_domain: str | None = None,    limit: int = 100,    offset: int = 0,) -> list[dict[str, Any]]
(c) Internal endpoint path and request body fields
Path: POST /api/internal/icp-job-titles/upsert
Auth: Depends(require_internal_key) + x-internal-org-id extracted for org_id
Request fields:
company_domain
company_name
company_description
raw_parallel_output
parallel_run_id
processor
source_submission_id
source_pipeline_run_id
(d) Query endpoint path and supported filters
Path: POST /api/v1/icp-job-titles/query
Auth: flexible (_resolve_flexible_auth)
tenant auth scoped to auth.org_id
super-admin must provide org_id in body
Supported filters/paging:
company_domain (normalized before filtering)
limit
offset
org_id (super-admin only)
(e) Dedup constraint fields
Unique dedup index on:
org_id
company_domain
(f) Backfill script details
Script: scripts/backfill_icp_job_titles.py
Run:
doppler run -- python scripts/backfill_icp_job_titles.py
Targets submission:
0921f10b-890b-47ab-8ceb-b1986df51cbb
Uses org_id:
b0293785-aa7a-4234-8201-cc47305295f8
(g) Backfill extraction path (exact keys)
From each succeeded step_results.output_payload:
output_payload.operation_result.output.domain
output_payload.operation_result.output.company_name
output_payload.operation_result.output.company_description
output_payload.operation_result.output.parallel_raw_response.output.content
output_payload.operation_result.output.parallel_run_id
output_payload.operation_result.output.processor
(h) Anything to flag
I left unrelated pre-existing working tree changes untouched (including trigger/*, docs/api-reference-docs, and many untracked files), as required.
Backfill script is ready but not executed (per scope).
Lint check on edited files returned clean.