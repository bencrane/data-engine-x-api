Implemented the directive fully with 7 standalone commits (no push):
848431e add RAPIDAPI_SALESNAV_SCRAPE_API_KEY to config
2a457ef add RapidAPI Sales Navigator URL scraper provider adapter
a821fda add contract for Sales Navigator URL scraper output
5bfd34e add person.search.sales_nav_url operation service
fcb64b3 wire person.search.sales_nav_url into execute router
2f66cc1 add tests for person.search.sales_nav_url operation
2b1d355 update documentation for person.search.sales_nav_url operation
(a) Config env var name
RAPIDAPI_SALESNAV_SCRAPE_API_KEY (mapped via rapidapi_salesnav_scrape_api_key in app/config.py)
(b) Provider adapter signature + endpoint
Signature:
scrape_sales_nav_url(*, api_key: str | None, sales_nav_url: str, page: int = 1, account_number: int = 1) -> ProviderAdapterResult
Endpoint called:
POST https://realtime-linkedin-sales-navigator-data.p.rapidapi.com/premium_search_person_via_url
Implemented in app/providers/rapidapi_salesnav.py
(c) Person mapping field count
19 fields per mapped person object.
(d) Contract field counts
SalesNavPersonItem: 19 fields
SalesNavSearchOutput: 6 fields
(e) Operation service input extraction
sales_nav_url: checks input_data["sales_nav_url"], then input_data["cumulative_context"]["sales_nav_url"]
page: checks input_data["page"], then input_data["options"]["page"], default 1
account_number: checks input_data["account_number"], default 1
(f) Router wiring confirmation
Added operation ID to SUPPORTED_OPERATION_IDS in app/routers/execute_v1.py
Added import for execute_person_search_sales_nav_url
Added dispatch branch with persist_operation_execution(...) and DataEnvelope(data=result)
(g) Test count and names
7 tests in tests/test_salesnav_url_scraper.py:
test_scrape_sales_nav_url_missing_api_key
test_scrape_sales_nav_url_missing_url
test_scrape_sales_nav_url_success
test_scrape_sales_nav_url_empty_results
test_scrape_sales_nav_url_http_error
test_scrape_sales_nav_url_maps_person_fields
test_execute_reads_from_cumulative_context
Executed: PYTHONPATH=. uv run --with pytest --with pytest-asyncio pytest tests/test_salesnav_url_scraper.py
Result: 7 passed
(h) Anything to flag
CLAUDE.md had no explicit operation-count references to update, so no changes were made there.
docs/SYSTEM_OVERVIEW.md was updated to 62 operations and includes the new person.search.sales_nav_url row.
Existing unrelated dirty/untracked workspace changes were left untouched.