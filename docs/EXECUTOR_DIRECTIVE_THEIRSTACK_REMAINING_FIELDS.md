# Directive: TheirStack Job Search — Map Remaining API Fields

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We recently enriched the TheirStack job search adapter from 8 to 38 mapped fields. Three meaningful fields from the API response are still unmapped: a structured `locations` array (multi-location jobs), `countries`/`country_codes` (multi-country remote jobs). This directive completes the mapping so we capture 100% of useful API data.

---

## API Response Fields to Add

From the TheirStack `POST /v1/jobs/search` response, each job item in `data[]` includes these fields we do not yet map:

### 1. `locations` — structured location array

```json
"locations": [
  {
    "name": "Live Oak",
    "state": "California",
    "state_code": "CA",
    "country_code": "US",
    "country_name": "United States",
    "display_name": "Live Oak, California, United States",
    "latitude": 37,
    "longitude": -122,
    "type": "city",
    "admin1_code": "CA",
    "admin1_name": "California",
    "continent": "NA",
    "id": 5367315
  }
]
```

Each location object has: `name`, `state`, `state_code`, `country_code`, `country_name`, `display_name`, `latitude`, `longitude`, `type`, `admin1_code`, `admin1_name`, `continent`, `id`.

This is critical for multi-location jobs — a single posting can list 3-4 cities. The flat `location`/`short_location` fields we already map only capture one.

### 2. `countries` — list of country names

```json
"countries": ["United States", "Canada", "Spain", "France", "Australia"]
```

For remote jobs that span multiple countries. We currently only map `country` (singular string).

### 3. `country_codes` — list of ISO2 country codes

```json
"country_codes": ["US", "CA", "ES", "FR", "AU"]
```

Parallel to `countries`. We currently only map `country_code` (singular string).

---

## Existing code to read before starting:

- `app/providers/theirstack.py` — `_map_job_item` function (line ~89), existing helper functions `_as_str`, `_as_float`, `_as_int`, `_as_str_list`, `_as_dict`, `_as_list`
- `app/contracts/theirstack.py` — `TheirStackJobItem` model, existing nested models `TheirStackHiringTeamMember`, `TheirStackEmbeddedCompany`
- `tests/test_theirstack_job_search.py` — existing test patterns, `_sample_job_payload()` fixture

---

## Deliverable 1: Add `_map_location_item` to Provider Adapter

**File:** `app/providers/theirstack.py`

Add a new mapping function:

**`_map_location_item(raw: dict) -> dict | None`**

Map these fields:

| Canonical field | Source field | Type |
|---|---|---|
| `name` | `name` | `str \| None` |
| `state` | `state` | `str \| None` |
| `state_code` | `state_code` | `str \| None` |
| `country_code` | `country_code` | `str \| None` |
| `country_name` | `country_name` | `str \| None` |
| `display_name` | `display_name` | `str \| None` |
| `latitude` | `latitude` | `float \| None` |
| `longitude` | `longitude` | `float \| None` |
| `type` | `type` | `str \| None` |

Skip items where both `name` and `display_name` are null (empty location object, not useful).

Do NOT map `admin1_code`, `admin1_name`, `continent`, or `id` — these are redundant with `state_code`/`state`/`country_code` or are TheirStack internal IDs.

### Update `_map_job_item` to include the three new fields:

Add these keys to the returned dict:

```python
"locations": locations or None,    # list[dict] | None — built by iterating raw["locations"] through _map_location_item, same pattern as hiring_team
"countries": _as_str_list(raw.get("countries")),
"country_codes": _as_str_list(raw.get("country_codes")),
```

Place `locations` near the existing location fields (after `cities`). Place `countries` and `country_codes` next to the existing `country` and `country_code` fields.

Commit standalone with message: `map remaining TheirStack job fields: locations array, countries, country_codes`

---

## Deliverable 2: Add Contract Models

**File:** `app/contracts/theirstack.py`

### 2a. Add `TheirStackJobLocation` model

Place it BEFORE `TheirStackJobItem` (same as the other nested models):

```python
class TheirStackJobLocation(BaseModel):
    name: str | None = None
    state: str | None = None
    state_code: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    display_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    type: str | None = None
```

### 2b. Add three fields to `TheirStackJobItem`

Add to the model (place near existing location fields):

```python
locations: list[TheirStackJobLocation] | None = None
countries: list[str] | None = None
country_codes: list[str] | None = None
```

Commit standalone with message: `add TheirStackJobLocation contract and multi-location fields to TheirStackJobItem`

---

## Deliverable 3: Update Tests

**File:** `tests/test_theirstack_job_search.py`

### 3a. Update `_sample_job_payload()` to include the three new fields:

```python
"locations": [
    {
        "name": "New York",
        "state": "New York",
        "state_code": "NY",
        "country_code": "US",
        "country_name": "United States",
        "display_name": "New York, New York, United States",
        "latitude": 40.7128,
        "longitude": -74.006,
        "type": "city",
        "admin1_code": "NY",
        "admin1_name": "New York",
        "continent": "NA",
        "id": 5128581
    },
    {
        "name": "San Francisco",
        "state": "California",
        "state_code": "CA",
        "country_code": "US",
        "country_name": "United States",
        "display_name": "San Francisco, California, United States",
        "latitude": 37.7749,
        "longitude": -122.4194,
        "type": "city",
        "admin1_code": "CA",
        "admin1_name": "California",
        "continent": "NA",
        "id": 5391959
    }
],
"countries": ["United States"],
"country_codes": ["US"],
```

### 3b. Update `test_map_job_item_full_fields` to assert the new fields:

- `locations` has 2 items
- First location: `name` == "New York", `state_code` == "NY", `display_name` == "New York, New York, United States", `latitude` == 40.7128, `type` == "city"
- Locations do NOT contain `admin1_code`, `admin1_name`, `continent`, or `id` keys
- `countries` == `["United States"]`
- `country_codes` == `["US"]`

### 3c. Update `test_map_job_item_minimal_fields` to assert graceful handling:

- `locations` is `None` when not present in payload
- `countries` is `None` when not present
- `country_codes` is `None` when not present

### 3d. Add new test `test_map_location_item_valid`:

Call `_map_location_item` directly with a full location object. Assert all 9 mapped fields are correct. Assert `admin1_code`, `admin1_name`, `continent`, `id` are NOT present in the result.

### 3e. Add new test `test_map_location_item_skip_empty`:

Call `_map_location_item` with `{"name": None, "display_name": None, "latitude": 0}`. Assert returns `None`.

### 3f. Update `test_job_search_success_response_shape` to verify:

- `validated.results[0].locations` is not None
- `validated.results[0].countries` is not None

Commit standalone with message: `add tests for TheirStack locations array and multi-country fields`

---

## What is NOT in scope

- No changes to `_map_company_item`, `_map_company_object`, `_map_hiring_team_item`, or `_map_tech_item`.
- No changes to operation services or the execute router.
- No changes to existing operations or their filter surface.
- No deploy commands. No migrations.

## Commit convention

Each deliverable is one commit. Do not push. Do not squash.

## When done

Report back with:
(a) Total mapped field count in `_map_job_item` (should be 41)
(b) Total field count in `TheirStackJobItem` contract (should be 42 including source_provider)
(c) `TheirStackJobLocation` field count
(d) Test count and all test names
(e) Confirmation that existing tests still pass (`tests/test_theirstack_job_search.py` and `tests/test_theirstack.py`)
(f) Anything to flag
