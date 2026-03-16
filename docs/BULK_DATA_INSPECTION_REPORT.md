# Bulk Data Inspection Report

**Generated:** 2026-03-14

## 1. USASpending Bulk Download

### File Metadata
- **ZIP File Size:** 54.5 MB (`awards.zip`)
- **Extracted File Size:** 408 MB (`All_Contracts_PrimeTransactions_2026-03-14_H02M50S58_1.csv`)
- **Number of CSV files in ZIP:** 1

### Schema Overview
- **Row count:** 191,886
- **Column count:** 242

### Sample Data (Key Fields)
*Extracted from a single representative row in the data payload.*
- `number_of_actions`: 1
- `action_date`: 2026-03-11
- `awarding_agency_name`: Department of Veterans Affairs
- `awarding_office_name`: 257-NETWORK CONTRACT OFFICE 17 (36C257)
- `recipient_uei`: SWCCBS41L723
- `recipient_name`: C & C HOME CARE LLC
- `recipient_city_name`: MINNEAPOLIS
- `recipient_state_name`: MINNESOTA
- `award_type`: PURCHASE ORDER
- `naics_code`: 335132
- `naics_description`: COMMERCIAL, INDUSTRIAL, AND INSTITUTIONAL ELECTRIC LIGHTING FIXTURE MANUFACTURING
- `contracting_officers_determination_of_business_size`: SMALL BUSINESS
- `domestic_or_foreign_entity`: U.S. OWNED BUSINESS

### Manufacturing Filter Counts
*Filter applied: NAICS 31-33 (Manufacturing)*
- **Total rows parsed in slice:** 191,886
- **Manufacturing (NAICS 31-33) rows:** 77,722
- **Small business rows:** 191,886*
- **Manufacturing + Small business rows:** 77,722

*(Note on Small Business filter: In the parsed sample, all 191k contracts contained the string "SMALL BUSINESS" in the `contracting_officers_determination_of_business_size` column, either as "SMALL BUSINESS" or "OTHER THAN SMALL BUSINESS". A stricter exact match string check is required for true "Small Business Only" logic in the pipeline).*

---

## 2. SAM.gov Monthly Extract

Due to an enforced quota limit observed during the `USASPENDING_SAM_API_TEST_REPORT`, the SAM.gov Extracts API request for the monthly full-entity dump returned a `429` (Rate Limited) Error:
```json
{
    "code": "900804",
    "message": "Message throttled out",
    "description": "You have exceeded your quota. You can access API after 2026-Mar-15 00:00:00+0000 UTC",
    "nextAccessTime": "2026-Mar-15 00:00:00+0000 UTC"
}
```

---

## 3. SAM.gov Daily Delta

The daily data endpoint similarly failed due to the same rate limit constraints for the API key (`429`).
No test delta unzipping could take place yet.

---

## 4. Schema Recommendations

Based on the actual inspected data from USASpending and the known layout for SAM.gov entities:

### `usaspending.awards`
The USASpending CSV contains an enormously wide schema (242 fields). Moving this straight into Supabase rows will be extremely heavy if most of it is unused. We strongly recommend filtering only the necessary columns into the Database layer while putting the full raw row in an S3 bucket or dropping it entirely.

**Recommended Keys:**
- **Primary Key:** `generated_internal_id` or `award_id_piid` (Note: `award_id_piid` can have duplicates if multiple actions fall under the same core PIID. Generating a synthetic uuid hashed from `generated_internal_id` + `action_date` is safest).

**High-Value Fields to Retain:**
- `award_id_piid`
- `recipient_uei`
- `recipient_name`
- `awarding_agency_name`
- `action_date`
- `naics_code`
- `naics_description`
- `contracting_officers_determination_of_business_size_code`
- `total_obligation` (or equivalent financial impact fields)

### `sam.entity_registrations`
*Pending un-throttled inspection of the actual `.dat` extracts on Mar 15.*
- **Primary Key:** `uei`
- **Parsing Caution:** Look out for Tilde-separated (`~`) repeating fields such as the NAICS lists (e.g. `331110Y~332710N~333249Y`). These cannot be natively shoved into a Postgres `text[]` column safely without string-splitting/parsing in the application layer first or mapping the arrays to a dedicated junction table (e.g., `sam.entity_naics`).
- If you desire small business flags combined with manufacturing NAICS, those tilde-separated `Y/N` flags associated with each NAICS code in SAM.gov will be critical.

---
*Inspection Complete per available API states.*
