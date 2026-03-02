Implemented exactly per directive and committed in 6 standalone commits.
3ca8600 add BlitzAPI dedicated company enrichment provider adapter
525adbb add BlitzAPI company enrichment output contract
02225a2 add company.enrich.profile_blitzapi operation service
39ba2a8 wire company.enrich.profile_blitzapi into execute router
5e2d14c add tests for company.enrich.profile_blitzapi operation
1dce18a update documentation for company.enrich.profile_blitzapi operation
(a) Provider adapter signature + endpoint
Function added in app/providers/blitzapi.py:
async def enrich_company_profile(*, api_key: str | None, company_linkedin_url: str | None) -> ProviderAdapterResult:
Calls exact endpoint:
POST https://api.blitz-api.ai/v2/enrichment/company
Uses:
x-api-key header
JSON body {"company_linkedin_url": ...}
_blitzapi_request_with_retry(...)
httpx.AsyncClient(timeout=30.0)
Attempt action is exactly:
"action": "enrich_company_profile"
(b) company_linkedin_id top-level output confirmation
Confirmed: in execute_company_enrich_profile_blitzapi, output is flat canonical fields at top level.
company_linkedin_id is top-level in output (stringified from BlitzAPI numeric linkedin_id).
Verified in test: test_enrich_company_success asserts output["company_linkedin_id"] == "108037802".
(c) Contract field list
Added BlitzAPICompanyEnrichOutput in app/contracts/company_enrich.py with:
company_name
company_domain
company_website
company_linkedin_url
company_linkedin_id
company_type
industry_primary
employee_count
employee_range
founded_year
hq_locality
hq_country_code
description_raw
specialties
follower_count
source_provider (default "blitzapi")
(d) Input extraction + domain bridge behavior
In execute_company_enrich_profile_blitzapi (app/services/company_operations.py):
company_linkedin_url checks in order:
input_data["company_linkedin_url"]
input_data["linkedin_url"]
input_data["cumulative_context"]["company_linkedin_url"]
input_data["cumulative_context"]["linkedin_url"]
Domain fallback checks:
input_data["company_domain"]
input_data["domain"]
cumulative_context["company_domain"]
cumulative_context["domain"]
Bridge behavior:
If no LinkedIn URL but domain exists, calls blitzapi.resolve_linkedin_from_domain(...) first and appends that attempt.
Then calls blitzapi.enrich_company_profile(...) with resolved LinkedIn URL.
(e) Router wiring confirmation
In app/routers/execute_v1.py:
Added to SUPPORTED_OPERATION_IDS:
company.enrich.profile_blitzapi
Imported:
execute_company_enrich_profile_blitzapi
Added dispatch branch adjacent to company.enrich.profile path, with persist_operation_execution(...) and DataEnvelope(data=result).
(f) Test count + names
Added tests/test_blitzapi_company_enrichment.py with 7 tests:
test_enrich_company_missing_api_key
test_enrich_company_missing_linkedin_url
test_enrich_company_success
test_enrich_company_not_found
test_enrich_company_http_error
test_enrich_company_domain_bridge
test_enrich_company_reads_from_cumulative_context
Executed:
PYTHONPATH=. uv run --with pytest --with pytest-asyncio pytest tests/test_blitzapi_company_enrichment.py tests/test_blitzapi_domain_to_linkedin.py
Result: 13 passed (new 7 + existing 6).
(g) Flags
CLAUDE.md has no explicit operation-count references to update; no change made there.
There is a pre-existing unrelated modified path in the worktree: docs/api-reference-docs (left untouched).