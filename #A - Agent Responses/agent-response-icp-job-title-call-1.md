Implemented end-to-end from docs/EXECUTOR_DIRECTIVE_EXTRACT_ICP_TITLES.md with the 8 deliverables committed, plus one production-safety fix commit.
(a) Migration details
File: supabase/migrations/017_icp_title_extraction.sql
New table: extracted_icp_job_title_details
New column on existing table: icp_job_titles.extracted_titles (JSONB)
(b) Provider adapter signature + endpoint
Function:
async def extract_icp_titles(*, company_domain: str, raw_parallel_output: dict[str, Any] | str, raw_parallel_icp_id: str | None = None) -> ProviderAdapterResult
Endpoint called:
POST https://bencrane--hq-master-data-ingest-extract-icp-titles.modal.run
Implemented in app/providers/modal_extract_icp.py with:
required-input skip handling (missing_required_inputs)
60s timeout
HTTP/network failure mapping to failed
success: false mapping to failed
mapped success payload per directive
(c) Contract field counts
IcpTitleItem: 3 fields (title, buyer_role, reasoning)
ExtractIcpTitlesOutput: 6 fields (company_domain, company_name, titles, title_count, usage, source_provider)
File: app/contracts/icp_extraction.py
(d) Persistence function signatures
def update_icp_extracted_titles(*, org_id: str, company_domain: str, extracted_titles: list[dict[str, Any]]) -> dict[str, Any] | None
def upsert_icp_title_details_batch(*, org_id: str, company_domain: str, company_name: str | None, titles: list[dict[str, Any]], source_icp_job_titles_id: str | None = None) -> list[dict[str, Any]]
Added in app/services/icp_job_titles.py
(e) Operation service input extraction logic
app/services/icp_extraction_operations.py checks:
company_domain from:
input_data["company_domain"]
input_data["cumulative_context"]["company_domain"]
raw_parallel_output from:
input_data["raw_parallel_output"]
input_data["cumulative_context"]["parallel_raw_response"]["output"]["content"]
input_data["cumulative_context"]["raw_parallel_output"]
raw_parallel_icp_id from:
input_data["raw_parallel_icp_id"]
input_data["cumulative_context"]["raw_parallel_icp_id"]
input_data["cumulative_context"]["icp_job_titles_id"]
Fallback DB lookup when needed:
query_icp_job_titles(org_id, company_domain, limit=1) to recover missing raw_parallel_output / ICP row id
Then it:
Calls provider
Validates via ExtractIcpTitlesOutput
Writes icp_job_titles.extracted_titles
Upserts batch rows to extracted_icp_job_title_details
Returns standard operation result (status: "found" on success)
(f) Router wiring confirmation
app/routers/execute_v1.py now has:
SUPPORTED_OPERATION_IDS includes company.derive.extract_icp_titles
import for execute_company_derive_extract_icp_titles
dispatch branch with persist_operation_execution(...) and DataEnvelope(data=result)
(g) Query endpoint path + supported filters
Path: POST /api/v1/icp-title-details/query
Request model: IcpTitleDetailsQueryRequest
Filters: company_domain, buyer_role, limit, offset, org_id (super-admin context)
Auth/scoping: flexible auth, tenant-scoped by org; super-admin requires org_id in body
Added to app/routers/entities_v1.py + backing service function query_icp_title_details(...)
(h) Anything to flag
Added an extra hardening commit: 56b3a98
reason: Trigger passes cumulative context as execute input; without injecting org_id in execute router, this new operation would fail persistence paths.
No deploy commands run.
Lints checked on edited Python files: no linter errors found.
Existing unrelated dirty/untracked workspace content remains untouched (including docs/api-reference-docs submodule delta and many untracked files).
Commits created
a8636c5 add 017 migration for icp title extraction — extracted_titles column + flat details table
3a549ae add Modal provider adapter for ICP title extraction via Anthropic
3451d14 add contract for ICP title extraction output
2fdaa2d add persistence functions for extracted ICP titles
be529b7 add company.derive.extract_icp_titles operation service
4627026 wire company.derive.extract_icp_titles into execute router
a3f7740 add query endpoint for extracted ICP title details
d8a6a2c update documentation for ICP title extraction operation
56b3a98 fix extract ICP titles execute path to pass org_id for persistence