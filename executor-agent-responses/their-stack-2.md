All three deliverables are committed with the exact commit messages from the directive. I’ve also gathered the precise field/test counts and validation status for the final report.Implemented exactly per docs/EXECUTOR_DIRECTIVE_THEIRSTACK_REMAINING_FIELDS.md in 3 standalone commits (no push, no squash):
0bf91a9 — map remaining TheirStack job fields: locations array, countries, country_codes
ee3251b — add TheirStackJobLocation contract and multi-location fields to TheirStackJobItem
95c5a6e — add tests for TheirStack locations array and multi-country fields
What changed
app/providers/theirstack.py
Added _map_location_item(raw: dict) -> dict | None
Skips empty locations when both name and display_name are null
Maps only: name, state, state_code, country_code, country_name, display_name, latitude, longitude, type
Updated _map_job_item with:
locations (mapped list or None)
countries (_as_str_list)
country_codes (_as_str_list)
Placement follows directive (locations near location fields; countries near country fields)
app/contracts/theirstack.py
Added TheirStackJobLocation model before TheirStackJobItem
Added to TheirStackJobItem:
locations: list[TheirStackJobLocation] | None = None
countries: list[str] | None = None
country_codes: list[str] | None = None
tests/test_theirstack_job_search.py
Extended _sample_job_payload() with locations, countries, country_codes
Updated test_map_job_item_full_fields assertions:
2 mapped locations
first location checks (name, state_code, display_name, latitude, type)
confirms admin1_code, admin1_name, continent, id are absent
checks countries and country_codes
Updated test_map_job_item_minimal_fields to assert locations, countries, country_codes are None
Added:
test_map_location_item_valid
test_map_location_item_skip_empty
Updated test_job_search_success_response_shape:
asserts validated.results[0].locations is not None
asserts validated.results[0].countries is not None
Requested report
(a) Total mapped field count in _map_job_item: 41 ✅
(b) Total field count in TheirStackJobItem (including source_provider): 42 ✅
(c) TheirStackJobLocation field count: 9 ✅
(d) Test count and all test names: 27 total
From tests/test_theirstack_job_search.py (19):
test_map_job_item_full_fields
test_map_job_item_minimal_fields
test_map_hiring_team_item_valid
test_map_hiring_team_item_skip_empty
test_map_location_item_valid
test_map_location_item_skip_empty
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
From tests/test_theirstack.py (8):
test_execute_company_search_by_tech_stack_missing_filters_failed
test_execute_company_search_by_tech_stack_success_validates_contract
test_execute_company_search_by_job_postings_missing_filters_failed
test_execute_company_search_by_job_postings_success_validates_contract
test_execute_company_enrich_tech_stack_missing_identifiers_failed
test_execute_company_enrich_tech_stack_success_validates_contract
test_execute_company_enrich_hiring_signals_missing_domain_failed
test_execute_company_enrich_hiring_signals_success_validates_contract
(e) Confirmation existing tests still pass (tests/test_theirstack_job_search.py and tests/test_theirstack.py): Could not execute in this environment (pytest, python, and doppler are unavailable / missing). No linter issues were introduced in edited files.
(f) Anything to flag:
Repo has pre-existing unrelated dirty/untracked files (left untouched).
docs/api-reference-docs remains modified and uncommitted (pre-existing/unrelated).