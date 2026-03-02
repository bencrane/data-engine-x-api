Implemented all 6 deliverables in scope with 6 standalone commits (not pushed).
git log -6 --oneline:
c967e03 update system overview with 6 CRM resolve operations (57 total)
e92eb73 add tests for 6 CRM resolve operations
b161b90 wire 6 CRM resolve operations into execute router
382df22 add 6 CRM resolve operation services
7ddbb18 add resolution contracts for CRM cleanup operations
944e2ba add 6 HQ resolution provider adapters for CRM cleanup operations
(a) Operation IDs
company.resolve.domain_from_email
company.resolve.domain_from_linkedin
company.resolve.domain_from_name
company.resolve.linkedin_from_domain
person.resolve.linkedin_from_email
company.resolve.location_from_domain
(b) Provider adapter function signatures (all 6)
async def resolve_domain_from_email(*, base_url: str, api_key: str | None, work_email: str | None) -> ProviderAdapterResult
async def resolve_domain_from_linkedin(*, base_url: str, api_key: str | None, company_linkedin_url: str | None) -> ProviderAdapterResult
async def resolve_domain_from_company_name(*, base_url: str, api_key: str | None, company_name: str | None) -> ProviderAdapterResult
async def resolve_linkedin_from_domain(*, base_url: str, api_key: str | None, domain: str | None) -> ProviderAdapterResult
async def resolve_person_linkedin_from_email(*, base_url: str, api_key: str | None, work_email: str | None) -> ProviderAdapterResult
async def resolve_company_location_from_domain(*, base_url: str, api_key: str | None, domain: str | None) -> ProviderAdapterResult
(c) HQ endpoint paths called
resolve_domain_from_email → /api/workflows/resolve-domain-from-email/single
resolve_domain_from_linkedin → /api/workflows/resolve-domain-from-linkedin/single
resolve_domain_from_company_name → /api/workflows/resolve-company-name/single
resolve_linkedin_from_domain → /api/workflows/resolve-linkedin-from-domain/single
resolve_person_linkedin_from_email → /api/workflows/resolve-person-linkedin-from-email/single
resolve_company_location_from_domain → /api/workflows/resolve-company-location-from-domain/single
(d) Contract model names + field counts
ResolveDomainOutput — 4 fields (domain, cleaned_company_name, resolve_source, source_provider)
ResolveLinkedInOutput — 3 fields (company_linkedin_url, resolve_source, source_provider)
ResolvePersonLinkedInOutput — 3 fields (person_linkedin_url, resolve_source, source_provider)
ResolveLocationOutput — 5 fields (company_city, company_state, company_country, resolve_source, source_provider)
(e) Input extraction aliases per operation
All operations check:
1) direct input_data
2) input_data["cumulative_context"]
Alias sets used:
Email ops (company.resolve.domain_from_email, person.resolve.linkedin_from_email): work_email, email
Domain ops (company.resolve.linkedin_from_domain, company.resolve.location_from_domain): domain, company_domain, canonical_domain
LinkedIn-domain op (company.resolve.domain_from_linkedin): company_linkedin_url, linkedin_url
Company name op (company.resolve.domain_from_name): company_name
(f) Router wiring confirmation
In app/routers/execute_v1.py:
Added all 6 IDs to SUPPORTED_OPERATION_IDS
Imported all 6 service execute functions from app.services.resolve_operations
Added 6 dispatch branches, each with persist_operation_execution(...) + DataEnvelope(data=result)
(g) Test count and names
Added tests/test_resolve_operations.py with 20 tests:
test_resolve_domain_from_email_missing_input
test_resolve_domain_from_email_success
test_resolve_domain_from_email_not_found
test_resolve_domain_from_linkedin_missing_input
test_resolve_domain_from_linkedin_success
test_resolve_domain_from_linkedin_not_found
test_resolve_domain_from_name_missing_input
test_resolve_domain_from_name_success
test_resolve_domain_from_name_not_found
test_resolve_linkedin_from_domain_missing_input
test_resolve_linkedin_from_domain_success
test_resolve_linkedin_from_domain_not_found
test_resolve_person_linkedin_from_email_missing_input
test_resolve_person_linkedin_from_email_success
test_resolve_person_linkedin_from_email_not_found
test_resolve_location_from_domain_missing_input
test_resolve_location_from_domain_success
test_resolve_location_from_domain_not_found
test_resolve_domain_from_email_reads_cumulative_context
test_resolve_linkedin_from_domain_reads_cumulative_context
Validation run:
PYTHONPATH=. uv run --with pytest --with pytest-asyncio pytest tests/test_resolve_operations.py
Result: 20 passed
(h) Anything to flag
Kept scope tight: no deploy commands, no blueprint changes, no fallback logic added.
status propagation in resolve services is based on provider attempt status (found / not_found / failed / skipped), matching your pattern and enabling explicit not_found.
Existing unrelated working-tree changes were left untouched.