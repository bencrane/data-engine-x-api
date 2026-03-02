Implemented all 6 deliverables from docs/EXECUTOR_DIRECTIVE_THEIRSTACK_ENRICHMENT.md and committed them as standalone commits in the required order:
7980aad enrich TheirStack provider adapter with full job posting field mapping
a2c661f add enriched TheirStack job posting contracts with hiring team and embedded company
d17cd86 expand company.search.by_job_postings filter surface for staffing use case
3e4d738 add job.search operation with full TheirStack filter passthrough
580d529 wire job.search operation into execute router
6f6f703 add tests for enriched TheirStack job search adapter and job.search operation
python3 -m pytest ... could not run in this shell because pytest is not installed in the active interpreter (No module named pytest).
Requested report
(a) _map_job_item mapped field list (38 total)
job_id, theirstack_job_id, job_title, normalized_title, company_name, company_domain, url, final_url, source_url, date_posted, discovered_at, reposted, date_reposted, location, short_location, long_location, state_code, postal_code, latitude, longitude, country, country_code, cities, remote, hybrid, seniority, employment_statuses, easy_apply, salary_string, min_annual_salary_usd, max_annual_salary_usd, avg_annual_salary_usd, salary_currency, description, technology_slugs, hiring_team, company_object, manager_roles.
Backward compatibility preserved with job_id aliasing the same value as theirstack_job_id.
(b) TheirStackJobItem field count
Old: 9
New: 39
(c) Full filters exposed in job.search
job_title_or, job_title_not, job_title_pattern_and, job_title_pattern_or, job_title_pattern_not
job_country_code_or, job_country_code_not, job_location_pattern_or, job_location_pattern_not
posted_at_max_age_days, posted_at_gte, posted_at_lte, discovered_at_max_age_days, discovered_at_gte, discovered_at_lte
remote, job_seniority_or, min_salary_usd, max_salary_usd, easy_apply, employment_statuses_or
job_description_pattern_or, job_description_pattern_not, job_description_contains_or, job_description_contains_not
job_technology_slug_or, job_technology_slug_not, job_technology_slug_and
url_domain_or, url_domain_not
company_domain_or, company_domain_not, company_name_or, company_name_not, company_name_case_insensitive_or, company_name_partial_match_or, company_linkedin_url_or, company_list_id_or, company_list_id_not
company_description_pattern_or, company_description_pattern_not
min_revenue_usd, max_revenue_usd, min_employee_count, max_employee_count, min_funding_usd, max_funding_usd, funding_stage_or, last_funding_round_date_lte, last_funding_round_date_gte
industry_id_or, industry_id_not, company_country_code_or, company_country_code_not
company_technology_slug_or, company_technology_slug_and, company_technology_slug_not, company_investors_or, company_investors_partial_match_or, company_tags_or, only_yc_companies
company_type, blur_company_data
Pagination/control params from step_config: limit, offset, page, cursor, include_total_results
(d) Router wiring confirmation
Added "job.search" to SUPPORTED_OPERATION_IDS in app/routers/execute_v1.py.
Imported execute_job_search from app.services.theirstack_operations.
Added dispatch branch invoking execute_job_search, persisting execution via persist_operation_execution, and returning DataEnvelope.
(e) Test count + names
Added 17 tests in tests/test_theirstack_job_search.py:
test_map_job_item_full_fields
test_map_job_item_minimal_fields
test_map_hiring_team_item_valid
test_map_hiring_team_item_skip_empty
test_map_company_object_valid
test_map_company_object_skip_empty
test_search_jobs_pagination_params
test_search_jobs_metadata_in_output
test_job_search_full_filters
test_job_search_missing_required_filter
test_job_search_boolean_false_preserved
test_job_search_integer_zero_preserved
test_job_search_success_response_shape
test_job_search_empty_results
test_job_search_api_error
test_company_search_by_job_postings_still_works
test_company_search_by_job_postings_expanded_filters
(f) Edge cases / concerns
Test execution is currently blocked by missing pytest in the shell runtime, so runtime verification is pending.
job.search requires at least one of: posted_at_max_age_days, posted_at_gte, posted_at_lte, company_domain_or, company_linkedin_url_or, company_name_or; False and 0 values are preserved by design.
execute_v1 still only enforces strict entity_type for person.* and company.*; job.search is accepted under existing generic handling.