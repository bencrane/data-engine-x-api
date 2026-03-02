mplemented all 6 deliverables and created 6 standalone commits (no push):
5555c73 add Enigma get_brand_locations provider adapter for operating location retrieval
4b7b166 add EnigmaLocationsOutput contract for operating location enrichment
4c59e1c add company.enrich.locations operation service with brand match fallback
d050ed3 wire company.enrich.locations into execute router
b6c8842 add tests for Enigma operating locations provider adapter and operation
18049ff update system overview for company.enrich.locations operation
Also ran tests:
PYTHONPATH=. uv run --with pytest --with pytest-asyncio pytest tests/test_card_revenue.py tests/test_enigma_locations.py -q
Result: 13 passed
(a) GraphQL variable names and controls
searchInput: brand lookup target for query ({"entityType":"BRAND","id":<brand_id>})
locationLimit: number of operating locations to fetch (clamped to [1, 100])
locationConditions: optional GraphQL filter; when operating_status_filter is provided, sets {"filter":{"EQ":["operatingStatuses.operatingStatus", <value>]}}, else None
(b) Provider adapter function signature
async def get_brand_locations(*, api_key: str | None, brand_id: str | None, limit: int = 25, operating_status_filter: str | None = None) -> ProviderAdapterResult:
(c) _map_operating_location field list
enigma_location_id
location_name
full_address
street
city
state
postal_code
operating_status
(d) Contract field counts
EnigmaLocationItem: 8 fields
EnigmaLocationsOutput: 10 fields
(e) Operation service input extraction logic
In execute_company_enrich_locations:
enigma_brand_id: from input_data["enigma_brand_id"] first, fallback input_data["cumulative_context"]["enigma_brand_id"]
company_name: from input_data["company_name"], fallback cumulative_context["company_name"]
company_domain: from input_data["company_domain"], then normalized input_data["company_website"], then cumulative_context["company_domain"], then normalized cumulative_context["company_website"]
If no enigma_brand_id and no company_name/company_domain, returns failed with missing_inputs: ["enigma_brand_id|company_name|company_domain"]
If enigma_brand_id exists, skips match_business; otherwise does match_business first, then get_brand_locations
(f) Router wiring confirmation
app/routers/execute_v1.py updated with:
SUPPORTED_OPERATION_IDS includes company.enrich.locations
import added for execute_company_enrich_locations
dispatch branch added with persistence + DataEnvelope return, matching existing pattern
(g) Test count and names
Added tests/test_enigma_locations.py with 8 tests:
test_get_brand_locations_missing_api_key
test_get_brand_locations_missing_brand_id
test_get_brand_locations_success
test_get_brand_locations_empty
test_get_brand_locations_with_status_filter
test_execute_company_enrich_locations_missing_inputs
test_execute_company_enrich_locations_with_brand_id
test_execute_company_enrich_locations_with_domain_fallback
(h) Anything to flag
Repo had unrelated pre-existing dirty/untracked changes; untouched.
docs/SYSTEM_OVERVIEW.md previously had an inconsistent company enrichment count relative to listed rows; now updated to 8 with the new company.enrich.locations row and operation registry count updated to 51.