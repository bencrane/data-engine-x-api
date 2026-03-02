# Directive: `person.search.sales_nav_url` — RapidAPI Sales Navigator URL Scraper

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We have a RapidAPI endpoint that takes a full LinkedIn Sales Navigator search URL and returns person results (names, titles, companies, LinkedIn profile URLs). This directive builds a standalone operation that accepts a Sales Nav URL, calls the RapidAPI scraper, and returns the results as a fan-out-capable list. This is a standard FastAPI operation — fast response time (seconds), goes through `/api/v1/execute`.

---

## RapidAPI Endpoint Reference

**Endpoint:** `POST https://realtime-linkedin-sales-navigator-data.p.rapidapi.com/premium_search_person_via_url`

**Headers:**
```
x-rapidapi-host: realtime-linkedin-sales-navigator-data.p.rapidapi.com
x-rapidapi-key: <from RAPIDAPI_SALESNAV_SCRAPE_API_KEY env var>
Content-Type: application/json
```

**Request body:**
```json
{
  "page": 1,
  "url": "<full Sales Navigator search URL>",
  "account_number": 1
}
```

**Response (success):**
```json
{
  "success": true,
  "status": 200,
  "response": {
    "data": [
      {
        "firstName": "Kyohwe",
        "fullName": "Kyohwe Goo",
        "lastName": "Goo",
        "geoRegion": "South Korea",
        "currentPosition": {
          "tenureAtPosition": { "numYears": 4, "numMonths": 8 },
          "companyName": "Hyundai Motor Company",
          "description": "...",
          "title": "Design Strategy",
          "companyId": "825160",
          "companyUrnResolutionResult": {
            "name": "Hyundai Motor Company",
            "industry": "Motor Vehicle Manufacturing",
            "location": "Seoul, Seoul, South Korea"
          },
          "current": true,
          "tenureAtCompany": { "numYears": 4, "numMonths": 8 },
          "startedOn": { "month": 5, "year": 2020 }
        },
        "profilePictureDisplayImage": "https://...",
        "summary": "...",
        "profileUrn": "ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY",
        "navigationUrl": "https://www.linkedin.com/in/ACwAACc_JjIBSeHOEA2truT7un1QADxUExNCuoY",
        "openLink": false
      }
    ],
    "pagination": {
      "total": 11,
      "count": 25,
      "start": 0,
      "links": []
    }
  }
}
```

**Pagination:** The API returns up to 25 results per page. For more results, increment `page` (1, 2, 3, etc.). `pagination.total` indicates the total number of results available.

---

## Existing code to read before starting

- `app/providers/revenueinfra/validate_job.py` — reference pattern for calling an external HTTP endpoint with header-based auth
- `app/providers/revenueinfra/_common.py` — shared helpers (`ProviderAdapterResult`, `now_ms`, `parse_json_or_raw`)
- `app/services/research_operations.py` — reference pattern for operation service functions
- `app/contracts/company_research.py` — reference pattern for Pydantic contracts with lists
- `app/routers/execute_v1.py` — operation dispatch + `SUPPORTED_OPERATION_IDS`
- `app/config.py` — settings class (you will add the API key here)
- `#A - User Inputs/rapid-api-sample-response.json` — full sample response with 11 person results

---

## Deliverable 1: Config

**File:** `app/config.py`

Add to the Settings class:

```python
rapidapi_salesnav_scrape_api_key: str | None = None
```

Env var: `RAPIDAPI_SALESNAV_SCRAPE_API_KEY` (already exists in Doppler).

Commit standalone with message: `add RAPIDAPI_SALESNAV_SCRAPE_API_KEY to config`

---

## Deliverable 2: Provider Adapter

**File:** `app/providers/rapidapi_salesnav.py` (new file)

```python
async def scrape_sales_nav_url(
    *,
    api_key: str | None,
    sales_nav_url: str,
    page: int = 1,
    account_number: int = 1,
) -> ProviderAdapterResult:
```

**Logic:**
1. Skip if `api_key` is missing → `skipped`, `missing_provider_api_key`
2. Skip if `sales_nav_url` is missing/empty → `skipped`, `missing_required_inputs`
3. Call `POST https://realtime-linkedin-sales-navigator-data.p.rapidapi.com/premium_search_person_via_url` with:
   - Headers: `x-rapidapi-host: realtime-linkedin-sales-navigator-data.p.rapidapi.com`, `x-rapidapi-key: <api_key>`, `Content-Type: application/json`
   - Body: `{ "page": page, "url": sales_nav_url, "account_number": account_number }`
4. Timeout: 30 seconds.
5. If HTTP error → `failed`
6. Parse response. If `success: false` or no `response.data` → `not_found`
7. Map each person in `response.data` to a canonical person object:

```python
def _map_person(raw: dict) -> dict:
    current = raw.get("currentPosition") or {}
    company_urn = current.get("companyUrnResolutionResult") or {}
    started_on = current.get("startedOn") or {}
    tenure_position = current.get("tenureAtPosition") or {}
    tenure_company = current.get("tenureAtCompany") or {}

    return {
        "full_name": raw.get("fullName"),
        "first_name": raw.get("firstName"),
        "last_name": raw.get("lastName"),
        "linkedin_url": raw.get("navigationUrl"),
        "profile_urn": raw.get("profileUrn"),
        "geo_region": raw.get("geoRegion"),
        "summary": raw.get("summary"),
        "current_title": current.get("title"),
        "current_company_name": current.get("companyName"),
        "current_company_id": current.get("companyId"),
        "current_company_industry": company_urn.get("industry"),
        "current_company_location": company_urn.get("location"),
        "position_start_month": started_on.get("month"),
        "position_start_year": started_on.get("year"),
        "tenure_at_position_years": tenure_position.get("numYears"),
        "tenure_at_position_months": tenure_position.get("numMonths"),
        "tenure_at_company_years": tenure_company.get("numYears"),
        "tenure_at_company_months": tenure_company.get("numMonths"),
        "open_link": raw.get("openLink"),
    }
```

8. Return mapped output:

```python
"mapped": {
    "results": [_map_person(p) for p in data],
    "result_count": len(data),
    "total_available": pagination.get("total"),
    "page": page,
    "source_url": sales_nav_url,
}
```

**Important:** The output key must be `results` (a list of dicts) for fan-out compatibility.

Commit standalone with message: `add RapidAPI Sales Navigator URL scraper provider adapter`

---

## Deliverable 3: Contract

**File:** `app/contracts/sales_nav.py` (new file)

```python
from pydantic import BaseModel


class SalesNavPersonItem(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    profile_urn: str | None = None
    geo_region: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    current_company_id: str | None = None
    current_company_industry: str | None = None
    current_company_location: str | None = None
    position_start_month: int | None = None
    position_start_year: int | None = None
    tenure_at_position_years: int | None = None
    tenure_at_position_months: int | None = None
    tenure_at_company_years: int | None = None
    tenure_at_company_months: int | None = None
    open_link: bool | None = None


class SalesNavSearchOutput(BaseModel):
    results: list[SalesNavPersonItem] | None = None
    result_count: int | None = None
    total_available: int | None = None
    page: int | None = None
    source_url: str | None = None
    source_provider: str = "rapidapi_salesnav"
```

Commit standalone with message: `add contract for Sales Navigator URL scraper output`

---

## Deliverable 4: Service Operation

**File:** `app/services/salesnav_operations.py` (new file)

```python
async def execute_person_search_sales_nav_url(
    *,
    input_data: dict[str, Any],
) -> dict[str, Any]:
```

**Input extraction:**
- `sales_nav_url` from `input_data.get("sales_nav_url")` or `input_data.get("cumulative_context", {}).get("sales_nav_url")`
- `page` from `input_data.get("page")` or `input_data.get("options", {}).get("page")` — default 1
- `account_number` from `input_data.get("account_number")` — default 1

**Required inputs:** `sales_nav_url`. Missing → return `status: "failed"` with `missing_inputs: ["sales_nav_url"]`.

**Provider call:**
```python
settings = get_settings()
result = await scrape_sales_nav_url(
    api_key=settings.rapidapi_salesnav_scrape_api_key,
    sales_nav_url=sales_nav_url,
    page=page,
    account_number=account_number,
)
```

Validate with `SalesNavSearchOutput` contract. Follow the exact attempt tracking + status derivation pattern from existing operation services.

**Operation ID:** `"person.search.sales_nav_url"`

Commit standalone with message: `add person.search.sales_nav_url operation service`

---

## Deliverable 5: Router Wiring

**File:** `app/routers/execute_v1.py`

1. Add `"person.search.sales_nav_url"` to `SUPPORTED_OPERATION_IDS`.
2. Import `execute_person_search_sales_nav_url` from `app.services.salesnav_operations`.
3. Add dispatch branch:

```python
if payload.operation_id == "person.search.sales_nav_url":
    result = await execute_person_search_sales_nav_url(input_data=payload.input)
    persist_operation_execution(
        auth=auth,
        entity_type=payload.entity_type,
        operation_id=payload.operation_id,
        input_payload=payload.input,
        result=result,
    )
    return DataEnvelope(data=result)
```

Commit standalone with message: `wire person.search.sales_nav_url into execute router`

---

## Deliverable 6: Tests

**File:** `tests/test_salesnav_url_scraper.py` (new file)

### Required test cases:

1. `test_scrape_sales_nav_url_missing_api_key` — skipped with `missing_provider_api_key`
2. `test_scrape_sales_nav_url_missing_url` — skipped with `missing_required_inputs`
3. `test_scrape_sales_nav_url_success` — mock RapidAPI response with 3 persons. Verify `result_count == 3`, `results` has 3 items, each has `full_name`, `linkedin_url`, `current_title`, `current_company_name`.
4. `test_scrape_sales_nav_url_empty_results` — mock response with empty `data` array. Verify `status: "not_found"`.
5. `test_scrape_sales_nav_url_http_error` — mock HTTP 500. Verify `status: "failed"`.
6. `test_scrape_sales_nav_url_maps_person_fields` — verify all mapped fields from the sample response are correctly extracted (tenure, company ID, geo_region, profile_urn, etc.).
7. `test_execute_reads_from_cumulative_context` — verify `sales_nav_url` is read from `cumulative_context` when not in direct input.

Mock all HTTP calls. Use data from `#A - User Inputs/rapid-api-sample-response.json`.

Commit standalone with message: `add tests for person.search.sales_nav_url operation`

---

## Deliverable 7: Update Documentation

### File: `docs/SYSTEM_OVERVIEW.md`

Add to Person section:
```
| `person.search.sales_nav_url` | RapidAPI Sales Navigator scraper (accepts full Sales Nav URL, returns person results) |
```

Update operation count (62 total).

### File: `CLAUDE.md`

Update operation count references if present.

Commit standalone with message: `update documentation for person.search.sales_nav_url operation`

---

## What is NOT in scope

- No Sales Nav template URL swapping (that's `person.search.sales_nav_alumni` — separate, blocked on LinkedIn org ID)
- No pagination handling beyond single page (caller can pass `page` param for additional pages)
- No dedicated storage table (results go through standard entity state + step_results)
- No deploy commands

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Config env var name
(b) Provider adapter function signature and RapidAPI endpoint it calls
(c) Person mapping field count (how many fields per person)
(d) Contract field counts (SalesNavPersonItem, SalesNavSearchOutput)
(e) Operation service input extraction (what context fields it checks)
(f) Router wiring confirmation
(g) Test count and names
(h) Anything to flag
