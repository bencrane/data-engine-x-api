# FMCSA Remaining CSV Export Feeds Preflight And Mappings

## Transport Contract

This batch uses the FMCSA CSV export endpoint class:

- `GET https://data.transportation.gov/api/views/<dataset-id>/rows.csv?accessType=DOWNLOAD`
- no auth
- header-row CSV
- full source-row preservation per `feed_date`
- same-feed-date reruns remain idempotent at `feed_date + source_feed_name + row_position`

Preflight was run against the live export URLs in streamed mode so large files could be validated without requiring the entire file to be buffered in memory. Each check confirmed:

- HTTP `200`
- non-empty body
- `text/csv` content
- not HTML
- header row present
- first parsed data row matches the expected dictionary width

No requested feed failed preflight, so no feed is skipped for this batch.

## Shared Storage Semantics

All implemented feeds use the same ingestion semantics:

- store every observed source row with `feed_date`
- preserve row identity as `feed_date + source_feed_name + row_position`
- preserve raw row payload as:
  - ordered `raw_values`
  - contract-keyed `raw_fields`
- preserve source metadata:
  - `source_provider`
  - `source_feed_name`
  - `source_download_url`
  - `source_file_variant`
  - `source_observed_at`
  - `source_task_id`
  - `source_schedule_id`
  - `source_run_metadata`
- do not perform business-level deduplication at ingestion time
- allow different `feed_date` snapshots of the same business row to coexist

## Preflight Results

| Feed | Dataset ID | URL tested | Result | Final status | Header contract result | Notes |
|---|---|---|---|---|---|---|
| `Crash File` | `aayw-vxb3` | `https://data.transportation.gov/api/views/aayw-vxb3/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 59-column header and first row width 59 | header exactly matches dictionary field names |
| `Carrier - All With History` | `6eyk-hxee` | `https://data.transportation.gov/api/views/6eyk-hxee/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 43-column header and first row width 43 | header uses Socrata/export aliases, so explicit index mapping is required |
| `Inspections Per Unit` | `wt8s-2hbx` | `https://data.transportation.gov/api/views/wt8s-2hbx/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 12-column header and first row width 12 | header exactly matches dictionary field names |
| `Special Studies` | `5qik-smay` | `https://data.transportation.gov/api/views/5qik-smay/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 5-column header and first row width 5 | header exactly matches dictionary field names |
| `Revocation - All With History` | `sa6p-acbp` | `https://data.transportation.gov/api/views/sa6p-acbp/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 6-column header and first row width 6 | header uses export aliases, so explicit index mapping is required |
| `Insur - All With History` | `ypjt-5ydn` | `https://data.transportation.gov/api/views/ypjt-5ydn/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 9-column header and first row width 9 | header uses export aliases, so explicit index mapping is required |
| `OUT OF SERVICE ORDERS` | `p2mt-9ige` | `https://data.transportation.gov/api/views/p2mt-9ige/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 7-column header and first row width 7 | one header name differs from the dictionary and requires explicit mapping |
| `Inspections and Citations` | `qbt8-7vic` | `https://data.transportation.gov/api/views/qbt8-7vic/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 6-column header and first row width 6 | header exactly matches dictionary field names |
| `Vehicle Inspections and Violations` | `876r-jsdb` | `https://data.transportation.gov/api/views/876r-jsdb/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 12-column header and first row width 12 | header exactly matches dictionary field names |
| `Company Census File` | `az4n-8mr2` | `https://data.transportation.gov/api/views/az4n-8mr2/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 147-column header and first row width 147 | large file; streaming parse and chunked writes required |
| `Vehicle Inspection File` | `fx4q-ay7w` | `https://data.transportation.gov/api/views/fx4q-ay7w/rows.csv?accessType=DOWNLOAD` | `200`, `text/csv`, non-empty, parseable | `implemented` | exact 63-column header and first row width 63 | large file; streaming parse and chunked writes required |

## Header Contracts

### `Crash File`

- Expected row width excluding header: `59`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, CRASH_ID, REPORT_STATE, REPORT_NUMBER, REPORT_DATE, REPORT_TIME, REPORT_SEQ_NO, DOT_NUMBER, CI_STATUS_CODE, FINAL_STATUS_DATE, LOCATION, CITY_CODE, CITY, STATE, COUNTY_CODE, TRUCK_BUS_IND, TRAFFICWAY_ID, ACCESS_CONTROL_ID, ROAD_SURFACE_CONDITION_ID, CARGO_BODY_TYPE_ID, GVW_RATING_ID, VEHICLE_IDENTIFICATION_NUMBER, VEHICLE_LICENSE_NUMBER, VEHICLE_LIC_STATE, VEHICLE_HAZMAT_PLACARD, WEATHER_CONDITION_ID, VEHICLE_CONFIGURATION_ID, LIGHT_CONDITION_ID, HAZMAT_RELEASED, AGENCY, VEHICLES_IN_ACCIDENT, FATALITIES, INJURIES, TOW_AWAY, FEDERAL_RECORDABLE, STATE_RECORDABLE, SNET_VERSION_NUMBER, SNET_SEQUENCE_ID, TRANSACTION_CODE, TRANSACTION_DATE, UPLOAD_FIRST_BYTE, UPLOAD_DOT_NUMBER, UPLOAD_SEARCH_INDICATOR, UPLOAD_DATE, ADD_DATE, CRASH_CARRIER_ID, CRASH_CARRIER_NAME, CRASH_CARRIER_STREET, CRASH_CARRIER_CITY, CRASH_CARRIER_CITY_CODE, CRASH_CARRIER_STATE, CRASH_CARRIER_ZIP_CODE, CRASH_COLONIA, DOCKET_NUMBER, CRASH_CARRIER_INTERSTATE, NO_ID_FLAG, STATE_NUMBER, STATE_ISSUING_NUMBER, CRASH_EVENT_SEQ_ID_DESC
```

### `Carrier - All With History`

- Expected row width excluding header: `43`
- Header alignment: explicit column-index mapping required
- Ordered dictionary fields:

```text
Docket Number, USDOT Number, MX Type, RFC Number, Common Authority, Contract Authority, Broker Authority, Pending Common Authority, Pending Contract Authority, Pending Broker Authority, Common Authority Revocation, Contract Authority Revocation, Broker Authority Revocation, Property, Passenger, Household Goods, Private Check, Enterprise Check, BIPD Required, Cargo Required, Bond/Surety Required, BIPD on File, Cargo on File, Bond/Surety on File, Address Status, DBA Name, Legal Name, Business Address - PO Box/Street, Business Address - Colonia, Business Address - City, Business Address - State Code, Business Address - Country Code, Business Address - Zip Code, Business Address - Telephone Number, Business Address - Fax Number, Mailing Address - PO Box/Street, Mailing Address - Colonia, Mailing Address - City, Mailing Address - State Code, Mailing Address - Country Code, Mailing Address - Zip Code, Mailing Address - Telephone Number, Mailing Address - Fax Number
```

- Live header order:

```text
DOCKET_NUMBER, DOT_NUMBER, MX_TYPE, RFC_NUMBER, COMMON_STAT, CONTRACT_STAT, BROKER_STAT, COMMON_APP_PEND, CONTRACT_APP_PEND, BROKER_APP_PEND, COMMON_REV_PEND, CONTRACT_REV_PEND, BROKER_REV_PEND, PROPERTY_CHK, PASSENGER_CHK, HHG_CHK, PRIVATE_AUTH_CHK, ENTERPRISE_CHK, MIN_COV_AMOUNT, CARGO_REQ, BOND_REQ, BIPD_FILE, CARGO_FILE, BOND_FILE, UNDELIVERABLE_MAIL, DBA_NAME, LEGAL_NAME, BUS_STREET_PO, BUS_COLONIA, BUS_CITY, BUS_STATE_CODE, BUS_CTRY_CODE, BUS_ZIP_CODE, BUS_TELNO, BUS_FAX, MAIL_STREET_PO, MAIL_COLONIA, MAIL_CITY, MAIL_STATE_CODE, MAIL_CTRY_CODE, MAIL_ZIP_CODE, MAIL_TELNO, MAIL_FAX
```

### `Inspections Per Unit`

- Expected row width excluding header: `12`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, INSPECTION_ID, INSP_UNIT_ID, INSP_UNIT_TYPE_ID, INSP_UNIT_NUMBER, INSP_UNIT_MAKE, INSP_UNIT_COMPANY, INSP_UNIT_LICENSE, INSP_UNIT_LICENSE_STATE, INSP_UNIT_VEHICLE_ID_NUMBER, INSP_UNIT_DECAL, INSP_UNIT_DECAL_NUMBER
```

### `Special Studies`

- Expected row width excluding header: `5`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, INSPECTION_ID, INSP_STUDY_ID, STUDY, SEQ_NO
```

### `Revocation - All With History`

- Expected row width excluding header: `6`
- Header alignment: explicit column-index mapping required
- Ordered dictionary fields:

```text
Docket Number, USDOT Number, Operating Authority Registration Type, Serve Date, Revocation Type, Effective Date
```

- Live header order:

```text
DOCKET_NUMBER, DOT_NUMBER, TYPE_LICENSE, ORDER1_SERVE_DATE, ORDER2_TYPE_DESC, order2_effective_Date
```

### `Insur - All With History`

- Expected row width excluding header: `9`
- Header alignment: explicit column-index mapping required
- Ordered dictionary fields:

```text
Docket Number, Insurance Type, BI&PD Class, BI&PD Maximum Dollar Limit, BI&PD Underlying Dollar Limit, Policy Number, Effective Date, Form Code, Insurance Company Name
```

- Live header order:

```text
prefix_docket_number, ins_type_code, ins_class_code, max_cov_amount, underl_lim_amount, policy_no, effective_date, ins_form_code, name_company
```

### `OUT OF SERVICE ORDERS`

- Expected row width excluding header: `7`
- Header alignment: explicit column-index mapping required
- Ordered dictionary fields:

```text
DOT_NUMBER, LEGAL_NAME, DBA_NAME, OOS_DATE, OOS_REASON, STATUS, OOS_RESCIND_DATE
```

- Live header order:

```text
DOT_NUMBER, LEGAL_NAME, DBA_NAME, OOS_DATE, OOS_REASON, STATUS, RESCIND_DATE
```

### `Inspections and Citations`

- Expected row width excluding header: `6`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, INSPECTION_ID, VIOSEQNUM, ADJSEQ, CITATION_CODE, CITATION_RESULT
```

### `Vehicle Inspections and Violations`

- Expected row width excluding header: `12`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, INSPECTION_ID, INSP_VIOLATION_ID, SEQ_NO, PART_NO, PART_NO_SECTION, INSP_VIOL_UNIT, INSP_UNIT_ID, INSP_VIOLATION_CATEGORY_ID, OUT_OF_SERVICE_INDICATOR, DEFECT_VERIFICATION_ID, CITATION_NUMBER
```

### `Company Census File`

- Expected row width excluding header: `147`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
MCS150_DATE, ADD_DATE, STATUS_CODE, DOT_NUMBER, DUN_BRADSTREET_NO, PHY_OMC_REGION, SAFETY_INV_TERR, CARRIER_OPERATION, BUSINESS_ORG_ID, MCS150_MILEAGE, MCS150_MILEAGE_YEAR, MCS151_MILEAGE, TOTAL_CARS, MCS150_UPDATE_CODE_ID, PRIOR_REVOKE_FLAG, PRIOR_REVOKE_DOT_NUMBER, PHONE, FAX, CELL_PHONE, COMPANY_OFFICER_1, COMPANY_OFFICER_2, BUSINESS_ORG_DESC, TRUCK_UNITS, POWER_UNITS, BUS_UNITS, FLEETSIZE, REVIEW_ID, RECORDABLE_CRASH_RATE, MAIL_NATIONALITY_INDICATOR, PHY_NATIONALITY_INDICATOR, PHY_BARRIO, MAIL_BARRIO, CARSHIP, DOCKET1PREFIX, DOCKET1, DOCKET2PREFIX, DOCKET2, DOCKET3PREFIX, DOCKET3, POINTNUM, TOTAL_INTRASTATE_DRIVERS, MCSIPSTEP, MCSIPDATE, HM_Ind, INTERSTATE_BEYOND_100_MILES, INTERSTATE_WITHIN_100_MILES, INTRASTATE_BEYOND_100_MILES, INTRASTATE_WITHIN_100_MILES, TOTAL_CDL, TOTAL_DRIVERS, AVG_DRIVERS_LEASED_PER_MONTH, CLASSDEF, LEGAL_NAME, DBA_NAME, PHY_STREET, PHY_CITY, PHY_COUNTRY, PHY_STATE, PHY_ZIP, PHY_CNTY, CARRIER_MAILING_STREET, CARRIER_MAILING_STATE, CARRIER_MAILING_CITY, CARRIER_MAILING_COUNTRY, CARRIER_MAILING_ZIP, CARRIER_MAILING_CNTY, CARRIER_MAILING_UND_DATE, DRIVER_INTER_TOTAL, EMAIL_ADDRESS, REVIEW_TYPE, REVIEW_DATE, SAFETY_RATING, SAFETY_RATING_DATE, UNDELIV_PHY, CRGO_GENFREIGHT, CRGO_HOUSEHOLD, CRGO_METALSHEET, CRGO_MOTOVEH, CRGO_DRIVETOW, CRGO_LOGPOLE, CRGO_BLDGMAT, CRGO_MOBILEHOME, CRGO_MACHLRG, CRGO_PRODUCE, CRGO_LIQGAS, CRGO_INTERMODAL, CRGO_PASSENGERS, CRGO_OILFIELD, CRGO_LIVESTOCK, CRGO_GRAINFEED, CRGO_COALCOKE, CRGO_MEAT, CRGO_GARBAGE, CRGO_USMAIL, CRGO_CHEM, CRGO_DRYBULK, CRGO_COLDFOOD, CRGO_BEVERAGES, CRGO_PAPERPROD, CRGO_UTILITY, CRGO_FARMSUPP, CRGO_CONSTRUCT, CRGO_WATERWELL, CRGO_CARGOOTHR, CRGO_CARGOOTHR_DESC, OWNTRUCK, OWNTRACT, OWNTRAIL, OWNCOACH, OWNSCHOOL_1_8, OWNSCHOOL_9_15, OWNSCHOOL_16, OWNBUS_16, OWNVAN_1_8, OWNVAN_9_15, OWNLIMO_1_8, OWNLIMO_9_15, OWNLIMO_16, TRMTRUCK, TRMTRACT, TRMTRAIL, TRMCOACH, TRMSCHOOL_1_8, TRMSCHOOL_9_15, TRMSCHOOL_16, TRMBUS_16, TRMVAN_1_8, TRMVAN_9_15, TRMLIMO_1_8, TRMLIMO_9_15, TRMLIMO_16, TRPTRUCK, TRPTRACT, TRPTRAIL, TRPCOACH, TRPSCHOOL_1_8, TRPSCHOOL_9_15, TRPSCHOOL_16, TRPBUS_16, TRPVAN_1_8, TRPVAN_9_15, TRPLIMO_1_8, TRPLIMO_9_15, TRPLIMO_16, DOCKET1_STATUS_CODE, DOCKET2_STATUS_CODE, DOCKET3_STATUS_CODE
```

### `Vehicle Inspection File`

- Expected row width excluding header: `63`
- Header alignment: exact match to the dictionary contract
- Ordered source fields:

```text
CHANGE_DATE, INSPECTION_ID, DOT_NUMBER, REPORT_STATE, REPORT_NUMBER, INSP_DATE, INSP_START_TIME, INSP_END_TIME, REGISTRATION_DATE, REGION, CI_STATUS_CODE, LOCATION, LOCATION_DESC, COUNTY_CODE_STATE, COUNTY_CODE, INSP_LEVEL_ID, SERVICE_CENTER, CENSUS_SOURCE_ID, INSP_FACILITY, SHIPPER_NAME, SHIPPING_PAPER_NUMBER, CARGO_TANK, HAZMAT_PLACARD_REQ, SNET_VERSION_NUMBER, SNET_SEARCH_DATE, ALCOHOL_CONTROL_SUB, DRUG_INTRDCTN_SEARCH, DRUG_INTRDCTN_ARRESTS, SIZE_WEIGHT_ENF, TRAFFIC_ENF, LOCAL_ENF_JURISDICTION, PEN_CEN_MATCH, FINAL_STATUS_DATE, POST_ACC_IND, GROSS_COMB_VEH_WT, VIOL_TOTAL, OOS_TOTAL, DRIVER_VIOL_TOTAL, DRIVER_OOS_TOTAL, VEHICLE_VIOL_TOTAL, VEHICLE_OOS_TOTAL, HAZMAT_VIOL_TOTAL, HAZMAT_OOS_TOTAL, SNET_SEQUENCE_ID, TRANSACTION_CODE, TRANSACTION_DATE, UPLOAD_DATE, UPLOAD_FIRST_BYTE, UPLOAD_DOT_NUMBER, UPLOAD_SEARCH_INDICATOR, CENSUS_SEARCH_DATE, SNET_INPUT_DATE, SOURCE_OFFICE, MCMIS_ADD_DATE, INSP_CARRIER_NAME, INSP_CARRIER_STREET, INSP_CARRIER_CITY, INSP_CARRIER_STATE, INSP_CARRIER_ZIP_CODE, INSP_COLONIA, DOCKET_NUMBER, INSP_INTERSTATE, INSP_CARRIER_STATE_ID
```

## Feed Mappings

### `Crash File`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/27-crash-file/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/27-crash-file/overview-data-dictionary.md`
- Canonical business concept: commercial motor vehicle crash records with attached carrier-identification fields.
- Canonical table: `entities.commercial_vehicle_crashes`
- Shared existing table or new table: new table.
- Why separation is required: no existing table models crash-level FMCSA history data.
- Typed columns:
  - crash identifiers and timing fields
  - reporting geography
  - vehicle configuration and road-condition fields
  - severity counts
  - carrier-identification and carrier-address fields
  - transaction/upload metadata
- Raw source row preservation plan: preserve the full CSV row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Carrier - All With History`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/28-carrier-all-with-history/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/04-carrier-daily-diff/data-dictionary.json`
- Canonical business concept: carrier/broker/freight-forwarder registration and authority snapshot rows.
- Canonical table: `entities.carrier_registrations`
- Shared existing table or new table: shared existing table.
- Why shared-table storage is safe: the all-history dictionary is the same 43-field registration/authority/address contract as the daily carrier feed; only the export header names differ.
- Typed columns:
  - entity identifiers
  - authority status and pending/revocation flags
  - insurance-required and insurance-on-file summary fields
  - legal/DBA names
  - business and mailing addresses
- Raw source row preservation plan: preserve full row in `raw_source_row`; distinguish daily versus all-history via `source_feed_name` and `source_file_variant`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Inspections Per Unit`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/29-inspections-per-unit/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/29-inspections-per-unit/overview-data-dictionary.md`
- Canonical business concept: inspected vehicle units attached to a vehicle inspection.
- Canonical table: `entities.vehicle_inspection_units`
- Shared existing table or new table: new table.
- Why separation is required: these rows represent unit-level children of inspection headers and do not fit any existing table.
- Typed columns:
  - change timestamp
  - `inspection_id`, `insp_unit_id`
  - unit type, sequence, make, company/unit number
  - license, VIN, decal fields
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Special Studies`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/30-special-studies/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/30-special-studies/overview-data-dictionary.md`
- Canonical business concept: special-study observations attached to a vehicle inspection.
- Canonical table: `entities.vehicle_inspection_special_studies`
- Shared existing table or new table: new table.
- Why separation is required: these are inspection-child study rows with no compatible existing table.
- Typed columns:
  - change timestamp
  - `inspection_id`, `insp_study_id`
  - `study`
  - `seq_no`
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Revocation - All With History`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/31-revocation-all-with-history/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/02-revocation-daily-diff/data-dictionary.json`
- Canonical business concept: operating-authority revocation rows.
- Canonical table: `entities.operating_authority_revocations`
- Shared existing table or new table: shared existing table.
- Why shared-table storage is safe: the all-history feed carries the same six business fields and the same revocation semantics as the daily feed; only the live header aliases differ.
- Typed columns:
  - entity identifiers
  - authority registration type
  - serve date
  - revocation type
  - effective date
- Raw source row preservation plan: preserve full row in `raw_source_row`; distinguish variants with source metadata.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Insur - All With History`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/32-insur-all-with-history/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/03-insurance-daily-diff/data-dictionary.json`
- Canonical business concept: active or pending insurance policy inventory rows.
- Canonical table: `entities.insurance_policies`
- Shared existing table or new table: shared existing table.
- Why shared-table storage is safe: the all-history feed carries the same nine business fields and policy semantics as the daily insurance feed; the daily feed’s blank removal rows are an extra variant-specific case already modeled via `is_removal_signal`.
- Typed columns:
  - docket number
  - insurance type and BI&PD class
  - BI&PD maximum and underlying limits
  - policy number
  - effective date
  - form code
  - insurance company name
  - removal-signal columns remain present but are only populated for daily-diff blank rows
- Raw source row preservation plan: preserve full row in `raw_source_row`; distinguish variants with source metadata.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `OUT OF SERVICE ORDERS`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/18-out-of-service-orders/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/18-out-of-service-orders/overview-data-dictionary.md`
- Canonical business concept: FMCSA out-of-service orders for regulated entities.
- Canonical table: `entities.out_of_service_orders`
- Shared existing table or new table: new table.
- Why separation is required: no existing table models OOS-order lifecycle rows.
- Typed columns:
  - `dot_number`
  - `legal_name`, `dba_name`
  - `oos_date`
  - `oos_reason`
  - `status`
  - `oos_rescind_date`
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Inspections and Citations`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/19-inspections-and-citations/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/19-inspections-and-citations/overview-data-dictionary.md`
- Canonical business concept: citation outcomes attached to inspection violations.
- Canonical table: `entities.vehicle_inspection_citations`
- Shared existing table or new table: new table.
- Why separation is required: these are citation-child rows, not inspection headers or violation rows.
- Typed columns:
  - change timestamp
  - `inspection_id`
  - `vioseqnum`, `adjseq`
  - `citation_code`
  - `citation_result`
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Vehicle Inspections and Violations`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/20-vehicle-inspections-and-violations/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/20-vehicle-inspections-and-violations/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/24-sms-input-violation/data-dictionary.json`
- Canonical business concept: row-level inspection violations.
- Canonical table: `entities.carrier_inspection_violations`
- Shared existing table or new table: shared existing table.
- Why shared-table storage is safe: both the existing SMS violation feed and this file represent violation rows tied to inspections; overlapping typed columns such as identifiers and OOS signal retain the same meaning, while source-specific fields remain nullable and are disambiguated by source metadata.
- Why a separate source contract is still required: the MCMIS file carries `inspection_id`, `insp_violation_id`, part/section codes, category IDs, and citation numbers that are not present in the SMS violation export.
- Typed columns:
  - shared inspection/violation identifiers
  - date and `dot_number`
  - source-specific violation code and description columns
  - OOS indicator and weighting fields
  - MCMIS part, section, unit, category, defect-verification, and citation fields
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: buffered parsing is acceptable for this feed.

### `Company Census File`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/01-company-census-file/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/26-sms-input-motor-carrier-census-information/data-dictionary.json`
- Canonical business concept: observed motor-carrier census snapshot rows.
- Canonical table: `entities.motor_carrier_census_records`
- Shared existing table or new table: shared existing table with additive columns.
- Why shared-table storage is safe: the SMS census feed and Company Census File are the same carrier-census concept at different contract breadths; shared storage remains non-ambiguous because rows are source-oriented and source metadata already distinguishes the SMS subset from the full census export.
- Why additive extension is required: the Company Census File introduces a much larger field set including officer info, classification text, equipment counts, cargo flags, review/rating fields, and docket-status fields that do not exist in the SMS subset.
- Typed columns:
  - identity, status, operation, organization, mileage, and fleet-size fields
  - carrier contact, officer, legal/DBA, and physical/mailing address fields
  - driver counts and equipment counts
  - review, safety-rating, and docket-status fields
  - cargo flags and cargo-other text
  - existing SMS census fields remain in the shared table
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: streamed download, streamed header-row CSV parse, and chunked confirmed writes. This feed should not require the entire file in memory at once.

### `Vehicle Inspection File`

- Docs used:
  - `docs/api-reference-docs/fmcsa-open-data/05-vehicle-introspection-file-daily-diff/data-dictionary.json`
  - `docs/api-reference-docs/fmcsa-open-data/05-vehicle-introspection-file-daily-diff/overview-data-dictionary.md`
  - `docs/api-reference-docs/fmcsa-open-data/25-sms-input-inspection/data-dictionary.json`
- Canonical business concept: row-level inspection header records.
- Canonical table: `entities.carrier_inspections`
- Shared existing table or new table: shared existing table with additive columns.
- Why shared-table storage is safe: both the existing SMS inspection feed and this file represent inspection rows. Shared source metadata keeps the SMS scoring-oriented rows distinct from the richer MCMIS inspection-header rows.
- Why additive extension is required: the Vehicle Inspection File adds inspection lifecycle timestamps, facility/process metadata, transaction/upload metadata, shipper data, violation totals, carrier-address fields, and interstate flags that are not present in the SMS subset.
- Typed columns:
  - shared inspection identifiers, `dot_number`, dates, and report fields
  - inspection timing and registration fields
  - region, service-center, facility, and census-source fields
  - placard/search/enforcement indicators
  - violation and OOS totals
  - transaction/upload timestamps and upload identifiers
  - carrier-address and carrier-state-id fields
  - existing SMS inspection fields remain in the shared table
- Raw source row preservation plan: preserve full row in `raw_source_row`.
- Required source metadata columns: all shared FMCSA metadata fields plus `feed_date`.
- Row identity / rerun idempotency: `feed_date + source_feed_name + row_position`.
- Large-file handling decision: streamed download, streamed header-row CSV parse, and chunked confirmed writes. This feed should not require the entire file in memory at once.

## Flags

- No requested feed was skipped in this batch because every URL passed preflight.
- `Carrier - All With History`, `Revocation - All With History`, and `Insur - All With History` all safely share their daily-counterpart tables because the dictionary structures and row semantics match.
- The live export headers for `Carrier - All With History`, `Revocation - All With History`, `Insur - All With History`, and `OUT OF SERVICE ORDERS` do not exactly match the dictionary field names, so those feeds must use explicit header-to-contract index mapping instead of assuming header names are canonical.
- `Company Census File` and `Vehicle Inspection File` are treated as large-file feeds and require streaming parse plus chunked confirmed writes.
