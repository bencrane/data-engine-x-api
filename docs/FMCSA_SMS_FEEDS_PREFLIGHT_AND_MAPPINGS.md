# FMCSA SMS Feeds Preflight And Mappings

## Contract Update

The original candidate transport contract for this batch was invalid in practice:

- every candidate `https://data.transportation.gov/download/<dataset-id>/text%2Fplain` URL returned `404`
- the dataset pages are live and expose stable CSV export URLs behind the Export button
- the plain `/resource/<dataset-id>.csv` URLs appear truncated and are not safe as the ingestion source

Per follow-up user direction, this batch uses the authoritative direct export endpoint behind the page Export button:

- `GET https://data.transportation.gov/api/views/<dataset-id>/rows.csv?accessType=DOWNLOAD`
- no auth
- no browser automation
- CSV with header row
- full source rows preserved as observed for each `feed_date`

`SMS Input - Crash` was explicitly removed from scope by user instruction before implementation and remains skipped.

## Preflight Results

| Feed | Original candidate URL result | Authoritative export URL tested | Export result | Final status | Notes |
|---|---|---|---|---|---|
| `SMS Input - Crash` | `404` on candidate `gwak-5bwn` text/plain URL | not adopted | not implemented | `skipped` | local docs were mismatched/ambiguous and the user asked to skip crash entirely |
| `SMS AB PassProperty` | `404` on `download/4y6x-dmck/text%2Fplain` | `https://data.transportation.gov/api/views/4y6x-dmck/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 21-column header | `implemented` | authoritative page title confirms `SMS AB PassProperty` |
| `SMS C PassProperty` | `404` on `download/h9zy-gjn8/text%2Fplain` | `https://data.transportation.gov/api/views/h9zy-gjn8/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 21-column header | `implemented` | authoritative page title confirms `SMS C PassProperty` |
| `SMS Input - Violation` | `404` on `download/8mt8-2mdr/text%2Fplain` | `https://data.transportation.gov/api/views/8mt8-2mdr/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 13-column header | `implemented` | local docs and live export header agree |
| `SMS Input - Inspection` | `404` on `download/rbkj-cgst/text%2Fplain` | `https://data.transportation.gov/api/views/rbkj-cgst/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 39-column header | `implemented` | local docs and live export header agree |
| `SMS Input - Motor Carrier Census` | `404` on `download/kjg3-diqy/text%2Fplain` | `https://data.transportation.gov/api/views/kjg3-diqy/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 42-column header | `implemented` | local docs and live export header agree |
| `SMS AB Pass` | `404` on `download/m3ry-qcip/text%2Fplain` | `https://data.transportation.gov/api/views/m3ry-qcip/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 36-column header | `implemented` | local docs and live export header agree |
| `SMS C Pass` | original candidate incorrectly reused `h9zy-gjn8`, which is `SMS C PassProperty` | `https://data.transportation.gov/api/views/h3zn-uid9/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable, exact 36-column header | `implemented` | authoritative live page for `SMS C Pass` is `h3zn-uid9`; local `34-sms-c-pass` docs are stale duplicate PassProperty docs and were not trusted for the contract |

## Duplicate Investigation

The original directive-level duplicate issue was real at the candidate URL layer:

- both `SMS C PassProperty` and the original `SMS C Pass` candidate pointed at `h9zy-gjn8`
- that dataset is definitively `SMS C PassProperty`

After checking the authoritative live dataset pages, `SMS C Pass` is actually a different dataset:

- `SMS C PassProperty` -> `h9zy-gjn8`
- `SMS C Pass` -> `h3zn-uid9`

So the final implementation keeps both feeds because the authoritative export files are distinct:

- `SMS C PassProperty`: 21 columns, no percentile or alert fields
- `SMS C Pass`: 36 columns, includes percentile and alert fields

## Shared Storage Semantics

All implemented SMS feeds use the same ingestion semantics:

- store every data row with `feed_date`
- preserve source-row identity as `feed_date + source_feed_name + row_position`
- preserve raw source row payload as both ordered `raw_values` and header-keyed `raw_fields`
- preserve source metadata:
  - `source_provider`
  - `source_feed_name`
  - `source_download_url`
  - `source_file_variant = csv_export`
  - `source_observed_at`
  - `source_task_id`
  - `source_schedule_id`
  - `source_run_metadata`
- no business-level deduplication at ingestion time
- same-day reruns overwrite the same source row slot
- different `feed_date` values coexist as separate observed snapshots

## Header Contracts

### PassProperty Header Contract

Expected row width: `21`

Ordered source fields:

```text
DOT_NUMBER, INSP_TOTAL, DRIVER_INSP_TOTAL, DRIVER_OOS_INSP_TOTAL, VEHICLE_INSP_TOTAL, VEHICLE_OOS_INSP_TOTAL, UNSAFE_DRIV_INSP_W_VIOL, UNSAFE_DRIV_MEASURE, UNSAFE_DRIV_AC, HOS_DRIV_INSP_W_VIOL, HOS_DRIV_MEASURE, HOS_DRIV_AC, DRIV_FIT_INSP_W_VIOL, DRIV_FIT_MEASURE, DRIV_FIT_AC, CONTR_SUBST_INSP_W_VIOL, CONTR_SUBST_MEASURE, CONTR_SUBST_AC, VEH_MAINT_INSP_W_VIOL, VEH_MAINT_MEASURE, VEH_MAINT_AC
```

### Pass Header Contract

Expected row width: `36`

Ordered source fields:

```text
DOT_NUMBER, INSP_TOTAL, DRIVER_INSP_TOTAL, DRIVER_OOS_INSP_TOTAL, VEHICLE_INSP_TOTAL, VEHICLE_OOS_INSP_TOTAL, UNSAFE_DRIV_INSP_W_VIOL, UNSAFE_DRIV_MEASURE, UNSAFE_DRIV_PCT, UNSAFE_DRIV_RD_ALERT, UNSAFE_DRIV_AC, UNSAFE_DRIV_BASIC_ALERT, HOS_DRIV_INSP_W_VIOL, HOS_DRIV_MEASURE, HOS_DRIV_PCT, HOS_DRIV_RD_ALERT, HOS_DRIV_AC, HOS_DRIV_BASIC_ALERT, DRIV_FIT_INSP_W_VIOL, DRIV_FIT_MEASURE, DRIV_FIT_PCT, DRIV_FIT_RD_ALERT, DRIV_FIT_AC, DRIV_FIT_BASIC_ALERT, CONTR_SUBST_INSP_W_VIOL, CONTR_SUBST_MEASURE, CONTR_SUBST_PCT, CONTR_SUBST_RD_ALERT, CONTR_SUBST_AC, CONTR_SUBST_BASIC_ALERT, VEH_MAINT_INSP_W_VIOL, VEH_MAINT_MEASURE, VEH_MAINT_PCT, VEH_MAINT_RD_ALERT, VEH_MAINT_AC, VEH_MAINT_BASIC_ALERT
```

### Violation Header Contract

Expected row width: `13`

Ordered source fields:

```text
Unique_ID, Insp_Date, DOT_Number, Viol_Code, BASIC_Desc, OOS_Indicator, OOS_Weight, Severity_Weight, Time_Weight, Total_Severity_Wght, Section_Desc, Group_Desc, Viol_Unit
```

### Inspection Header Contract

Expected row width: `39`

Ordered source fields:

```text
Unique_ID, Report_Number, Report_State, DOT_Number, Insp_Date, Insp_level_ID, County_code_State, Time_Weight, Driver_OOS_Total, Vehicle_OOS_Total, Total_Hazmat_Sent, OOS_Total, Hazmat_OOS_Total, Hazmat_Placard_req, Unit_Type_Desc, Unit_Make, Unit_License, Unit_License_State, VIN, Unit_Decal_Number, Unit_Type_Desc2, Unit_Make2, Unit_License2, Unit_License_State2, VIN2, Unit_Decal_Number2, Unsafe_Insp, Fatigued_Insp, Dr_Fitness_Insp, Subt_Alcohol_Insp, Vh_Maint_Insp, HM_Insp, BASIC_Viol, Unsafe_Viol, Fatigued_Viol, Dr_Fitness_Viol, Subt_Alcohol_Viol, Vh_Maint_Viol, HM_Viol
```

### Motor Carrier Census Header Contract

Expected row width: `42`

Ordered source fields:

```text
DOT_NUMBER, LEGAL_NAME, DBA_NAME, CARRIER_OPERATION, HM_FLAG, PC_FLAG, PHY_STREET, PHY_CITY, PHY_STATE, PHY_ZIP, PHY_COUNTRY, MAILING_STREET, MAILING_CITY, MAILING_STATE, MAILING_ZIP, MAILING_COUNTRY, TELEPHONE, FAX, EMAIL_ADDRESS, MCS150_DATE, MCS150_MILEAGE, MCS150_MILEAGE_YEAR, ADD_DATE, OIC_STATE, NBR_POWER_UNIT, DRIVER_TOTAL, RECENT_MILEAGE, RECENT_MILEAGE_YEAR, VMT_SOURCE_ID, PRIVATE_ONLY, AUTHORIZED_FOR_HIRE, EXEMPT_FOR_HIRE, PRIVATE_PROPERTY, PRIVATE_PASSENGER_BUSINESS, PRIVATE_PASSENGER_NONBUSINESS, MIGRANT, US_MAIL, FEDERAL_GOVERNMENT, STATE_GOVERNMENT, LOCAL_GOVERNMENT, INDIAN_TRIBE, OP_OTHER
```

## Feed Mappings

### `SMS AB PassProperty`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/22-sms-ab-passproperty/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/22-sms-ab-passproperty/overview-data-dictionary.md`
  - authoritative live page metadata for dataset `4y6x-dmck`
  - authoritative CSV export header for dataset `4y6x-dmck`
- Canonical business concept: carrier BASIC summary measures without percentile/alert columns for the AB carrier segment.
- Canonical table: `entities.carrier_safety_basic_measures`
- Typed columns:
  - `carrier_segment`, `dot_number`
  - inspection totals
  - per-BASIC violation counts
  - per-BASIC measure values
  - per-BASIC acute/critical boolean flags
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: local docs in this folder were stale and described the 36-column Pass shape; the live export header and live page metadata were used as the contract source instead.

### `SMS C PassProperty`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/23-sms-c-passproperty/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/23-sms-c-passproperty/overview-data-dictionary.md`
  - authoritative live page metadata for dataset `h9zy-gjn8`
  - authoritative CSV export header for dataset `h9zy-gjn8`
- Canonical business concept: carrier BASIC summary measures without percentile/alert columns for the intrastate non-hazmat carrier segment.
- Canonical table: `entities.carrier_safety_basic_measures`
- Typed columns: same shape as `SMS AB PassProperty`, with `carrier_segment` distinguishing the segment.
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: shares row shape with `SMS AB PassProperty`, so shared-table storage is safe and non-ambiguous.

### `SMS AB Pass`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/33-sms-ab-pass/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/33-sms-ab-pass/overview-data-dictionary.md`
  - authoritative CSV export header for dataset `m3ry-qcip`
- Canonical business concept: carrier BASIC summary measures with percentile and alert columns for the AB passenger carrier segment.
- Canonical table: `entities.carrier_safety_basic_percentiles`
- Typed columns:
  - `carrier_segment`, `dot_number`
  - inspection totals
  - per-BASIC violation counts
  - per-BASIC measure values
  - per-BASIC percentile values
  - per-BASIC roadside alert, acute/critical, and overall BASIC alert booleans
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: this is not the same concept as PassProperty because percentile and alert fields materially change downstream meaning.

### `SMS C Pass`

- Docs used:
  - authoritative live page metadata for dataset `h3zn-uid9`
  - authoritative CSV export header for dataset `h3zn-uid9`
  - local `docs/api-reference-docs/fmcsa-open-data/34-sms-c-pass/*` files as evidence of stale/mismatched repo docs only
- Canonical business concept: carrier BASIC summary measures with percentile and alert columns for the intrastate passenger carrier segment.
- Canonical table: `entities.carrier_safety_basic_percentiles`
- Typed columns: same shape as `SMS AB Pass`, with `carrier_segment` distinguishing the segment.
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: the original candidate dataset ID was wrong; the corrected authoritative live dataset is `h3zn-uid9`.

### `SMS Input - Violation`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/overview-data-dictionary.md`
  - authoritative CSV export header for dataset `8mt8-2mdr`
- Canonical business concept: row-level violations contributing to SMS calculations.
- Canonical table: `entities.carrier_inspection_violations`
- Typed columns:
  - `inspection_unique_id`, `inspection_date`, `dot_number`, `violation_code`, `basic_description`
  - `oos_indicator`, `oos_weight`, `severity_weight`, `time_weight`, `total_severity_weight`
  - `section_description`, `group_description`, `violation_unit`
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: multiple rows can legitimately share the same `inspection_unique_id`; ingestion does not collapse them.

### `SMS Input - Inspection`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/overview-data-dictionary.md`
  - authoritative CSV export header for dataset `rbkj-cgst`
- Canonical business concept: row-level inspections contributing to SMS calculations.
- Canonical table: `entities.carrier_inspections`
- Typed columns:
  - inspection identifiers, dates, and jurisdiction fields
  - OOS counts, hazmat counts, and time weight
  - primary and secondary unit vehicle identifiers
  - BASIC relevance booleans
  - BASIC violation counts
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Contract clarification: the local repo dictionary for `SMS Input - Inspection` is valid and matches the live `rbkj-cgst` CSV export header exactly at 39 columns. This feed is not one of the stale/mismatched SMS doc cases.
- Semantic caveat: this is a snapshot of current SMS input rows for the run date, not a deduplicated inspection master table.

### `SMS Input - Motor Carrier Census`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/overview-data-dictionary.md`
  - authoritative CSV export header for dataset `kjg3-diqy`
- Canonical business concept: row-level carrier census/registration source rows used by SMS.
- Canonical table: `entities.motor_carrier_census_records`
- Typed columns:
  - carrier identity and operation classification fields
  - physical and mailing addresses
  - contact info
  - MCS-150 dates and mileage fields
  - oversight, fleet, recent mileage, and operation-classification booleans
- Raw row preservation plan: preserve the full CSV row in `raw_source_row`.
- Row identity / rerun strategy: `feed_date + source_feed_name + row_position`.
- Semantic caveat: this remains observed-source storage, not a current deduplicated carrier entity model.

## Flags

- `SMS Input - Crash` remains skipped by explicit user instruction.
- The original `text/plain` URLs are not usable for this batch and were replaced with the authoritative export URLs.
- The repo’s local `22-sms-ab-passproperty` docs are stale and describe the Pass shape, not the live PassProperty header.
- The repo’s local `34-sms-c-pass` docs are stale duplicate PassProperty docs; the authoritative live `SMS C Pass` dataset is `h3zn-uid9`.
- `/resource/<dataset-id>.csv` should not be used for ingestion because it appears to return a truncated subset rather than the full export.
