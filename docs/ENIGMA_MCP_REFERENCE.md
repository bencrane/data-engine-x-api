# Enigma MCP Reference

**Last updated:** 2026-03-18
**Source basis:** `mcps/user-enigma/tools/*.json` descriptors + `enigmadb://ontology/schema` resource (no live tool/API calls used for this document).

## 1. Tool Inventory

Total tools in `user-enigma`: **10**

---

### `search_business`

**Full description**

> 🔍 Find a SPECIFIC NAMED BUSINESS to analyze - searches for individual businesses by exact name, website, address, or phone.
>
> ⚠️ CRITICAL: This finds SPECIFIC BUSINESSES BY NAME, not business categories!
>
> ✅ CORRECT usage:
> • search_business("Starbucks") - Find the Starbucks corporation
> • search_business("Joe's Pizza") - Find a specific pizza place named Joe's
> • search_business("target.com") - Find Target by their website
> • search_business("Apple Inc") - Find Apple by company name
> • search_business("Tesla") - Find Tesla Motors
>
> ❌ INCORRECT usage (these won't work as expected):
> • search_business("coffee shops") - Not a business name!
> • search_business("restaurants") - Not a specific business!
> • search_business("tech companies") - Not a named business!
> • search_business("wholesalers") - This is a category, not a business name!
>
> 💡 **For bulk discovery by business type, use:**
> • generate_brands_segment(business_description="coffee shops") - Find all coffee companies
> • generate_locations_segment(business_description="restaurants") - Find all restaurant locations
>
> 🎯 **What you get back:**
> • Complete business profile with revenue data
> • Industry classifications (NAICS codes + descriptions)
> • Technology stack (payment processors, e-commerce platforms)
> • Operating locations count and sample addresses
> • Brand ID for deeper analysis with other tools
>
> Args:
> query: The SPECIFIC business name or website to search for
> limit: Maximum number of results to return (default: 1)
> street1: Optional street address line 1
> street2: Optional street address line 2
> city: Optional city name
> state: Optional state abbreviation or name
> postal_code: Optional postal/zip code
> phone_number: Optional phone number
>
> Returns:
> Business profile including revenue data, locations count, technologies used,
> and the Brand ID needed for deeper analysis with other tools.
>
> Next steps (optional):
> • get_brand_locations() - Analyze this brand's individual stores
> • get_brand_legal_entities() - Investigate corporate structure
> • get_brand_card_analytics() - Access detailed financial metrics
> • search_gov_archive() - Deep official records and regulatory intelligence

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query` | `string` | Yes | — | Specific business name or website. |
| `limit` | `integer` | No | `1` | Max results returned. |
| `street1` | `string \| null` | No | `null` | Optional street address line 1. |
| `street2` | `string \| null` | No | `null` | Optional street address line 2. |
| `city` | `string \| null` | No | `null` | Optional city filter. |
| `state` | `string \| null` | No | `null` | Optional state filter. |
| `postal_code` | `string \| null` | No | `null` | Optional ZIP/postal filter. |
| `phone_number` | `string \| null` | No | `null` | Optional phone filter. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `search_kyb`

**Full description**

> 🔍 Know Your Business (KYB) search - verify and get detailed information about a business.
>
> This tool performs KYB (Know Your Business) searches using business name, address, person, and TIN information.
> It's designed for business verification and due diligence purposes.
>
> Note: The API requires at least two of: business name, address, person objects, or TIN.
> Note: TIN verification is an optional add-on service and must be enabled on your account.
> Note: When TIN is supplied, the tool automatically requests tin_verification attributes from the API.
>
> Args:
> name: The business name to search for (required)
> street_address1: The street address of the business (optional)
> city: The city where the business is located (optional)
> state: The state where the business is located (optional)
> postal_code: The postal/ZIP code of the business (optional)
> person_first_name: First name of associated person for verification (optional)
> person_last_name: Last name of associated person for verification (optional)
> tin: Tax Identification Number - a 9-digit string (optional, requires add-on service).
>      When provided, automatically includes tin_verification attribute in the request.
>
> Returns:
> Detailed business information from the KYB search including verification status,
> business details, and any additional data returned by the API.
>
> Example:
> search_kyb("BMJ YACHTS LLC", "401 E Las Olas Blvd Ste 130", "Fort Lauderdale", "FL", "33301-2477")
> search_kyb("Acme Corp", person_first_name="John", person_last_name="Doe")
> search_kyb("Acme Corp", tin="123456789")

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `name` | `string` | Yes | — | Business name to verify. |
| `street_address1` | `string \| null` | No | `null` | Optional street address. |
| `city` | `string \| null` | No | `null` | Optional city. |
| `state` | `string \| null` | No | `null` | Optional state. |
| `postal_code` | `string \| null` | No | `null` | Optional postal code. |
| `person_first_name` | `string \| null` | No | `null` | Optional associated person first name. |
| `person_last_name` | `string \| null` | No | `null` | Optional associated person last name. |
| `tin` | `string \| null` | No | `null` | Optional 9-digit TIN (add-on dependent). |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `search_negative_news`

**Full description**

> Search for negative news and risk factors about a business using AI-powered web research.
>
> This tool performs comprehensive web research to identify potential risks, negative news,
> legal issues, controversies, and other red flags associated with a specific business.
>
> **What you discover:**
> • Legal issues (lawsuits, regulatory actions)
> • Financial problems (bankruptcy, debt issues)
> • Management controversies and scandals
> • Poor business practices and ethical concerns
> • Environmental violations and issues
> • Labor disputes and employment problems
> • Customer complaints and service issues
> • Product recalls and safety concerns
> • Cybersecurity incidents and data breaches
> • Any other potential red flags
>
> **Key insights provided:**
> • Risk assessment level (high, medium, low, unknown)
> • Detailed findings with specific issues
> • Source URLs for verification
> • Evidence-based analysis
>
> **Essential for:**
> • Due diligence research
> • Risk assessment and analysis
> • Vendor verification
> • Investment decision support
> • Compliance checking
> • Background research
>
> Args:
> business_name: The name of the business to research
> address: The business address to help distinguish from similar names
>
> Returns:
> Comprehensive risk assessment including findings, risk level, and sources

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `business_name` | `string` | Yes | — | Business name for risk research. |
| `address` | `string` | Yes | — | Address disambiguation for similarly named entities. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `search_gov_archive`

**Full description**

> Deep Official Records Intelligence - Comprehensive search across government databases, regulatory filings, and institutional data sources.
>
> **IMPORTANT: Always parallelize with search_kyb**
> For any entity lookup, call search_gov_archive and search_kyb in the same parallel batch.
> Do not use search_gov_archive as a standalone first step — search_kyb often surfaces entities
> that gov_archive alone misses (especially LLCs and newer registrations). Running them together
> is always faster and more complete than running them sequentially.
>
> **Optional: Two-Pass Row-Detail Retrieval**
> By default (include_row_details=False), results contain only core fields (business name, address,
> dataset info) — no raw record details. This is sufficient in most cases.
> If you need the full record details for specific datasets after reviewing Pass 1 hits, call again
> with include_row_details=True and resource_ids set to the relevant resource_ids from Pass 1.
> Skip Pass 2 entirely if Pass 1 returns no useful hits — additional gov_archive calls will not
> improve results; use search_kyb instead.
>
> query: search string applied across business name and address fields.
> Original prompt: the prompt that was used to call this tool. (optional, however it's highly recommended to provide it always)
> page: page number for pagination (default: 1).
> limit: number of records to return per page (default: 50, max: 300).
> historical_data: defaults to False. When False, records that are not present in the latest snapshot of data are removed and the `is_current` field is hidden.
> category: Filter results by data category (default: "all"). Use "all" for no filtering, or specify a category name to filter by resource type (e.g., "cannabis", "liquor_license", "business_license"). Categories are synced from the data catalog.
> include_row_details: defaults to False. Set to True only when retrieving full row_details for specific resource_ids identified in a prior call.
>
> ... (descriptor continues with source coverage, workflow, and note requiring non-empty query)
>
> Returns:
> Dictionary containing:
> - hits: Raw search results from the specified page
> - total_found: Total number of records available
> - page: Current page number
> - metadata: Additional processing information

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `query` | `string \| null` | No (schema), effectively yes by note | `null` | Search string (name/address/combined). |
| `original_prompt` | `string \| null` | No | `null` | Original user prompt for context. |
| `page` | `integer` | No | `1` | Pagination page number. |
| `limit` | `integer` | No | `50` | Results per page (descriptor says max `300`). |
| `historical_data` | `boolean` | No | `false` | Include historical/non-current records. |
| `category` | `string` | No | `"all"` | Dataset category filter. |
| `resource_ids` | `string[] \| null` | No | `null` | Direct resource ID filter (takes precedence over category per descriptor text). |
| `include_row_details` | `boolean` | No | `false` | Include full row details (recommended with `resource_ids`). |

**Return shape**

- JSON schema output is an object: `{ "result": object }` where `result` allows additional properties.

---

### `generate_locations_segment`

**Full description**

> Bulk discovery of business locations by type or description. Finds ALL business locations matching a business category, industry code or region (e.g., all coffee shop locations, all restaurant outlets). Use this to generate a segment of locations for market mapping, expansion analysis, or competitive research.
>
> Args:
> industry_description: Text description of the business type (e.g., 'coffee shop', 'fast food', 'auto repair')
> industry_codes: NAICS or other industry codes (optional)
> states, cities, postal_codes: Geographic filters (optional)
> has_phone_numbers, has_email_addresses: Filter for contact info (optional)
> operating_statuses: Filter by operating status (optional)
> min/max_annual_revenue, min/max_annual_growth: Financial filters (optional)
> limit: Maximum number of locations to return (optional, max 250))
> Ordering (optional): order_by_metric in [avg_transaction_size, has_transactions, refunds_amount, card_transactions_count, card_revenue_amount, card_customers_average_daily_count, card_revenue_yoy_growth, card_revenue_prior_period_growth]; order_period in [1m, 3m, 12m]; order_direction in [DESC, ASC]
> Returns:
> JSON list of locations matching the criteria, with summary info.
>
> Example usage:
> generate_locations_segment(industry_description='coffee shop')
> NOTE: when supplying a city, the state must also be supplied.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `industry_description` | `string \| null` | No | `null` | Business category/description. |
| `industry_codes` | `string \| string[] \| null` | No | `null` | Industry codes (NAICS/other). |
| `states` | `string \| string[] \| null` | No | `null` | State filter(s). |
| `cities` | `string \| string[] \| null` | No | `null` | City filter(s). |
| `postal_codes` | `string \| string[] \| null` | No | `null` | Postal/ZIP filter(s). |
| `has_phone_numbers` | `string \| boolean \| integer \| null` | No | `null` | Contact-availability filter. |
| `has_email_addresses` | `string \| boolean \| integer \| null` | No | `null` | Contact-availability filter. |
| `operating_statuses` | `string \| string[] \| null` | No | `null` | Operating status filter(s). |
| `min_annual_revenue` | `string \| number \| integer \| null` | No | `null` | Lower annual revenue bound. |
| `max_annual_revenue` | `string \| number \| integer \| null` | No | `null` | Upper annual revenue bound. |
| `min_annual_growth` | `string \| number \| integer \| null` | No | `null` | Lower annual growth bound. |
| `max_annual_growth` | `string \| number \| integer \| null` | No | `null` | Upper annual growth bound. |
| `order_by_metric` | `string \| null` | No | `null` | Sort metric (descriptor provides allowed values). |
| `order_period` | `string \| null` | No | `null` | Sort period (`1m`, `3m`, `12m`). |
| `order_direction` | `string \| null` | No | `null` | Sort direction (`DESC`, `ASC`). |
| `limit` | `integer` | No | `250` | Max locations returned (descriptor max `250`). |

**Return shape**

- JSON schema output is `{ "result": string | object[] }`.

---

### `generate_brands_segment`

**Full description**

> Bulk discovery of brands by business type or description. Finds ALL brands matching a business category, industry, or description (e.g., all coffee companies, all restaurant chains). Use this to generate a segment of brands for market analysis, prospecting, or competitive research.
>
> Args:
> industry_description: Text description of the business type (e.g., 'coffee shop', 'fast food', 'auto repair')
> industry_codes: NAICS or other industry codes (optional)
> states, cities, postal_codes: Geographic filters (optional)
> has_phone_numbers, has_email_addresses: Filter for contact info (optional)
> operating_statuses: Filter by operating status (optional)
> min/max_annual_revenue, min/max_annual_growth: Financial filters (optional)
> limit: Maximum number of brands to return (optional, max 250))
> Ordering (optional): order_by_metric in [avg_transaction_size, has_transactions, refunds_amount, card_transactions_count, card_revenue_amount, card_customers_average_daily_count, card_revenue_yoy_growth, card_revenue_prior_period_growth]; order_period in [1m, 3m, 12m]; order_direction in [DESC, ASC]
> Returns:
> JSON list of brands matching the criteria, with summary info.
>
> Example usage:
> generate_brands_segment(industry_description='coffee shop')
> NOTE: when supplying a city, the state must also be supplied.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `industry_description` | `string \| null` | No | `null` | Business category/description. |
| `industry_codes` | `string \| string[] \| null` | No | `null` | Industry codes (NAICS/other). |
| `states` | `string \| string[] \| null` | No | `null` | State filter(s). |
| `cities` | `string \| string[] \| null` | No | `null` | City filter(s). |
| `postal_codes` | `string \| string[] \| null` | No | `null` | Postal/ZIP filter(s). |
| `has_phone_numbers` | `string \| boolean \| integer \| null` | No | `null` | Contact-availability filter. |
| `has_email_addresses` | `string \| boolean \| integer \| null` | No | `null` | Contact-availability filter. |
| `operating_statuses` | `string \| string[] \| null` | No | `null` | Operating status filter(s). |
| `min_annual_revenue` | `string \| number \| integer \| null` | No | `null` | Lower annual revenue bound. |
| `max_annual_revenue` | `string \| number \| integer \| null` | No | `null` | Upper annual revenue bound. |
| `min_annual_growth` | `string \| number \| integer \| null` | No | `null` | Lower annual growth bound. |
| `max_annual_growth` | `string \| number \| integer \| null` | No | `null` | Upper annual growth bound. |
| `order_by_metric` | `string \| null` | No | `null` | Sort metric (descriptor provides allowed values). |
| `order_period` | `string \| null` | No | `null` | Sort period (`1m`, `3m`, `12m`). |
| `order_direction` | `string \| null` | No | `null` | Sort direction (`DESC`, `ASC`). |
| `limit` | `integer` | No | `250` | Max brands returned (descriptor max `250`). |

**Return shape**

- JSON schema output is `{ "result": string | object[] }`.

---

### `get_brand_card_analytics`

**Full description**

> Access deep financial analytics for THE SPECIFIC BRAND you searched - comprehensive transaction and revenue intelligence with detailed monthly breakdowns.
>
> ... (descriptor includes metric list, monthly series fields, and usage guidance)
>
> Args:
> brand_id: The brand ID from search_business "Brand ID (for locations)" field
> months_back: (optional) Number of months of historical data to retrieve (default: 12, max: 60).
> original_prompt: The original user prompt for context.
>
> Returns:
> Raw JSON containing comprehensive financial analytics with month-by-month breakdowns
> for the specified number of months, including revenue data, growth rates, customer
> metrics, and transaction patterns.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `brand_id` | `string` | Yes | — | Brand ID to analyze. |
| `months_back` | `integer` | No | `12` | Historical months to include (descriptor max `60`). |
| `original_prompt` | `string \| null` | No | `null` | Original prompt context. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `get_brands_by_legal_entity`

**Full description**

> 🏢 Find all brands linked to a specific legal entity - reverse lookup from legal entity to brands.
>
> This is the REVERSE of get_brand_legal_entities(). Instead of finding legal entities
> for a brand, this finds all brands associated with a known legal entity ID.
>
> ... (descriptor includes use cases and workflow)
>
> Args:
> legal_entity_id: The legal entity ID (from get_brand_legal_entities or search results)
>
> Returns:
> Complete list of brands associated with this legal entity, including
> industry info, location counts, websites, and IDs for further analysis.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `legal_entity_id` | `string` | Yes | — | Legal entity ID for reverse brand lookup. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `get_brand_legal_entities`

**Full description**

> ⚖️ Investigate corporate structure for THE SPECIFIC BRAND you searched - uncover their legal entities and registrations.
>
> ... (descriptor includes intended insights and use cases)
>
> Args:
> brand_id: The brand ID from search_business "Brand ID (for locations)" field
>
> Returns:
> Complete legal entity hierarchy including all business registrations,
> formation dates, and state-by-state compliance status.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `brand_id` | `string` | Yes | — | Brand ID for legal entity traversal. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

### `get_brand_locations`

**Full description**

> 📍 Analyze locations for THE SPECIFIC BRAND you searched - see performance metrics for each store/office.
>
> This examines all locations for ONE brand at a time. You must first find the brand
> using search_business() to get their Brand ID.
>
> ⚠️ IMPORTANT: This is NOT a geographic business directory!
> • ✅ Shows all Starbucks locations in Texas (after searching for Starbucks)
> • ❌ Does NOT show "all coffee shops in Texas" (use generate_locations_segment for that)
>
> ... (descriptor includes filter guidance)
>
> Args:
> brand_id: The brand ID from search_business "Brand ID (for locations)" field
> limit: Maximum number of locations to return (default: 25, max: 100)
>
> Returns:
> Detailed data for each location including address, revenue, rankings,
> and performance metrics. Use pagination for brands with 100+ locations.

**Parameters**

| Name | Type | Required | Default | Description |
|---|---|---:|---|---|
| `brand_id` | `string` | Yes | — | Brand ID whose locations will be returned. |
| `limit` | `integer` | No | `25` | Max locations returned (descriptor max `100`). |
| `state_filter` | `string \| null` | No | `null` | Optional state filter. |
| `operating_status` | `string \| null` | No | `null` | Optional operating status filter. |
| `location_type` | `string \| null` | No | `null` | Optional location type filter. |
| `min_latitude` | `number \| null` | No | `null` | Minimum latitude boundary. |
| `max_latitude` | `number \| null` | No | `null` | Maximum latitude boundary. |
| `min_longitude` | `number \| null` | No | `null` | Minimum longitude boundary. |
| `max_longitude` | `number \| null` | No | `null` | Maximum longitude boundary. |
| `cursor` | `string \| null` | No | `null` | Cursor for pagination/continuation. |

**Return shape**

- JSON schema output is an object: `{ "result": string }`.

---

## 2. Ontology Schema

Source: `enigmadb://ontology/schema` fetched via MCP resource.

### 2.1 Entity Types

| Entity | Required fields (schema-level) | Attribute count | Notes |
|---|---|---:|---|
| `brand` | `name` | 3 | Business trade/common name entity. |
| `operating_location` | *(none declared)* | 7 | Individual locations tied to brand/address/phone refs. |
| `address` | `city`, `full_address`, `msa`, `state`, `street_address1`, `zip` | 50 | Extensive USPS/standardization/deliverability fields. |
| `phone_number` | `phone_number` | 6 | Raw and standardized number parts. |
| `website` | `website` | 11 | Raw and parsed URL components. |
| `industry` | `industry_code`, `industry_desc`, `industry_type` | 4 | Supports NAICS/SIC/MCC variants. |
| `txn_merchant` | `merchant_id`, `merchant_name` | 4 | Transaction merchant identity. |
| `legal_entity` | *(none declared)* | 4 | Parent abstraction for person/registered_entity. |
| `person` | `first_name`, `full_name`, `last_name` | 14 | Individual person and normalized name fields. |
| `registered_entity` | *(none declared)* | 4 | Corporate registration entity object. |
| `role` | *(none declared)* | 8 | Role/job hierarchy and normalized fields. |
| `registration` | `file_number`, `jurisdiction_state` | 18 | Secretary-of-state registration metadata. |
| `tin` | *(none declared)* | 5 | Tax identifier entity and validation fields. |

### 2.2 Entity Attributes (complete)

#### `brand`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `name` | `string` | Yes | Trade/common name for a business from raw data. |
| `brand_id` | `integer` | No | ID column of brand table. |
| `standardized_name` | `string` | No | Cleaned/standardized name. |

#### `operating_location`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `name` | `string` | No | Operating location name. |
| `operating_status` | `string` enum (`closed`, `temporarily_closed`, `open`, `coming_soon`) | No | Operating status from Google side panel. |
| `standardized_name` | `string` | No | Standardized operating location name. |
| `entity_ref__brand_id` | `integer` | No | Brand entity reference ID. |
| `operating_location_id` | `integer` | No | ID column of operating_location table. |
| `entity_ref__address_id` | `integer` | No | Address entity reference ID. |
| `entity_ref__phone_number_id` | `integer` | No | Phone number entity reference ID. |

#### `address`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `msa` | `string` | Yes | MSA. |
| `zip` | `string` | Yes | Zip. |
| `city` | `string` | Yes | City. |
| `state` | `string` (US-state enum) | Yes | State. |
| `county` | `string` | No | County. |
| `country` | `string` | No | Country. |
| `latitude` | `string` | No | Latitude. |
| `longitude` | `string` | No | Longitude. |
| `address_id` | `integer` | No | ID column of address table. |
| `record_type` | `string` | No | USPS record type classification. |
| `full_address` | `string` | Yes | Full address. |
| `ruca_modified` | `string` | No | Modified RUCA code. |
| `ruca_standard` | `string` | No | Standard RUCA code. |
| `street_address1` | `string` | Yes | Street address line 1. |
| `street_address2` | `string` | No | Street address line 2. |
| `standardized_csa` | `string` | No | Standardized CSA. |
| `standardized_msa` | `string` | No | Standardized MSA. |
| `standardized_rdi` | `string` | No | Residential delivery indicator. |
| `standardized_po_box` | `string` | No | Deprecated PO box field. |
| `standardized_dpv_cmra` | `string` | No | CMRA flag. |
| `standardized_latitude` | `number` | No | Standardized latitude. |
| `standardized_longitude` | `number` | No | Standardized longitude. |
| `standardized_dpv_vacant` | `string` | No | Vacant indicator. |
| `standardized_dpv_no_stat` | `string` | No | No-stat indicator. |
| `standardized_sub_address` | `string` | No | Deprecated standardized sub-address. |
| `standardized_country_name` | `string` | No | Standardized country. |
| `standardized_full_address` | `string` | No | Standardized full address string. |
| `standardized_dpv_match_code` | `string` | No | DPV match code. |
| `standardized_street_address` | `string` | No | Deprecated standardized street address. |
| `standardized_component__city` | `string` | No | Standardized city component. |
| `standardized_h3_index_res_10` | `integer` | No | H3 index (resolution 10). |
| `standardized_iso_country_code` | `string` | No | ISO country code. |
| `standardized_component__county` | `string` | No | Standardized county component. |
| `standardized_component__zip_five` | `string` | No | Standardized ZIP5. |
| `standardized_component__zip_plus` | `string` | No | Standardized ZIP+4 add-on. |
| `standardized_coordinate_precision` | `string` | No | Coordinate precision. |
| `standardized_component__state_abbr` | `string` | No | State abbreviation. |
| `standardized_component__usps_box_id` | `string` | No | USPS box identifier. |
| `standardized_component__building_name` | `string` | No | Building name. |
| `standardized_component__usps_box_type` | `string` | No | USPS box type. |
| `standardized_component__address_number` | `string` | No | Address number. |
| `standardized_component__occupancy_type` | `string` | No | Occupancy type (suite/apt/floor...). |
| `standardized_component__usps_box_group_id` | `string` | No | USPS box group identifier. |
| `standardized_component__street_name_pre_dir` | `string` | No | Street pre-direction. |
| `standardized_component__usps_box_group_type` | `string` | No | USPS box group type. |
| `standardized_component__occupancy_identifier` | `string` | No | Occupancy identifier. |
| `standardized_component__street_name_post_dir` | `string` | No | Street post-direction. |
| `standardized_component__street_name_pre_type` | `string` | No | Street pre-type. |
| `standardized_component__address_number_suffix` | `string` | No | Address number suffix. |
| `standardized_component__street_component_name` | `string` | No | Core street name component. |
| `standardized_component__street_name_post_type` | `string` | No | Street post-type. |
| `standardized_component__street_name_post_modifier` | `string` | No | Street post-modifier. |

#### `phone_number`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `phone_number` | `string` | Yes | Raw phone number. |
| `phone_number_id` | `integer` | No | ID column of phone_number table. |
| `standardized_area_code` | `string` | No | First 3 digits excluding country code. |
| `standardized_line_number` | `string` | No | Final 4 digits. |
| `standardized_phone_number` | `string` | No | Standardized full number. |
| `standardized_exchange_number` | `string` | No | Middle 3 digits. |

#### `website`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `website` | `string` | Yes | Raw website URL. |
| `website_id` | `integer` | No | ID column of website table. |
| `standardized_path` | `string` | No | URL path. |
| `standardized_query` | `string` | No | URL query string. |
| `standardized_domain` | `string` | No | Root/main domain. |
| `standardized_website` | `string` | No | Standardized website string. |
| `standardized_fragment` | `string` | No | URL fragment. |
| `standardized_protocol` | `string` | No | Protocol (`http`/`https`). |
| `standardized_page_name` | `string` | No | Canonical page/site identifier. |
| `standardized_subdomain` | `string` | No | Subdomain. |
| `standardized_path_params` | `string` | No | Path params segment. |
| `standardized_top_level_domain` | `string` | No | TLD/public suffix. |

#### `industry`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `industry_id` | `integer` | No | ID column of industry table. |
| `industry_code` | `string` | Yes | Industry code (MCC/NAICS/SIC). |
| `industry_desc` | `string` | Yes | Industry description. |
| `industry_type` | `string` enum (`mcc_code`, `naics_code`, `naics_2017_code`, `naics_2022_code`, `sic_code`, `enigma_industry_description`) | Yes | Code system/type. |

#### `txn_merchant`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `merchant_id` | `string` | Yes | Source merchant identifier. |
| `merchant_name` | `string` | Yes | Merchant name. |
| `txn_merchant_id` | `integer` | No | ID column of txn_merchant table. |
| `standardized_merchant_name` | `string` | No | Standardized merchant name. |

#### `legal_entity`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `type` | `string` enum (`person`, `registered_entity`) | No | Subclass type. |
| `legal_entity_id` | `integer` | No | ID column of legal_entity table. |
| `entity_ref__person_id` | `integer` | No | Person ref ID. |
| `entity_ref__registered_entity_id` | `integer` | No | Registered entity ref ID. |

#### `person`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `title` | `string` | No | Honorific title. |
| `suffix` | `string` | No | Name suffix. |
| `full_name` | `string` | Yes | Full name. |
| `last_name` | `string` | Yes | Last name. |
| `person_id` | `integer` | No | ID column of person table. |
| `first_name` | `string` | Yes | First name. |
| `middle_name` | `string` | No | Middle name. |
| `date_of_birth` | `string` (`date`) | No | Date of birth. |
| `standardized_title` | `string` | No | Standardized title. |
| `standardized_suffix` | `string` | No | Standardized suffix. |
| `standardized_full_name` | `string` | No | Standardized full name. |
| `standardized_last_name` | `string` | No | Standardized last name. |
| `standardized_first_name` | `string` | No | Standardized first name. |
| `standardized_middle_name` | `string` | No | Standardized middle name. |

#### `registered_entity`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `name` | `string` | No | Registered name. |
| `standardized_name` | `string` | No | Standardized legal name. |
| `registered_entity_id` | `integer` | No | ID column of registered_entity table. |
| `registered_entity_type` | `string` | No | Entity type (LLC/corporation/etc). |

#### `role`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `role_id` | `integer` | No | ID column of role table. |
| `job_title` | `string` | No | Role title. |
| `role_type` | `string` enum (`functional`, `governance`) | No | Role category. |
| `job_function` | `string` | No | Job function. |
| `management_level` | `string` | No | Management level. |
| `standardized_job_title` | `string` | No | Normalized job title. |
| `standardized_job_function` | `string` | No | Normalized job function. |
| `standardized_management_level` | `string` | No | Normalized management level. |

#### `registration`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `issue_date` | `string` (`date`) | No | Filing issue date. |
| `file_number` | `string` | Yes | Statement/file number. |
| `expiration_date` | `string` (`date`) | No | Expiration date. |
| `registered_name` | `string` | No | Raw registered name. |
| `registration_id` | `integer` | No | ID column of registration table. |
| `sos_file_number` | `string` | No | Secretary of state file number. |
| `jurisdiction_code` | `string` | No | Jurisdiction code (`xx_yy`). |
| `jurisdiction_type` | `string` | No | `domestic`/`foreign`. |
| `registration_type` | `string` | No | Registered business type. |
| `jurisdiction_state` | `string` (US-state enum) | Yes | Jurisdiction state. |
| `registration_status` | `string` | No | Raw status text. |
| `jurisdiction_country` | `string` | No | Jurisdiction country code. |
| `home_jurisdiction_code` | `string` | No | Home jurisdiction code. |
| `home_jurisdiction_state` | `string` | No | Home jurisdiction state. |
| `home_jurisdiction_country` | `string` | No | Home jurisdiction country. |
| `home_jurisdiction_file_number` | `string` | No | Home jurisdiction file number. |
| `standardized_registration_status` | `string` | No | Standardized active/inactive status. |
| `standardized_registration_sub_status` | `string` | No | Standardized sub-status. |

#### `tin`

| Attribute | Type | Required | Description |
|---|---|---:|---|
| `tin` | `string` | No | Taxpayer identification number. |
| `tin_id` | `integer` | No | ID column of TIN table. |
| `tin_type` | `string` enum (`EIN`, `SSN`, `ITIN`, `ATIN`, `PTIN`) | No | TIN type. |
| `validity` | `string` | No | Valid-format/issued indicator. |
| `standardized_tin` | `string` | No | Standardized 9-digit TIN. |

### 2.3 Relationships

Schema does not include explicit cardinality constraints beyond `left_id`/`right_id` required fields, so cardinality is reported as **Not specified in schema**.

| Relationship | Source (left) | Target (right) | Relationship properties | Cardinality |
|---|---|---|---|---|
| `legal_entity__owns__brand` | `legal_entity` | `brand` | none | Not specified |
| `legal_entity__performs__role` | `legal_entity` | `role` | none | Not specified |
| `legal_entity__licenses__brand` | `legal_entity` | `brand` | none | Not specified |
| `brand__is_affiliated_with__brand` | `brand` | `brand` | `affiliation_type` enum (`merged`, `acquired`, `rebranded`, `sub_brand`, `agent`, `co_branded`, `co_located`, `dealer`, `divested`, `franchisee`, `join_venture`, `licensee`, `location_type`, `ownership`, `partnership`, `reseller`, `service`, `supplier`) | Not specified |
| `brand__operates_website__website` | `brand` | `website` | none | Not specified |
| `legal_entity__owns__legal_entity` | `legal_entity` | `legal_entity` | none | Not specified |
| `legal_entity__files_taxes_using__tin` | `legal_entity` | `tin` | `verification_result`, `verification_status` | Not specified |
| `person__is_instance_of__legal_entity` | `person` | `legal_entity` | none | Not specified |
| `brand__does_business_within__industry` | `brand` | `industry` | none | Not specified |
| `brand__operates_at__operating_location` | `brand` | `operating_location` | none | Not specified |
| `operating_location__operates_at__address` | `operating_location` | `address` | none | Not specified |
| `registration__registered__registered_entity` | `registration` | `registered_entity` | none | Not specified |
| `operating_location__operates_website__website` | `operating_location` | `website` | none | Not specified |
| `registered_entity__is_instance_of__legal_entity` | `registered_entity` | `legal_entity` | none | Not specified |
| `txn_merchant__generates_transactions_for__brand` | `txn_merchant` | `brand` | none | Not specified |
| `operating_location__can_be_called_at__phone_number` | `operating_location` | `phone_number` | none | Not specified |
| `txn_merchant__generates_transactions_at__operating_location` | `txn_merchant` | `operating_location` | none | Not specified |

### 2.4 `_meta` Section

#### Supported types

| Key | Values |
|---|---|
| `supported_entity_types` | `brand`, `operating_location`, `address`, `phone_number`, `website`, `industry`, `txn_merchant`, `legal_entity`, `person`, `registered_entity`, `role`, `registration`, `tin` |
| `supported_relationship_types` | `brand__operates_at__operating_location`, `brand__is_affiliated_with__brand`, `brand__does_business_within__industry`, `brand__operates_website__website`, `txn_merchant__generates_transactions_for__brand`, `txn_merchant__generates_transactions_at__operating_location`, `operating_location__can_be_called_at__phone_number`, `operating_location__operates_at__address`, `operating_location__operates_website__website`, `legal_entity__owns__brand`, `person__is_instance_of__legal_entity`, `registered_entity__is_instance_of__legal_entity`, `legal_entity__performs__role`, `registration__registered__registered_entity`, `legal_entity__files_taxes_using__tin`, `legal_entity__owns__legal_entity`, `legal_entity__licenses__brand` |

#### Relationship-level global property

| Property | Type | Allowed values | Default | Meaning |
|---|---|---|---|---|
| `assertion_type` | `string` | `positive`, `negative` | `positive` | Controls whether a relationship is asserted to exist or explicitly not exist. |

#### Tenants

| Tenant ID | Name | Description | Default |
|---|---|---|---:|
| `90a3403c-348e-11ef-b9db-1ed548a728f3` | `enigmadb` | Main knowledge graph for production data | Yes |
| `9120e514-348e-11ef-a6f0-1ed548a728f3` | `validation` | Validation businesses data | No |

---

## 3. MCP ↔ Our Operations Mapping

### 3.1 MCP tools mapped to current `data-engine-x-api` operations

| MCP Tool | Our Operation(s) | Mapping status | Notes |
|---|---|---|---|
| `search_business` | `company.enrich.card_revenue`, `company.enrich.locations` | Partial / implicit | No dedicated operation named "search business"; these ops internally do brand matching (name/domain → brand). |
| `search_kyb` | `company.verify.enigma.kyb` | Direct | Same conceptual KYB verification path (our provider uses Enigma KYB REST endpoint). |
| `generate_brands_segment` | `company.search.enigma.brands` | Partial | Same high-level "brand discovery" intent, but our operation is prompt-driven semantic search with narrower explicit filter surface than MCP segment tool. |
| `generate_locations_segment` | *(none direct)* | No direct counterpart | Our stack has `company.enrich.locations` for known brand locations, not open-market location segmentation. |
| `get_brand_card_analytics` | `company.enrich.card_revenue` | Direct | Brand-level card analytics; our op also performs brand match when needed. |
| `get_brands_by_legal_entity` | *(none direct)* | Missing | No operation currently exposing reverse legal-entity→brands lookup. |
| `get_brand_legal_entities` | `company.enrich.enigma.legal_entities` | Direct | Brand legal entities / registrations mapping is present. |
| `get_brand_locations` | `company.enrich.locations` | Direct | Core location enrichment path; our op includes optional extended fields. |
| `search_negative_news` | *(none direct)* | Missing | No direct operation in current API. |
| `search_gov_archive` | *(none direct)* | Missing | No direct operation in current API. |

### 3.2 Our Enigma operations with no MCP tool equivalent

| Our Operation | MCP equivalent? | Notes |
|---|---|---|
| `company.search.enigma.aggregate` | No | Aggregate market sizing query exists in our GraphQL adapter layer; no same-named MCP tool. |
| `company.search.enigma.person` | No | Person-based reverse business lookup operation in our API. |
| `company.enrich.enigma.address_deliverability` | No | Address deliverability enrichment exists in our API, not as MCP tool. |
| `company.enrich.enigma.technologies` | No | Payment/tech enrichment exists in our API, not as MCP tool. |
| `company.enrich.enigma.industries` | No | Industry enrichment exists in our API, not as MCP tool. |
| `company.enrich.enigma.affiliated_brands` | No | Affiliated-brands traversal exists in our API. |
| `company.enrich.enigma.marketability` | No | Marketability flag enrichment exists in our API. |
| `company.enrich.enigma.activity_flags` | No | Activity/compliance flags enrichment exists in our API. |
| `company.enrich.enigma.bankruptcy` | No | Bankruptcy traversal exists in our API. |
| `company.enrich.enigma.watchlist` | No | Watchlist traversal exists in our API. |
| `person.search.enigma.roles` | No | Brand→location→roles person discovery exists in our API. |
| `person.enrich.enigma.profile` | No | Officer/person profile via legal entities exists in our API. |

### 3.3 Coverage summary

- MCP tools with direct/partial mapping into our operations: **7/10**.
- MCP tools with no current operation counterpart: **3/10** (`generate_locations_segment`, `search_negative_news`, `search_gov_archive`; plus `get_brands_by_legal_entity` missing as reverse lookup).
- Our listed Enigma operations with no MCP tool counterpart: **12/17**.

---

## 4. MCP Discovery Flow

Recommended flow for SMB list building via MCP descriptors:

### 4.1 Discovery-first path (new market list)

1. Start with **`generate_brands_segment`** for brand-level discovery or **`generate_locations_segment`** for location-first discovery.
2. Apply cheapest narrowing filters early:
   - `industry_description` / `industry_codes`
   - geography (`states`, then `cities`, then `postal_codes`)
   - `limit`
3. Sort intentionally if needed:
   - `order_by_metric`, `order_period`, `order_direction`.

### 4.2 Enrichment chain

For each brand candidate:

1. **`get_brand_card_analytics`** (revenue and transaction trends).
2. **`get_brand_locations`** (store-level footprint and performance signals).
3. **`get_brand_legal_entities`** (ownership and registrations).
4. Optional expansion:
   - Use legal entity IDs from step 3 in **`get_brands_by_legal_entity`** to discover affiliated portfolio brands.
5. Risk/compliance pass:
   - Run **`search_negative_news`** and **`search_gov_archive`** (descriptor guidance suggests pairing gov-archive with KYB context where possible).
   - Use **`search_kyb`** for entity verification.

### 4.3 Parameters that most impact spend / payload size

From descriptor surface:

- **High impact**
  - `limit` on segment/discovery/listing tools (`generate_*_segment`, `get_brand_locations`, `search_gov_archive`).
  - `months_back` on `get_brand_card_analytics` (larger historical windows).
  - `include_row_details` + `resource_ids` on `search_gov_archive` (second-pass deep detail retrieval).
- **Moderate impact**
  - Geography breadth (`states` vs `cities` vs `postal_codes`) on segment tools.
  - `page` and repeated pagination calls on `search_gov_archive`.

### 4.4 Input/output handoff patterns

- `search_business` → emits brand context → feed `brand_id` into:
  - `get_brand_card_analytics`
  - `get_brand_locations`
  - `get_brand_legal_entities`
- `get_brand_legal_entities` → emits `legal_entity_id` values → feed into:
  - `get_brands_by_legal_entity`
- Segment tools (`generate_brands_segment` / `generate_locations_segment`) → emit candidate records → feed individual entities through analytics/legal/risk tools in batches.

---

## 5. MCP vs Direct API

This section compares MCP descriptor capabilities to the direct Enigma GraphQL/KYB operations implemented in `data-engine-x-api`.

### 5.1 Capabilities MCP exposes that our direct GraphQL path does not

- `search_negative_news` appears MCP-only in current implementation scope.
- `search_gov_archive` appears MCP-only in current implementation scope.
- `get_brands_by_legal_entity` reverse traversal is available in MCP but not currently exposed as one of our operations.
- Broad open-market location segmentation (`generate_locations_segment`) is available as MCP tool but not currently represented as a direct operation in our API.

### 5.2 Where MCP simplifies usage

- MCP tools package multi-hop graph traversals into one call with straightforward arguments (`brand_id`, `legal_entity_id`, etc.).
- Segment tools provide business-oriented filter inputs (`industry_description`, `states`, `min_annual_revenue`, ordering knobs) instead of manual GraphQL construction.
- Descriptors include explicit usage guidance and recommended sequencing, reducing client-side query orchestration burden.

### 5.3 Are `search_negative_news` and `search_gov_archive` MCP-exclusive?

Based on:
- current MCP descriptor inventory, and
- currently wired Enigma provider operations in `data-engine-x-api`,

they are **MCP-exclusive in this system today** (no corresponding direct operation is currently implemented in `execute_v1`/provider adapters).

### 5.4 Where direct API in our stack is broader than MCP

Our Enigma GraphQL/KYB operation layer includes many specialized enrichments not represented as MCP tools in this server package:

- aggregate market sizing
- person reverse lookup
- address deliverability
- technologies
- industries
- affiliated brands
- marketability flags
- activity flags
- bankruptcy
- watchlist
- roles discovery
- officer-person profile

These are implemented as first-class operations in our `/api/v1/execute` surface.

---

## Appendix A: Tool Output Schemas (raw summary)

| Tool | `outputSchema` summary |
|---|---|
| `search_business` | `{ result: string }` |
| `search_kyb` | `{ result: string }` |
| `search_negative_news` | `{ result: string }` |
| `search_gov_archive` | `{ result: object }` (additional properties allowed) |
| `generate_locations_segment` | `{ result: string \| object[] }` |
| `generate_brands_segment` | `{ result: string \| object[] }` |
| `get_brand_card_analytics` | `{ result: string }` |
| `get_brands_by_legal_entity` | `{ result: string }` |
| `get_brand_legal_entities` | `{ result: string }` |
| `get_brand_locations` | `{ result: string }` |

