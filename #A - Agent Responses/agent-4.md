Implemented end-to-end per directive, with one commit per deliverable and no pushes.
Commits:
5be25bf — add BlitzAPI domain-to-linkedin provider adapter
a6a0020 — add company.resolve.linkedin_from_domain_blitzapi operation service
fa6352c — wire company.resolve.linkedin_from_domain_blitzapi into execute router
204ea24 — add tests for BlitzAPI domain-to-linkedin resolve operation
4cc1ae4 — update documentation for company.resolve.linkedin_from_domain_blitzapi operation
(a) Provider adapter signature + endpoint
Signature:
resolve_linkedin_from_domain(*, api_key: str | None, domain: str | None) -> ProviderAdapterResult
Endpoint called:
POST https://api.blitz-api.ai/v2/enrichment/domain-to-linkedin
Added in app/providers/blitzapi.py with timeout=15.0.
(b) Service input extraction (domain aliases)
Service uses existing _extract_domain(...) in app/services/resolve_operations.py, which checks:
direct input: domain, company_domain, canonical_domain
then cumulative_context: domain, company_domain, canonical_domain
(c) Contract used for output validation
ResolveLinkedInOutput from app/contracts/resolve.py.
(d) Top-level company_linkedin_url confirmation
Confirmed. Service returns:
output["company_linkedin_url"] at top level
This is produced via validated ResolveLinkedInOutput and supports entity state persistence mapping.
(e) Router wiring confirmation
Added to SUPPORTED_OPERATION_IDS:
company.resolve.linkedin_from_domain_blitzapi
Imported handler:
execute_company_resolve_linkedin_from_domain_blitzapi
Added dispatch branch in app/routers/execute_v1.py with persist_operation_execution(...) and DataEnvelope(data=result).
(f) Test count + names
Added 6 tests in tests/test_blitzapi_domain_to_linkedin.py:
test_resolve_linkedin_missing_api_key
test_resolve_linkedin_missing_domain
test_resolve_linkedin_success
test_resolve_linkedin_not_found
test_resolve_linkedin_http_error
test_resolve_linkedin_reads_from_cumulative_context
(g) Anything to flag
pytest is not available in this shell environment (python3 -m pytest -> No module named pytest), so I could not execute the new tests locally.
Existing unrelated workspace changes were left untouched.