# USASpending.gov & SAM.gov API Test Report

**Generated:** 2026-03-14

## Summary

| Test | Name | Status | Status Code | Notes |
|------|------|--------|-------------|-------|
| 1 | Spending By Award Search | ✅ PASS | 200 | |
| 1b | Spending By Award Search (page 2) | ✅ PASS | 200 | Pagination works |
| 2 | Recipient Details | ✅ PASS | 200 | Uses `recipient_id` (hash-level format) |
| 3 | Award Details | ✅ PASS | 200 | Uses `generated_internal_id`, not Award ID |
| 4 | NAICS Code Reference | ✅ PASS | 200 | |
| 5 | Bulk Download (optional) | ✅ PASS | 200 | Returns status_url, file_url immediately |
| 6 | Full Response Schema Discovery | ✅ PASS | 200 | |
| 7 | SAM Entity Management — Basic Search | ❌ FAIL | 429 | Rate limited (quota exceeded) |
| 8 | SAM Entity Management — Search by UEI | ❌ FAIL | — | No UEI from Test 7 |
| 9 | SAM Entity Management — Search by Business Name | ❌ FAIL | 429 | Rate limited |
| 10 | SAM Entity Management — CSV Format | ❌ FAIL | 429 | Rate limited |
| 11 | SAM Entity Management — Full Section Discovery | ❌ FAIL | — | No UEI from Test 7 |
| 12 | SAM Entity Extracts — List Available Files | ❌ FAIL | 429 | Rate limited |
| 13 | SAM Entity Extracts — Daily Delta | ❌ FAIL | 429 | Rate limited |
| 14 | SAM Get Opportunities API | ❌ FAIL | 429 | Rate limited |

---

## API #1: USASpending.gov — Detailed Results

### Test 1: Spending By Award Search

**Payload:** Small business manufacturers (NAICS 31-33), contract awards (A/B/C/D), last 30 days.

**Result:** 200 OK. `results` array contains award objects. `page_metadata` present with `page`, `hasNext`.

**Sample data (5 records):**

| Recipient Name | Award Amount | Awarding Agency | NAICS Code | Start Date | State |
|----------------|--------------|----------------|------------|------------|-------|
| MORGAN INGLAND LLC | $36,670 | Department of Homeland Security | 334416 | 2026-11-25 | MD |
| ALPHASIX, LLC. | $3,930 | Department of Justice | 339940 | 2026-09-30 | VA |
| FOUR POINTS TECHNOLOGY, L.L.C. | $42,333.33 | Department of Justice | 339112 | 2026-09-30 | VA |
| PHAMATECH, INCORPORATED | $1,387.12 | Department of Justice | 334516 | 2026-09-30 | CA |
| BURBANK DENTAL LABORATORY, INC. | $1,012.20 | Department of Justice | 339116 | 2026-09-30 | CA |

**NAICS validation:** All results have NAICS codes starting with 31, 32, or 33 (manufacturing). ✅

**page_metadata:** `{"page": 1, "hasNext": true, "last_record_unique_id": 355577356, "last_record_sort_value": "1782864000000"}`

### Test 1b: Pagination (page 2)

**Result:** 200 OK. Page 2 returns different results. `page_metadata.page`: 2, `hasNext`: true. ✅

**Sample recipients from page 2:** BURBANK DENTAL LABORATORY, INC., PLATYPUS MARINE INC, COMBINED SYSTEMS INC, GEISSELE AUTOMATICS LLC, CABRAS MARINE CORPORATION

### Test 2: Recipient Details

**Identifier used:** `recipient_id` = `817a95dd-cd8c-484c-4a25-334ad922ba6f-C` (hash + level suffix, e.g. `-C` for child)

**Endpoint:** `GET /api/v2/recipient/{recipient_id}/`

**Result:** 200 OK. Response includes: name, uei, recipient_id, business_types, location (address, city, state, zip), total_transaction_amount, total_transactions.

**Note:** UEI is the modern identifier; DUNS is deprecated (null in results).

### Test 3: Award Details

**Identifier used:** `generated_internal_id` = `CONT_AWD_70Z04026P60354Y00_7008_-NONE-_-NONE-`

**Important:** The Award ID (e.g. `70Z04026P60354Y00`) alone returns 404. Use `generated_internal_id` from search results.

**Endpoint:** `GET /api/v2/awards/{generated_internal_id}/`

**Result:** 200 OK. Full award details: piid, category, type, description, total_obligation, date_signed, recipient (hash, name, uei, location), period_of_performance, place_of_performance, naics_hierarchy, psc_hierarchy, funding_agency, awarding_agency, latest_transaction_contract_data.

### Test 4: NAICS Code Reference

**Endpoint:** `GET /api/v2/references/naics/33/`

**Result:** 200 OK. Returns hierarchy: `results[0]` has `naics`, `naics_description`, `children` array of sub-codes (3311, 3312, … 3399) with descriptions and counts.

### Test 5: Bulk Download

**Endpoint:** `POST /api/v2/bulk_download/awards/`

**Payload:** `prime_award_types`, `date_type`, `date_range`, `agencies` (required).

**Result:** 200 OK. Returns immediately with `status_url`, `file_name`, `file_url`. Does not wait for file generation. ✅

### Test 6: Full Response Schema — All Available Fields

**Fields returned (from spending_by_award with full field request):**

```
internal_id, Award ID, Recipient Name, Recipient DUNS Number, recipient_id, Recipient UEI,
Awarding Agency, Awarding Sub Agency, Funding Agency, Funding Sub Agency,
Place of Performance State Code, Start Date, End Date, Award Amount, Total Outlays,
Contract Award Type, NAICS, PSC, Recipient Location, Primary Place of Performance,
generated_internal_id, awarding_agency_id, agency_slug
```

**NAICS structure:** `{"code": "334416", "description": "..."}` (object, not string)

**PSC structure:** `{"code": "5999", "description": "..."}` (object)

**Recipient Location / Primary Place of Performance:** Nested objects with `location_country_code`, `country_name`, `state_code`, `state_name`, `city_name`, `county_code`, `county_name`, `address_line1`, `zip4`, `zip5`, `congressional_code`.

---

## API #2: SAM.gov — Rate Limit Encountered

All SAM.gov tests returned **429 / quota exceeded**:

```json
{
  "code": "900804",
  "message": "Message throttled out",
  "description": "You have exceeded your quota. You can access API after 2026-Mar-15 00:00:00+0000 UTC",
  "nextAccessTime": "2026-Mar-15 00:00:00+0000 UTC"
}
```

**Tests 7–14 could not be validated** due to rate limiting. Re-run after quota reset (2026-Mar-15) with:

```bash
doppler run -- bash scripts/test_usaspending_sam_apis.sh /tmp/api_test_output
```

**SAM.gov endpoints to validate (once quota resets):**

| Test | Endpoint | Purpose |
|------|----------|---------|
| 7 | `GET /entity-information/v3/entities?naicsCode=33&registrationDate=[...]` | Basic entity search |
| 8 | `GET /entity-information/v3/entities?ueiSAM={UEI}` | Lookup by UEI |
| 9 | `GET /entity-information/v3/entities?legalBusinessName=ACME` | Search by name |
| 10 | Same as 7 with `&format=csv` | CSV export |
| 11 | Same as 8 with `includeSections=entityRegistration,coreData,generalInformation,repsAndCerts,pointsOfContact` | Full section discovery |
| 12 | `GET /data-services/v1/extracts?fileType=ENTITY&sensitivity=PUBLIC&frequency=MONTHLY` | Monthly extract list |
| 13 | `GET /data-services/v1/extracts?fileType=ENTITY&sensitivity=PUBLIC&frequency=DAILY&date=03/12/2026` | Daily delta |
| 14 | `GET /opportunities/v2/search?postedFrom=...&postedTo=...&ptype=o` | Opportunities |

---

## Errors & Deviations

1. **USASpending Award Details:** `GET /api/v2/awards/{award_id}/` expects `generated_internal_id`, not the human-readable Award ID (PIID). Documented in API but easy to miss.

2. **USASpending Sort:** The `sort` field must be included in the requested `fields` array or the request returns 400.

3. **USASpending Bulk Download:** Filter structure differs from search. Requires `agencies` (with `type`, `tier`, `name`), `date_type`, `date_range`, `prime_award_types`.

4. **SAM.gov Rate Limits:** API key hit quota. Throttle response is JSON with `code`, `message`, `nextAccessTime`.

---

## Rate Limit Observations

- **USASpending:** No throttling observed. All requests completed in &lt;2s.
- **SAM.gov:** Quota exceeded. All Entity Management, Extracts, and Opportunities endpoints returned 429. Quota resets 2026-Mar-15.

---

## Recommendations

### For Daily Ingestion Pipeline

| Source | Endpoint | Use Case |
|--------|----------|----------|
| **USASpending** | `POST /api/v2/search/spending_by_award/` | Primary award search. Filter by NAICS, recipient type, date range. Paginate via `page` or `last_record_unique_id`. |
| **USASpending** | `GET /api/v2/recipient/{recipient_id}/` | Enrich recipient details (UEI, location, business types). |
| **USASpending** | `GET /api/v2/awards/{generated_internal_id}/` | Full award details when needed. |
| **SAM.gov** | Entity Management API (`/entity-information/v3/entities`) | Entity registration data, UEI lookup. **Respect rate limits.** |
| **SAM.gov** | Entity Extracts API (`/data-services/v1/extracts`) | **Baseline load.** Monthly/daily bulk files for full entity dataset. Prefer extracts over paginated API for large loads. |

### One-Time Baseline vs Daily

- **USASpending:** Use `spending_by_award` search for incremental (date-filtered) daily runs. Use `bulk_download/awards` for large historical backfills.
- **SAM.gov:** Use **Entity Extracts** (Tests 12, 13) for baseline and daily delta. Use Entity Management API only for targeted lookups (UEI, name search) to avoid quota exhaustion.
- **SAM.gov Opportunities:** Lower priority; use for solicitation discovery if needed. Same rate limits apply.

### Scripts

- **`scripts/test_usaspending_sam_apis.sh`** — Curl-based test script. Run with `doppler run -- bash scripts/test_usaspending_sam_apis.sh /tmp/output` to inject `SAM_GOV_API_KEY`.
- **`scripts/test_usaspending_sam_apis.py`** — Python/httpx version (may hang on SAM requests in some environments; curl script is more reliable).
