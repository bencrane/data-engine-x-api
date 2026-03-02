Implemented all 5 deliverables in-scope, with 5 standalone commits (no push, no deploy, no migration changes).
Commits
241a8cf — add revenueinfra provider adapter for fetching ICP candidate companies
6074d72 — add contract for company.fetch.icp_candidates operation
67f8871 — add company.fetch.icp_candidates operation service
6bbf07d — wire company.fetch.icp_candidates into execute router
4a537c4 — add tests for company.fetch.icp_candidates operation
Requested confirmations
(a) Provider adapter signature + endpoint
Signature in app/providers/revenueinfra/fetch_icp_companies.py:
async def fetch_icp_companies(*, base_url: str, limit: int | None = None) -> ProviderAdapterResult
Calls:
POST {base_url}/api/admin/temp/companies-for-parallel-icp
Body:
{"limit": limit} when provided, otherwise {}.
Timeout:
30.0 seconds.
No auth header.
(b) Contract field counts
IcpCompanyItem (in app/contracts/icp_companies.py): 3 fields
company_name, domain, company_description
FetchIcpCompaniesOutput: 3 fields
company_count, results, source_provider
(c) results key for fan-out
Confirmed. Provider mapped output uses top-level key results (list of dicts), which is what fan-out extraction expects.
(d) Field mapping
Confirmed mapping is implemented:
HQ description → canonical company_description
(e) Router wiring
app/routers/execute_v1.py updated to:
include "company.fetch.icp_candidates" in SUPPORTED_OPERATION_IDS
import execute_company_fetch_icp_candidates
dispatch and persist via persist_operation_execution(...) exactly in existing pattern
(f) Test count + names
Added tests/test_fetch_icp_companies.py with 5 tests:
test_fetch_icp_companies_success
test_fetch_icp_companies_empty
test_fetch_icp_companies_with_limit
test_fetch_icp_companies_http_error
test_fetch_icp_companies_maps_description_to_company_description
(g) Anything to flag
ReadLints reports no linter errors in changed files.
Could not execute tests in this shell environment because pytest is not installed (python3 -m pytest fails with No module named pytest).
Existing unrelated dirty/untracked workspace changes were left untouched.