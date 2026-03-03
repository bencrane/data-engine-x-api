Implemented the directive and completed all 8 requested commits in order.
Commits Created
a3cac15 add unified input extraction module with canonical alias maps
6a52372 migrate hq_workflow_operations to unified input extraction
5f45c8b migrate blitzapi_person_operations to unified input extraction
84963d1 migrate company_operations to unified input extraction
80a9225 migrate resolve_operations to unified input extraction
72072c4 migrate salesnav_operations to unified input extraction
4037caa migrate blitzapi_company_search to unified input extraction
009e2bf migrate remaining service files to unified input extraction
(a) Canonical alias tuples
From app/services/_input_extraction.py:
COMPANY_NAME: company_name, current_company_name, canonical_name, name, companyName, matched_name
COMPANY_DOMAIN: domain, company_domain, canonical_domain, customer_domain, current_company_domain
COMPANY_WEBSITE: company_website, website, website_url, websiteUrl
COMPANY_LINKEDIN_URL: company_linkedin_url, linkedin_url, customer_linkedin_url, current_company_linkedin_url
COMPANY_LINKEDIN_ID: company_linkedin_id, org_id, orgId, linkedin_id
COMPANY_DESCRIPTION: description, description_raw, company_description, about
COMPANY_INDUSTRY: industry, industry_primary, current_company_industry
COMPANY_LOCATION: hq_locality, hq_country_code, current_company_location, geo_region
PERSON_LINKEDIN_URL: person_linkedin_url, linkedin_url, profile_url
PERSON_FULL_NAME: full_name, person_full_name, name
PERSON_EMAIL: work_email, email
PERSON_FIRST_NAME: first_name, person_first_name
PERSON_LAST_NAME: last_name, person_last_name
ICP_CRITERION: criterion, icp_criterion
ICP_TITLES: champion_titles, titles, icp_titles
CUSTOMERS: customers
SALES_NAV_URL: sales_nav_url, salesnav_url
PRICING_PAGE_URL: pricing_page_url
(b) Number of service files migrated
16 service files migrated to shared extraction.
Includes all explicitly committed deliverables plus the “remaining files” batch where applicable.
(c) Number of inline alias tuples replaced
40 inline alias-pattern extractions replaced (measured across migrated files by before/after pattern scan).
(d) Test results
Ran:
PYTHONPATH=. uv run --with pytest --with pytest-asyncio --with pyyaml pytest tests/ -x -q
Result:
1 failed, 48 passed
Failing test: tests/test_blueprint_assembler.py::test_company_research_blueprint_order
Failure expectation mismatch in operation order (expected company.enrich.profile first, got research ops first).
(e) Aliases found beyond your initial list (and added)
Added to canonical map from existing code usage patterns:
current_company_domain
current_company_linkedin_url
profile_url
company_website, website, website_url, websiteUrl
person_first_name, person_last_name
pricing_page_url
(f) Flags
hq_workflow_operations.py local _extract_* helpers were kept and explicitly marked deprecated as requested.
In the “remaining service files” list, shovels_operations.py and change_detection_operations.py had no meaningful company/domain/linkedin alias tuples to replace, so they were left unchanged.
Working tree still has non-task items not committed by me:
docs/EXECUTOR_DIRECTIVE_UNIFIED_INPUT_EXTRACTION.md (untracked)
docs/api-reference-docs (existing state marker)