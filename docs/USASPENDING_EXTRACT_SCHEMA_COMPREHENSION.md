# USASpending.gov Bulk Download Schema Comprehension

**Date:** 2026-03-16
**Sources read:**
- `FY2026_All_Contracts_Full_20260307_1.csv` (first 50+ data rows inspected, full row count confirmed)
- `FY2026_All_Contracts_Full_20260307_2.csv` (row count confirmed)
- `FY(All)_All_Contracts_Delta_20260308_1.csv` (header and sample rows inspected)
- `GET /api/v2/references/data_dictionary/` — official field definitions (457 entries, 288 contract-related)
- USASpending API documentation in `api-reference-docs-new/usa-spending.gov/`
- `docs/USASPENDING_SAM_API_TEST_REPORT.md` — prior API test report
- `docs/BULK_DATA_INSPECTION_REPORT.md` — prior bulk download inspection

---

## 1. File Format Details

| Property | Value |
|---|---|
| File type | CSV |
| Encoding | ASCII (no BOM, no non-ASCII bytes observed in first 100KB) |
| Delimiter | Comma (`,`) |
| Quote character | Double-quote (`"`) — standard RFC 4180 CSV quoting |
| Header row | **Yes** — first line contains column names (unlike SAM.gov pipe-delimited files) |
| Total columns (full) | **297** |
| Total columns (delta) | **299** (297 + 2 delta-only columns prepended) |
| Line terminator | Newline |
| Compression | ZIP |

### File Naming Conventions

**Full downloads:**
```
FY{year}_All_Contracts_Full_{generation_date}_{part_number}.csv
```
Example: `FY2026_All_Contracts_Full_20260307_1.csv`

**Delta downloads:**
```
FY(All)_All_Contracts_Delta_{generation_date}_{part_number}.csv
```
Example: `FY(All)_All_Contracts_Delta_20260308_1.csv`

### Multi-File Splits

Both full and delta downloads split across multiple CSV files:
- **FY2026 Full:** 2 CSV files — `_1.csv` (2.1 GB, 1,000,000 data rows) + `_2.csv` (725 MB, 340,862 data rows)
- **All-FY Delta:** 3 CSV files — `_1.csv` (2.4 GB) + `_2.csv` (2.5 GB) + `_3.csv` (643 MB)

Each file has its own header row. Same schema per file — just row pagination (first file capped at 1,000,000 rows).

### File Sizes

| Download | Files | Total Size |
|---|---|---|
| FY2026 Full | 2 CSVs | ~2.8 GB |
| All-FY Delta | 3 CSVs | ~5.5 GB |

---

## 2. Complete Field Map (All 297 Columns)

### Award Identification (Columns 1–9)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 1 | `contract_transaction_unique_key` | TEXT | System-generated unique key per transaction row. Concatenation of agencyID, Referenced IDV Agency ID, PIID, modification number, parent award ID, and transaction number, underscore-delimited. `-NONE-` used for blank components. | `8900_-NONE-_89303020DMA000020_P00010_-NONE-_-NONE-` |
| 2 | `contract_award_unique_key` | TEXT | Groups all transactions under one award. Format: `CONT_AWD_{piid}_{agency}_{parent_piid}_{parent_agency}` for awards, `CONT_IDV_{piid}_{agency}` for IDVs. | `CONT_IDV_89303020DMA000020_8900` |
| 3 | `award_id_piid` | TEXT | Procurement Instrument Identifier — the human-readable award ID. | `89303020DMA000020` |
| 4 | `modification_number` | TEXT | Identifier of the specific modification/action on the award. `0` for initial award. | `P00010` |
| 5 | `transaction_number` | TEXT | Transaction sequence number within the modification. Always `0` in observed data. | `0` |
| 6 | `parent_award_agency_id` | TEXT | Agency code of the parent IDV (if this is a child order). Empty for standalone awards/IDVs. | `8900` |
| 7 | `parent_award_agency_name` | TEXT | Name of the parent award agency. | `Department of Energy` |
| 8 | `parent_award_id_piid` | TEXT | PIID of the parent IDV contract. | `NNG15SD00B` |
| 9 | `parent_award_modification_number` | TEXT | Modification number of the parent award. | `0` |

### Dollar Amounts (Columns 10–21)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 10 | `federal_action_obligation` | DECIMAL | **Incremental** dollar amount for this specific action. Can be $0.00 (admin changes), negative (deobligations like `-387.25`). | `268432.70` |
| 11 | `total_dollars_obligated` | DECIMAL | **Cumulative** total obligation for the award as of this action. | `771498.30` |
| 12 | `total_outlayed_amount_for_overall_award` | DECIMAL | Total outlays (actual payments) for the overall award. Often empty. | `7038292.30` |
| 13 | `base_and_exercised_options_value` | DECIMAL | Contract value for base + exercised options. Empty for IDVs. | `268432.70` |
| 14 | `current_total_value_of_award` | DECIMAL | Total amount obligated to date including base and exercised options. | `771498.30` |
| 15 | `base_and_all_options_value` | DECIMAL | Mutually agreed total value including ALL options (exercised or not). For IDVs, includes estimated value of all potential orders. | `0.00` |
| 16 | `potential_total_value_of_award` | DECIMAL | Maximum potential value if base and all options are exercised — the contract ceiling. | `60000000.00` |
| 17 | `disaster_emergency_fund_codes_for_overall_award` | TEXT | Semicolon-delimited list of DEFC codes with descriptions. | `AAC: Wildfire Suppression P.L. 117-328;Q: Not Designated...` |
| 18 | `outlayed_amount_from_COVID-19_supplementals_for_overall_award` | DECIMAL | COVID-19 supplemental outlays. Usually empty. | `` |
| 19 | `obligated_amount_from_COVID-19_supplementals_for_overall_award` | DECIMAL | COVID-19 supplemental obligations. Usually empty. | `` |
| 20 | `outlayed_amount_from_IIJA_supplemental_for_overall_award` | DECIMAL | IIJA (Infrastructure) supplemental outlays. Usually empty. | `` |
| 21 | `obligated_amount_from_IIJA_supplemental_for_overall_award` | DECIMAL | IIJA supplemental obligations. Usually empty. | `` |

### Dates (Columns 22–28)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 22 | `action_date` | DATE | Date the action was issued/signed. Format: `YYYY-MM-DD`. | `2025-11-03` |
| 23 | `action_date_fiscal_year` | INTEGER | Federal fiscal year (Oct–Sep) in which the action date falls. | `2026` |
| 24 | `period_of_performance_start_date` | DATE | Contract performance start date. Format: `YYYY-MM-DD`. | `2020-07-24` |
| 25 | `period_of_performance_current_end_date` | DATE | Current performance end date. Can be empty. Format: `YYYY-MM-DD`. | `2026-09-30` |
| 26 | `period_of_performance_potential_end_date` | TIMESTAMP | Potential end date if all options exercised. **Mixed format**: some `YYYY-MM-DD`, some `YYYY-MM-DD HH:MM:SS`. | `2028-09-30 00:00:00` |
| 27 | `ordering_period_end_date` | DATE | End date of the ordering period for IDVs. Format: `YYYY-MM-DD`. | `2026-01-28` |
| 28 | `solicitation_date` | DATE | Date the solicitation was issued. Can be empty. Format: `YYYY-MM-DD`. | `2019-10-07` |

### Awarding/Funding Agency (Columns 29–44)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 29 | `awarding_agency_code` | TEXT | CGAC department code (3-digit). | `089` |
| 30 | `awarding_agency_name` | TEXT | Department/establishment name. | `Department of Energy` |
| 31 | `awarding_sub_agency_code` | TEXT | Level 2 sub-agency code (4-digit). | `8900` |
| 32 | `awarding_sub_agency_name` | TEXT | Sub-agency name. | `Department of Energy` |
| 33 | `awarding_office_code` | TEXT | Level N office code. | `893030` |
| 34 | `awarding_office_name` | TEXT | Office name. | `HEADQUARTERS PROCUREMENT SERVICES` |
| 35 | `funding_agency_code` | TEXT | CGAC code of the funding agency (may differ from awarding). | `089` |
| 36 | `funding_agency_name` | TEXT | Funding agency name. | `Department of Energy` |
| 37 | `funding_sub_agency_code` | TEXT | Funding sub-agency code. | `8900` |
| 38 | `funding_sub_agency_name` | TEXT | Funding sub-agency name. | `Department of Energy` |
| 39 | `funding_office_code` | TEXT | Funding office code. | `893002` |
| 40 | `funding_office_name` | TEXT | Funding office name. | `MANAGEMENT` |
| 41 | `treasury_accounts_funding_this_award` | TEXT | Treasury Account Fund Symbol(s). **Semicolon-delimited** when multiple. Format: `{agency}-{period}-{main_acct}-{sub_acct}`. | `012-2024/2027-1106-000;012-X-1115-000` |
| 42 | `federal_accounts_funding_this_award` | TEXT | Federal account(s). **Semicolon-delimited** when multiple. Format: `{agency}-{acct}`. | `012-1106;012-1115` |
| 43 | `object_classes_funding_this_award` | TEXT | Object class(es) with descriptions. **Semicolon-delimited** when multiple. Format: `{code}: {description}`. | `25.1: Advisory and assistance services;25.2: Other services from non-Federal sources` |
| 44 | `program_activities_funding_this_award` | TEXT | Program activity/activities. **Semicolon-delimited** when multiple. Format: `{code}: {name}`. | `0001: WILDLAND FIRE MANAGEMENT;0002: EXPORT ADMINISTRATION` |

### Foreign Funding & SAM Exception (Columns 45–48)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 45 | `foreign_funding` | TEXT | Code indicating foreign funding applicability. | `X` |
| 46 | `foreign_funding_description` | TEXT | Description of foreign funding code. | `NOT APPLICABLE` |
| 47 | `sam_exception` | TEXT | SAM registration exception code. Usually empty. | `` |
| 48 | `sam_exception_description` | TEXT | Description of SAM exception. | `` |

### Recipient (Columns 49–73)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 49 | `recipient_uei` | TEXT | **Unique Entity Identifier** — 12-char alphanumeric. Primary join key to SAM.gov. | `GHDAN1FNERA8` |
| 50 | `recipient_duns` | TEXT | **Deprecated** DUNS number. Empty in all observed FY2026 rows. | `` |
| 51 | `recipient_name` | TEXT | Standardized/cleaned recipient name. | `THE MATTHEWS GROUP INC` |
| 52 | `recipient_name_raw` | TEXT | Original/raw name as submitted. May differ in word order. | `MATTHEWS GROUP, INC., THE` |
| 53 | `recipient_doing_business_as_name` | TEXT | DBA name. Usually empty. | `` |
| 54 | `cage_code` | TEXT | Commercial and Government Entity Code. 5-char alphanumeric. Also maps to SAM.gov. | `1VEU1` |
| 55 | `recipient_parent_uei` | TEXT | Parent company UEI. Same as `recipient_uei` when entity has no parent. | `GHDAN1FNERA8` |
| 56 | `recipient_parent_duns` | TEXT | **Deprecated** parent DUNS. Empty in FY2026. | `` |
| 57 | `recipient_parent_name` | TEXT | Standardized parent company name. | `THE MATTHEWS GROUP INC` |
| 58 | `recipient_parent_name_raw` | TEXT | Raw parent company name. | `THE MATTHEWS GROUP INC` |
| 59 | `recipient_country_code` | TEXT | 3-letter country code. | `USA` |
| 60 | `recipient_country_name` | TEXT | Country name. | `UNITED STATES` |
| 61 | `recipient_address_line_1` | TEXT | Street address. | `18915 LINCOLN RD` |
| 62 | `recipient_address_line_2` | TEXT | Second address line. Usually empty. | `` |
| 63 | `recipient_city_name` | TEXT | City name. | `PURCELLVILLE` |
| 64 | `prime_award_transaction_recipient_county_fips_code` | TEXT | 5-digit FIPS county code. | `51107` |
| 65 | `recipient_county_name` | TEXT | County name. | `LOUDOUN` |
| 66 | `prime_award_transaction_recipient_state_fips_code` | TEXT | 2-digit FIPS state code. | `51` |
| 67 | `recipient_state_code` | TEXT | 2-letter state abbreviation. | `VA` |
| 68 | `recipient_state_name` | TEXT | Full state name (uppercase). | `VIRGINIA` |
| 69 | `recipient_zip_4_code` | TEXT | ZIP+4 code (9 digits, no hyphen). | `201324145` |
| 70 | `prime_award_transaction_recipient_cd_original` | TEXT | Original congressional district. Format: `{state}-{district}`. | `VA-10` |
| 71 | `prime_award_transaction_recipient_cd_current` | TEXT | Current congressional district (may change with redistricting). | `VA-10` |
| 72 | `recipient_phone_number` | TEXT | Phone number (10 digits, no formatting). | `5407514465` |
| 73 | `recipient_fax_number` | TEXT | Fax number (10 digits, no formatting). | `5403389518` |

### Place of Performance (Columns 74–84)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 74 | `primary_place_of_performance_country_code` | TEXT | Country code for place of performance. | `USA` |
| 75 | `primary_place_of_performance_country_name` | TEXT | Country name. | `UNITED STATES` |
| 76 | `primary_place_of_performance_city_name` | TEXT | City name. | `PURCELLVILLE` |
| 77 | `prime_award_transaction_place_of_performance_county_fips_code` | TEXT | 5-digit FIPS county code. | `51107` |
| 78 | `primary_place_of_performance_county_name` | TEXT | County name. | `LOUDOUN` |
| 79 | `prime_award_transaction_place_of_performance_state_fips_code` | TEXT | 2-digit FIPS state code. | `51` |
| 80 | `primary_place_of_performance_state_code` | TEXT | 2-letter state abbreviation. | `VA` |
| 81 | `primary_place_of_performance_state_name` | TEXT | Full state name (uppercase). | `VIRGINIA` |
| 82 | `primary_place_of_performance_zip_4` | TEXT | ZIP+4 code. | `201324145` |
| 83 | `prime_award_transaction_place_of_performance_cd_original` | TEXT | Original congressional district. | `VA-10` |
| 84 | `prime_award_transaction_place_of_performance_cd_current` | TEXT | Current congressional district. | `VA-10` |

### Award Type & IDV (Columns 85–95)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 85 | `award_or_idv_flag` | TEXT | Whether the record is an award or an Indefinite Delivery Vehicle. | `AWARD` or `IDV` |
| 86 | `award_type_code` | TEXT | Type code: `A`=BPA Call, `B`=Purchase Order, `C`=Delivery Order, `D`=Definitive Contract. | `D` |
| 87 | `award_type` | TEXT | Description of award type. | `DEFINITIVE CONTRACT` |
| 88 | `idv_type_code` | TEXT | IDV type code (only for IDVs): `A`=GWAC, `B`=IDC, `C`=FSS, `D`=BOA, `E`=BPA. | `B` |
| 89 | `idv_type` | TEXT | IDV type description. | `IDC` |
| 90 | `multiple_or_single_award_idv_code` | TEXT | `M`=Multiple Award, `S`=Single Award. | `S` |
| 91 | `multiple_or_single_award_idv` | TEXT | Description. | `SINGLE AWARD` |
| 92 | `type_of_idc_code` | TEXT | IDC subtype code: `A`=Indefinite Delivery / Requirements, `B`=Indefinite Delivery / Indefinite Quantity, `C`=Indefinite Delivery / Definite Quantity. | `B` |
| 93 | `type_of_idc` | TEXT | Description. | `INDEFINITE DELIVERY / INDEFINITE QUANTITY` |
| 94 | `type_of_contract_pricing_code` | TEXT | Pricing type code. | `Z` |
| 95 | `type_of_contract_pricing` | TEXT | Pricing type description. Values include FIRM FIXED PRICE, LABOR HOURS, TIME AND MATERIALS, COST PLUS FIXED FEE, etc. | `LABOR HOURS` |

### Transaction Details (Columns 96–101)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 96 | `transaction_description` | TEXT | Free-text description of this specific action/modification. | `CHANGE COR & IAO` |
| 97 | `prime_award_base_transaction_description` | TEXT | Description of the base award (original purpose). | `REPAIR, ALTERATION AND CONSTRUCTION WORK...` |
| 98 | `action_type_code` | TEXT | Type of action (see full code table in Section 5). | `M` |
| 99 | `action_type` | TEXT | Description of action type. | `OTHER ADMINISTRATIVE ACTION` |
| 100 | `solicitation_identifier` | TEXT | Solicitation number/ID. | `89303019RMA000014` |
| 101 | `number_of_actions` | TEXT | Number of actions reported. Usually empty. | `` |

### Product/Service Classification (Columns 102–111)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 102 | `inherently_governmental_functions` | TEXT | Code: `CL`=Closely Associated, `OT`=Other. | `CL` |
| 103 | `inherently_governmental_functions_description` | TEXT | Description. | `CLOSELY ASSOCIATED` |
| 104 | `product_or_service_code` | TEXT | PSC code identifying the product or service procured. 4-char. | `Z2AB` |
| 105 | `product_or_service_code_description` | TEXT | PSC description. | `REPAIR OR ALTERATION OF CONFERENCE SPACE AND FACILITIES` |
| 106 | `contract_bundling_code` | TEXT | Bundling designation code. | `H` |
| 107 | `contract_bundling` | TEXT | Bundling description. | `NOT BUNDLED` |
| 108 | `dod_claimant_program_code` | TEXT | DoD claimant program code. Usually empty for non-DoD. | `` |
| 109 | `dod_claimant_program_description` | TEXT | Description. | `` |
| 110 | `naics_code` | TEXT | 6-digit NAICS industry code. | `236220` |
| 111 | `naics_description` | TEXT | NAICS industry description. | `COMMERCIAL AND INSTITUTIONAL BUILDING CONSTRUCTION` |

### Procurement Policy Flags (Columns 112–195)

~84 coded fields for competition, set-aside, regulatory compliance, and contract characteristics. Most are code/description pairs.

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 112 | `recovered_materials_sustainability_code` | TEXT | Sustainability code. | `C` |
| 113 | `recovered_materials_sustainability` | TEXT | Description. | `NO CLAUSES INCLUDED AND NO SUSTAINABILITY INCLUDED` |
| 114 | `domestic_or_foreign_entity_code` | TEXT | `A`=U.S. Owned, `B`=Other U.S., `C`=Foreign-Owned, `D`=Foreign-Owned but U.S. Inc. | `A` |
| 115 | `domestic_or_foreign_entity` | TEXT | Description. | `U.S. OWNED BUSINESS` |
| 116 | `dod_acquisition_program_code` | TEXT | DoD acquisition program code. | `` |
| 117 | `dod_acquisition_program_description` | TEXT | Description. | `` |
| 118 | `information_technology_commercial_item_category_code` | TEXT | IT commercial item category. | `` |
| 119 | `information_technology_commercial_item_category` | TEXT | Description. | `` |
| 120 | `epa_designated_product_code` | TEXT | EPA designation. | `` |
| 121 | `epa_designated_product` | TEXT | Description. | `` |
| 122 | `country_of_product_or_service_origin_code` | TEXT | Origin country code. | `` |
| 123 | `country_of_product_or_service_origin` | TEXT | Description. | `` |
| 124 | `place_of_manufacture_code` | TEXT | Manufacture location. | `` |
| 125 | `place_of_manufacture` | TEXT | Description. | `` |
| 126 | `subcontracting_plan_code` | TEXT | `A`=Plan not included, `B`=Plan not required, `C`=Plan required (included), etc. | `B` |
| 127 | `subcontracting_plan` | TEXT | Description. | `PLAN NOT REQUIRED` |
| 128 | `extent_competed_code` | TEXT | Competition type: `A`=Full and Open, `B`=Not Available, `C`=Not Competed, `D`=Full and Open After Exclusion, `E`=Follow On, `F`=Competed Under SAP, `G`=Not Competed Under SAP, `CDO`=Competitive Delivery Order, `NDO`=Non-Competitive Delivery Order. | `A` |
| 129 | `extent_competed` | TEXT | Description. | `FULL AND OPEN COMPETITION` |
| 130 | `solicitation_procedures_code` | TEXT | Solicitation method code. | `NP` |
| 131 | `solicitation_procedures` | TEXT | Description. | `NEGOTIATED PROPOSAL/QUOTE` |
| 132 | `type_of_set_aside_code` | TEXT | Set-aside type (see full code table below). | `NONE` |
| 133 | `type_of_set_aside` | TEXT | Description. | `NO SET ASIDE USED.` |
| 134 | `evaluated_preference_code` | TEXT | Evaluation preference code. | `NONE` |
| 135 | `evaluated_preference` | TEXT | Description. | `NO PREFERENCE USED` |
| 136 | `research_code` | TEXT | Research type code. | `` |
| 137 | `research` | TEXT | Description. | `` |
| 138 | `fair_opportunity_limited_sources_code` | TEXT | Fair opportunity limitation. | `` |
| 139 | `fair_opportunity_limited_sources` | TEXT | Description. | `` |
| 140 | `other_than_full_and_open_competition_code` | TEXT | OTFAOC code. | `` |
| 141 | `other_than_full_and_open_competition` | TEXT | Description. | `` |
| 142 | `number_of_offers_received` | TEXT | Count of offers/bids received. | `8` |
| 143 | `commercial_item_acquisition_procedures_code` | TEXT | Commercial item procedures. | `A` |
| 144 | `commercial_item_acquisition_procedures` | TEXT | Description. | `COMMERCIAL PRODUCTS/SERVICES` |
| 145 | `small_business_competitiveness_demonstration_program` | TEXT | Boolean flag (`t`/`f`). | `f` |
| 146 | `simplified_procedures_for_certain_commercial_items_code` | TEXT | `Y`/`N`. | `N` |
| 147 | `simplified_procedures_for_certain_commercial_items` | TEXT | Description. | `NO` |
| 148 | `a76_fair_act_action_code` | TEXT | A-76 Fair Act code. | `N` |
| 149 | `a76_fair_act_action` | TEXT | Description. | `NO` |
| 150 | `fed_biz_opps_code` | TEXT | FedBizOpps posting. | `Y` |
| 151 | `fed_biz_opps` | TEXT | Description. | `YES` |
| 152 | `local_area_set_aside_code` | TEXT | Local area set-aside. | `N` |
| 153 | `local_area_set_aside` | TEXT | Description. | `NO` |
| 154 | `price_evaluation_adjustment_preference_percent_difference` | TEXT | Price evaluation preference percentage. Usually empty. | `` |
| 155 | `clinger_cohen_act_planning_code` | TEXT | CCA compliance. | `N` |
| 156 | `clinger_cohen_act_planning` | TEXT | Description. | `NO` |
| 157 | `materials_supplies_articles_equipment_code` | TEXT | Materials/supplies flag. | `N` |
| 158 | `materials_supplies_articles_equipment` | TEXT | Description. | `NO` |
| 159 | `labor_standards_code` | TEXT | Labor standards applicability. | `N` |
| 160 | `labor_standards` | TEXT | Description. | `NO` |
| 161 | `construction_wage_rate_requirements_code` | TEXT | Davis-Bacon wage rate requirements. | `N` |
| 162 | `construction_wage_rate_requirements` | TEXT | Description. | `NO` |
| 163 | `interagency_contracting_authority_code` | TEXT | Interagency authority. | `X` |
| 164 | `interagency_contracting_authority` | TEXT | Description. | `NOT APPLICABLE` |
| 165 | `other_statutory_authority` | TEXT | Free-text statutory authority. Usually empty. | `` |
| 166 | `program_acronym` | TEXT | Program acronym. Usually empty. | `` |
| 167 | `parent_award_type_code` | TEXT | Parent award type code (matches col 86 values). | `` |
| 168 | `parent_award_type` | TEXT | Description. | `` |
| 169 | `parent_award_single_or_multiple_code` | TEXT | Parent award single/multiple. | `` |
| 170 | `parent_award_single_or_multiple` | TEXT | Description. | `` |
| 171 | `major_program` | TEXT | Major program identifier. Usually empty. | `` |
| 172 | `national_interest_action_code` | TEXT | National interest/emergency code. | `` |
| 173 | `national_interest_action` | TEXT | Description. | `` |
| 174 | `cost_or_pricing_data_code` | TEXT | Cost/pricing data obtained. | `N` |
| 175 | `cost_or_pricing_data` | TEXT | Description. | `NO` |
| 176 | `cost_accounting_standards_clause_code` | TEXT | CAS clause applicability. | `N` |
| 177 | `cost_accounting_standards_clause` | TEXT | Description. | `NO - CAS WAIVER APPROVED` |
| 178 | `government_furnished_property_code` | TEXT | GFE/GFP usage. | `N` |
| 179 | `government_furnished_property` | TEXT | Description. | `TRANSACTION DOES NOT USE GFE/GFP` |
| 180 | `sea_transportation_code` | TEXT | Sea transportation requirement. | `` |
| 181 | `sea_transportation` | TEXT | Description. | `` |
| 182 | `undefinitized_action_code` | TEXT | Undefinitized action indicator. | `X` |
| 183 | `undefinitized_action` | TEXT | Description. | `NO` |
| 184 | `consolidated_contract_code` | TEXT | Contract consolidation. | `D` |
| 185 | `consolidated_contract` | TEXT | Description. | `NOT CONSOLIDATED` |
| 186 | `performance_based_service_acquisition_code` | TEXT | PBA indicator. | `N` |
| 187 | `performance_based_service_acquisition` | TEXT | Description. | `NO - SERVICE WHERE PBA IS NOT USED.` |
| 188 | `multi_year_contract_code` | TEXT | Multi-year contract flag. | `N` |
| 189 | `multi_year_contract` | TEXT | Description. | `NO` |
| 190 | `contract_financing_code` | TEXT | Contract financing method. | `` |
| 191 | `contract_financing` | TEXT | Description. | `` |
| 192 | `purchase_card_as_payment_method_code` | TEXT | Purchase card usage. | `` |
| 193 | `purchase_card_as_payment_method` | TEXT | Description. | `` |
| 194 | `contingency_humanitarian_or_peacekeeping_operation_code` | TEXT | Contingency operations code. | `X` |
| 195 | `contingency_humanitarian_or_peacekeeping_operation` | TEXT | Description. | `NOT APPLICABLE` |

### Business Type Flags (Columns 196–284)

89 columns describing the recipient's business classifications. **All boolean flags use lowercase `t` (true) / `f` (false) format**, except for three non-boolean fields noted below.

#### Ownership/Demographics (196–214)

| # | Column Name | Description | Sample |
|---|---|---|---|
| 196 | `alaskan_native_corporation_owned_firm` | t/f flag | `f` |
| 197 | `american_indian_owned_business` | t/f flag | `f` |
| 198 | `indian_tribe_federally_recognized` | t/f flag | `f` |
| 199 | `native_hawaiian_organization_owned_firm` | t/f flag | `f` |
| 200 | `tribally_owned_firm` | t/f flag | `f` |
| 201 | `veteran_owned_business` | t/f flag | `t` |
| 202 | `service_disabled_veteran_owned_business` | t/f flag | `f` |
| 203 | `woman_owned_business` | t/f flag | `t` |
| 204 | `women_owned_small_business` | t/f flag | `f` |
| 205 | `economically_disadvantaged_women_owned_small_business` | t/f flag | `f` |
| 206 | `joint_venture_women_owned_small_business` | t/f flag | `f` |
| 207 | `joint_venture_economic_disadvantaged_women_owned_small_bus` | t/f flag (column name truncated) | `f` |
| 208 | `minority_owned_business` | t/f flag | `t` |
| 209 | `subcontinent_asian_asian_indian_american_owned_business` | t/f flag | `f` |
| 210 | `asian_pacific_american_owned_business` | t/f flag | `f` |
| 211 | `black_american_owned_business` | t/f flag | `f` |
| 212 | `hispanic_american_owned_business` | t/f flag | `f` |
| 213 | `native_american_owned_business` | t/f flag | `t` |
| 214 | `other_minority_owned_business` | t/f flag | `f` |

#### Business Size Determination (215–219)

| # | Column Name | Description | Sample |
|---|---|---|---|
| 215 | `contracting_officers_determination_of_business_size` | **Not boolean** — text value: `SMALL BUSINESS` or `OTHER THAN SMALL BUSINESS`. | `OTHER THAN SMALL BUSINESS` |
| 216 | `contracting_officers_determination_of_business_size_code` | **Not boolean** — `S`=Small Business, `O`=Other Than Small Business. | `O` |
| 217 | `emerging_small_business` | t/f flag | `f` |
| 218 | `community_developed_corporation_owned_firm` | t/f flag | `f` |
| 219 | `labor_surplus_area_firm` | t/f flag | `f` |

#### Government Entity Types (220–233)

| # | Column Name | Description | Sample |
|---|---|---|---|
| 220 | `us_federal_government` | t/f flag | `f` |
| 221 | `federally_funded_research_and_development_corp` | t/f flag | `f` |
| 222 | `federal_agency` | t/f flag | `f` |
| 223 | `us_state_government` | t/f flag | `f` |
| 224 | `us_local_government` | t/f flag | `f` |
| 225 | `city_local_government` | t/f flag | `f` |
| 226 | `county_local_government` | t/f flag | `f` |
| 227 | `inter_municipal_local_government` | t/f flag | `f` |
| 228 | `local_government_owned` | t/f flag | `f` |
| 229 | `municipality_local_government` | t/f flag | `f` |
| 230 | `school_district_local_government` | t/f flag | `f` |
| 231 | `township_local_government` | t/f flag | `f` |
| 232 | `us_tribal_government` | t/f flag | `f` |
| 233 | `foreign_government` | t/f flag | `f` |

#### Organizational Type & Legal Structure (234–265)

| # | Column Name | Description | Sample |
|---|---|---|---|
| 234 | `organizational_type` | **Not boolean** — text value: `CORPORATE NOT TAX EXEMPT`, `CORPORATE TAX EXEMPT`, `OTHER`, etc. | `CORPORATE NOT TAX EXEMPT` |
| 235 | `corporate_entity_not_tax_exempt` | t/f flag | `t` |
| 236 | `corporate_entity_tax_exempt` | t/f flag | `f` |
| 237 | `partnership_or_limited_liability_partnership` | t/f flag | `f` |
| 238 | `sole_proprietorship` | t/f flag | `f` |
| 239 | `small_agricultural_cooperative` | t/f flag | `f` |
| 240 | `international_organization` | t/f flag | `f` |
| 241 | `us_government_entity` | t/f flag | `f` |
| 242 | `community_development_corporation` | t/f flag | `f` |
| 243 | `domestic_shelter` | t/f flag | `f` |
| 244 | `educational_institution` | t/f flag | `f` |
| 245 | `foundation` | t/f flag | `f` |
| 246 | `hospital_flag` | t/f flag | `f` |
| 247 | `manufacturer_of_goods` | t/f flag | `f` |
| 248 | `veterinary_hospital` | t/f flag | `f` |
| 249 | `hispanic_servicing_institution` | t/f flag | `f` |
| 250 | `receives_contracts` | t/f flag | `t` |
| 251 | `receives_financial_assistance` | t/f flag | `f` |
| 252 | `receives_contracts_and_financial_assistance` | t/f flag | `t` |
| 253 | `airport_authority` | t/f flag | `f` |
| 254 | `council_of_governments` | t/f flag | `f` |
| 255 | `housing_authorities_public_tribal` | t/f flag | `f` |
| 256 | `interstate_entity` | t/f flag | `f` |
| 257 | `planning_commission` | t/f flag | `f` |
| 258 | `port_authority` | t/f flag | `f` |
| 259 | `transit_authority` | t/f flag | `f` |
| 260 | `subchapter_scorporation` | t/f flag | `t` |
| 261 | `limited_liability_corporation` | t/f flag | `f` |
| 262 | `foreign_owned` | t/f flag | `f` |
| 263 | `for_profit_organization` | t/f flag | `t` |
| 264 | `nonprofit_organization` | t/f flag | `f` |
| 265 | `other_not_for_profit_organization` | t/f flag | `f` |

#### Special Programs & Certifications (266–284)

| # | Column Name | Description | Sample |
|---|---|---|---|
| 266 | `the_ability_one_program` | t/f flag | `f` |
| 267 | `private_university_or_college` | t/f flag | `f` |
| 268 | `state_controlled_institution_of_higher_learning` | t/f flag | `f` |
| 269 | `1862_land_grant_college` | t/f flag | `f` |
| 270 | `1890_land_grant_college` | t/f flag | `f` |
| 271 | `1994_land_grant_college` | t/f flag | `f` |
| 272 | `minority_institution` | t/f flag | `f` |
| 273 | `historically_black_college` | t/f flag | `f` |
| 274 | `tribal_college` | t/f flag | `f` |
| 275 | `alaskan_native_servicing_institution` | t/f flag | `f` |
| 276 | `native_hawaiian_servicing_institution` | t/f flag | `f` |
| 277 | `school_of_forestry` | t/f flag | `f` |
| 278 | `veterinary_college` | t/f flag | `f` |
| 279 | `dot_certified_disadvantage` | t/f flag | `f` |
| 280 | `self_certified_small_disadvantaged_business` | t/f flag | `f` |
| 281 | `small_disadvantaged_business` | t/f flag | `f` |
| 282 | `c8a_program_participant` | t/f flag | `f` |
| 283 | `historically_underutilized_business_zone_hubzone_firm` | t/f flag | `f` |
| 284 | `sba_certified_8a_joint_venture` | t/f flag | `f` |

### Executive Compensation (Columns 285–294)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 285 | `highly_compensated_officer_1_name` | TEXT | Name of highest-compensated officer. Often empty. | `ALAN D WEISS` |
| 286 | `highly_compensated_officer_1_amount` | DECIMAL | Annual compensation amount. | `357505.00` |
| 287 | `highly_compensated_officer_2_name` | TEXT | Second-highest compensated officer. | `RUSSELL T COOK` |
| 288 | `highly_compensated_officer_2_amount` | DECIMAL | Compensation amount. | `299758.00` |
| 289 | `highly_compensated_officer_3_name` | TEXT | Third. | `TATIANA (TANYA) C MATTHEWS` |
| 290 | `highly_compensated_officer_3_amount` | DECIMAL | Amount. | `250870.00` |
| 291 | `highly_compensated_officer_4_name` | TEXT | Fourth. | `MARK E BAILEY` |
| 292 | `highly_compensated_officer_4_amount` | DECIMAL | Amount. | `250647.00` |
| 293 | `highly_compensated_officer_5_name` | TEXT | Fifth. | `JOSEPH N MATTHEWS` |
| 294 | `highly_compensated_officer_5_amount` | DECIMAL | Amount. | `246147.00` |

### Metadata (Columns 295–297)

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|
| 295 | `usaspending_permalink` | TEXT | Direct link to the award on USASpending.gov. | `https://www.usaspending.gov/award/CONT_IDV_89303020DMA000020_8900/` |
| 296 | `initial_report_date` | TIMESTAMP+TZ | When the transaction was first reported. Format: `YYYY-MM-DD HH:MM:SS+00`. | `2025-11-03 16:42:19+00` |
| 297 | `last_modified_date` | TIMESTAMP+TZ | When the transaction was last modified. Format: `YYYY-MM-DD HH:MM:SS+00`. | `2025-11-03 16:44:15+00` |

---

## 3. Key Fields for Our Use Case

### Primary Keys

| Field | Column | Notes |
|---|---|---|
| `contract_transaction_unique_key` | 1 | **Natural unique key per transaction row.** Concatenation of agencyID, ref IDV agency, PIID, mod number, parent award ID, and transaction number. Guaranteed unique across all transactions in the dataset. |
| `contract_award_unique_key` | 2 | **Award-level grouping key.** Groups all transactions (initial award + modifications) under one award. Use this to reconstruct award history or get latest state. Format differs for awards (`CONT_AWD_...`) vs IDVs (`CONT_IDV_...`). |
| `award_id_piid` | 3 | **Human-readable award ID** (Procurement Instrument Identifier). Not unique by itself — same PIID appears with different modification numbers. |

### SAM.gov Join Keys

| Field | Column | Notes |
|---|---|---|
| `recipient_uei` | 49 | **Primary join key to SAM.gov** `unique_entity_id`. 12-character alphanumeric. Populated in all observed FY2026 rows. |
| `recipient_parent_uei` | 55 | Parent company UEI. Also joins to SAM.gov. Equals `recipient_uei` when entity has no parent. |
| `cage_code` | 54 | **Secondary join key to SAM.gov.** 5-character CAGE code. Also present in SAM.gov entity data. |
| `recipient_name` | 51 | Standardized contractor name. Useful for display/search but not a reliable join key. |

### Dollar Amount Fields

| Field | Column | What It Represents |
|---|---|---|
| `federal_action_obligation` | 10 | **Per-action incremental amount.** The dollars obligated/deobligated in THIS specific action. Can be $0.00 (admin changes) or negative (deobligations). This is the "delta" for each transaction. |
| `total_dollars_obligated` | 11 | **Cumulative obligation.** Running total of all obligations on the award as of this action. |
| `current_total_value_of_award` | 14 | **Current total value.** Total amount obligated including base and exercised options. Similar to col 11 but reflects option exercise value. |
| `base_and_exercised_options_value` | 13 | **Base + exercised options.** Contract value for base contract and any options that have been exercised (but not unexercised options). Empty for IDVs. |
| `base_and_all_options_value` | 15 | **Base + ALL options (ceiling).** Mutually agreed total value including all options, exercised or not. For IDVs, includes estimated value of all potential orders. Often $0.00 for modification records. |
| `potential_total_value_of_award` | 16 | **Maximum potential value.** The absolute ceiling — total amount that could be obligated if base and all options are exercised. This is the "contract ceiling" value. |

**Dollar amount hierarchy:** `federal_action_obligation` (per-action) ≤ `total_dollars_obligated` (cumulative) ≤ `current_total_value_of_award` ≤ `base_and_all_options_value` ≤ `potential_total_value_of_award` (ceiling).

### Classification Fields

| Field | Column | Notes |
|---|---|---|
| `naics_code` | 110 | 6-digit NAICS industry code. Critical for industry-based filtering. |
| `naics_description` | 111 | NAICS description text. |
| `product_or_service_code` | 104 | 4-character PSC code identifying what was procured. |
| `product_or_service_code_description` | 105 | PSC description. |
| `awarding_agency_name` | 30 | Department-level agency (e.g., `Department of Energy`). |
| `awarding_sub_agency_name` | 32 | Sub-agency (e.g., `National Aeronautics and Space Administration`). |
| `awarding_office_name` | 34 | Specific contracting office. |
| `action_date` | 22 | Date the action was signed. Primary date field for time-series analysis. |
| `action_type_code` | 98 | Type of action — see Section 5 for full code table. |
| `contracting_officers_determination_of_business_size_code` | 216 | `S`=Small Business, `O`=Other Than Small Business. The official size determination. |

### Place of Performance

| Field | Column | Notes |
|---|---|---|
| `primary_place_of_performance_state_code` | 80 | 2-letter state code where work is performed. |
| `primary_place_of_performance_city_name` | 76 | City name. |
| `primary_place_of_performance_zip_4` | 82 | ZIP+4 code. |
| `primary_place_of_performance_county_name` | 78 | County name. |

---

## 4. SAM.gov Join Key

### Primary Join

```sql
usaspending_contracts.recipient_uei = sam_gov_entities.unique_entity_id
```

- `recipient_uei` is a 12-character alphanumeric UEI, matching the format used in SAM.gov
- **Populated in all observed FY2026 rows** — no null UEIs found in sample data
- This is the definitive link between federal contract award data and SAM.gov entity registration data

### Parent Company Join

```sql
usaspending_contracts.recipient_parent_uei = sam_gov_entities.unique_entity_id
```

- When `recipient_parent_uei` differs from `recipient_uei`, the recipient is a subsidiary
- When they are equal, the entity has no parent (is itself the ultimate parent)

### Secondary Join Key

```sql
usaspending_contracts.cage_code = sam_gov_entities.cage_code
```

- CAGE code is a 5-character identifier also present in SAM.gov
- Useful as a fallback or cross-validation join key

### Caveats

1. **Legacy DUNS records:** Column 50 (`recipient_duns`) is **empty in all observed FY2026 data**. DUNS was deprecated in favor of UEI. Older fiscal year data in delta files may still have DUNS populated without UEI.
2. **SAM exceptions:** Columns 47–48 (`sam_exception`, `sam_exception_description`) indicate cases where a recipient has a SAM registration exception (e.g., foreign entities, classified contracts). These entities may not have a SAM.gov record to join to.
3. **Foreign entities:** Entities with `recipient_country_code` ≠ `USA` may not be registered in SAM.gov, particularly for foreign assistance contracts.

---

## 5. How Multiple Actions on the Same Award Work

### Transaction vs Award

- Each **row** is a transaction (one action on one award) — uniquely identified by `contract_transaction_unique_key`
- Each **award** has one or more transactions — grouped by `contract_award_unique_key`
- The same `award_id_piid` appears with different `modification_number` and `action_date` values

### Action Type Codes (Contracts)

| Code | Description | Typical `federal_action_obligation` |
|---|---|---|
| A | ADDITIONAL WORK (NEW AGREEMENT, JUSTIFICATION REQUIRED) | Non-zero |
| B | SUPPLEMENTAL AGREEMENT FOR WORK WITHIN SCOPE | Non-zero (can be small, e.g., $839.88) |
| C | FUNDING ONLY ACTION | Non-zero |
| D | CHANGE ORDER | Non-zero |
| E | TERMINATE FOR DEFAULT (COMPLETE OR PARTIAL) | Negative (deobligation) |
| F | TERMINATE FOR CONVENIENCE (COMPLETE OR PARTIAL) | Negative (deobligation) |
| G | EXERCISE AN OPTION | Non-zero (e.g., $268,432.70) |
| H | DEFINITIZE LETTER CONTRACT | Varies |
| J | NOVATION AGREEMENT | Usually $0 |
| K | CLOSE OUT | Usually $0 |
| L | DEFINITIZE CHANGE ORDER | Varies |
| M | OTHER ADMINISTRATIVE ACTION | Usually $0 (admin only) |
| N | LEGAL CONTRACT CANCELLATION | Negative |
| P | REREPRESENTATION OF NON-NOVATED MERGER/ACQUISITION | Usually $0 |
| R | REREPRESENTATION | Usually $0 |
| S | CHANGE PIID | Usually $0 |
| T | TRANSFER ACTION | Usually $0 |
| V | UEI OR LEGAL BUSINESS NAME CHANGE - NON-NOVATION | Usually $0 |
| W | ENTITY ADDRESS CHANGE | Usually $0 |
| X | TERMINATE FOR CAUSE | Negative |
| Y | ADD SUBCONTRACT PLAN | Usually $0 |

### Dollar Amount Behavior Across Actions

- `federal_action_obligation` (col 10): **Incremental** — the change for this specific action. Can be $0 (admin), positive (new funding), or negative (deobligation like `-387.25`, `-13659.00`)
- `total_dollars_obligated` (col 11): **Cumulative** — running total of all obligations as of this action

### Getting Latest Award State

To get the most recent state of each award:
```sql
-- Latest transaction per award
SELECT DISTINCT ON (contract_award_unique_key) *
FROM usaspending_contracts
ORDER BY contract_award_unique_key, action_date DESC, last_modified_date DESC
```

### Primary Key

`contract_transaction_unique_key` is the natural primary key — confirmed unique per row in the dataset.

---

## 6. Fields Requiring Special Parsing

### Boolean Flag Columns (196–284)

- **Format: lowercase `t` and `f`** (not `TRUE`/`FALSE`, not `Y`/`N`, not `1`/`0`)
- 86 of the 89 columns in this range use `t`/`f` format
- **3 exceptions that are NOT boolean:**
  - Col 215 `contracting_officers_determination_of_business_size` — text values: `SMALL BUSINESS`, `OTHER THAN SMALL BUSINESS`
  - Col 216 `contracting_officers_determination_of_business_size_code` — `S` or `O`
  - Col 234 `organizational_type` — text values: `CORPORATE NOT TAX EXEMPT`, `CORPORATE TAX EXEMPT`, `OTHER`, etc.
- Data dictionary confirms: valid values are `F = False, T = True` (stored as lowercase in CSV)

### Multi-Value / Delimited Fields (Columns 41–44)

These fields can contain **semicolon-delimited lists** when multiple values apply:

| Column | Format | Example |
|---|---|---|
| 41 `treasury_accounts_funding_this_award` | `{agency}-{period}-{main_acct}-{sub_acct}` semicolon-separated | `012-2024/2027-1106-000;012-X-1115-000` |
| 42 `federal_accounts_funding_this_award` | `{agency}-{acct}` semicolon-separated | `012-1106;012-1115` |
| 43 `object_classes_funding_this_award` | `{code}: {description}` semicolon-separated | `25.1: Advisory and assistance services;25.2: Other services from non-Federal sources` |
| 44 `program_activities_funding_this_award` | `{code}: {name}` semicolon-separated | `0001: WILDLAND FIRE MANAGEMENT;0002: EXPORT ADMINISTRATION` |

Some awards have **5+ semicolon-separated values** in these fields (e.g., FDA contracts with multiple program activities).

### DEFC Codes (Column 17)

`disaster_emergency_fund_codes_for_overall_award` contains semicolon-delimited DEFC codes with descriptions:
```
AAC: Wildfire Suppression P.L. 117-328;Q: Not Designated Nonemergency/Emergency/Disaster/Wildfire Suppression
```

Most rows have either empty or a single value like `Q: Not Designated...`.

### Dollar Amounts

- Format: decimal with 2 decimal places (e.g., `268432.70`, `0.00`)
- **Negative values exist** for deobligations (e.g., `-387.25`, `-1712.34`, `-13659.00`)
- No currency symbols, no comma thousands separators
- Empty string when no value (not `NULL` text, not `0.00` — truly empty)

### Date Formats

| Pattern | Columns | Format | Example |
|---|---|---|---|
| Date only | 22, 24, 25, 27, 28 | `YYYY-MM-DD` | `2025-11-03` |
| Timestamp with timezone | 296, 297 | `YYYY-MM-DD HH:MM:SS+00` | `2025-11-03 16:44:15+00` |
| **Mixed format** | 26 (`period_of_performance_potential_end_date`) | Sometimes `YYYY-MM-DD`, sometimes `YYYY-MM-DD HH:MM:SS` | `2028-09-30 00:00:00` |

### Code/Description Pairs

Many fields come in paired columns (code + human-readable description). All documented code/description pairs:

| Code Column | Description Column | Domain |
|---|---|---|
| `award_type_code` (86) | `award_type` (87) | A/B/C/D |
| `idv_type_code` (88) | `idv_type` (89) | A/B/C/D/E |
| `type_of_contract_pricing_code` (94) | `type_of_contract_pricing` (95) | Multiple codes |
| `action_type_code` (98) | `action_type` (99) | A through Y (see Section 5) |
| `extent_competed_code` (128) | `extent_competed` (129) | A/B/C/D/E/F/G/CDO/NDO |
| `type_of_set_aside_code` (132) | `type_of_set_aside` (133) | NONE/SBA/8A/SBP/HMT/HMP/VSB/ESB/HZC/SDVOSBC/BI/IEE/ISBEE/HZS/SDVOSBS/8AN/RSB/WOSB/EDWOSB/WOSBSS/EDWOSBSS and more |
| `domestic_or_foreign_entity_code` (114) | `domestic_or_foreign_entity` (115) | A/B/C/D |
| `contracting_officers_determination_of_business_size_code` (216) | `contracting_officers_determination_of_business_size` (215) | S/O |

Plus ~30 more paired columns in the procurement policy flags section (cols 112–195).

---

## 7. Full vs Delta File Differences

### Schema Differences

| Property | Full File | Delta File |
|---|---|---|
| Column count | 297 | 299 |
| Extra columns | — | `correction_delete_ind` (col 1), `agency_id` (col 2) |
| Column position | Cols 1–297 are the standard fields | **Delta-only columns are PREPENDED** — cols 1–2 are delta-specific, cols 3–299 match full file cols 1–297 |

**Important:** The directive stated the delta-only columns are appended. **Actual finding: they are prepended at positions 1–2**, shifting all other columns by 2.

### Delta-Only Columns

| Column | Position in Delta | Description | Sample Values |
|---|---|---|---|
| `correction_delete_ind` | 1 | Indicates correction (`C`) or deletion (`D`). **Empty string** for standard correction/update rows (most rows). Only populated with `D` for deletions. | `` (empty), `C`, `D` |
| `agency_id` | 2 | 4-digit agency code for routing/filtering. | `0300` |

### Delta Processing Logic

- **Empty `correction_delete_ind`**: Standard update — upsert the row
- **`C` value**: Explicit correction — upsert the row (same as empty in practice)
- **`D` value**: Deletion — remove the row identified by `contract_transaction_unique_key`

### Bulk Download CSV vs Search API Fields

The `POST /api/v2/search/spending_by_award/` endpoint returns approximately 10 fields per the available documentation:

| Search API Field | Bulk Download Equivalent |
|---|---|
| Award ID | `award_id_piid` |
| Recipient Name | `recipient_name` |
| Start Date | `period_of_performance_start_date` |
| End Date | `period_of_performance_current_end_date` |
| Award Amount | `total_dollars_obligated` or `current_total_value_of_award` |
| Awarding Agency | `awarding_agency_name` |
| Awarding Sub Agency | `awarding_sub_agency_name` |
| Award Type | `award_type` |
| Funding Agency | `funding_agency_name` |
| Funding Sub Agency | `funding_sub_agency_name` |

The bulk download provides **297 columns vs ~10 from the search API** — approximately 30x more data per transaction.

---

## 8. Data Volume Expectations

### Row Counts (Confirmed)

| File | Data Rows |
|---|---|
| `FY2026_All_Contracts_Full_20260307_1.csv` | **1,000,000** |
| `FY2026_All_Contracts_Full_20260307_2.csv` | **340,862** |
| **FY2026 Full Total** | **1,340,862** |

This covers Oct 2025 – early Mar 2026 (~5 months of FY2026).

### Extrapolations

| Metric | Estimate |
|---|---|
| Full FY2026 (12 months) | ~3.0–3.2 million transactions |
| Full FY file size (12 months) | ~6–7 GB across 3–4 CSV files |
| All-FY delta file | ~5.5 GB across 3 CSVs (covers corrections/updates across all fiscal years) |

### Monthly Archive Availability

Per the API documentation, `POST /api/v2/bulk_download/list_monthly_files/` lists monthly archive files. From the API docs:
- Lists monthly files associated with requested parameters
- Monthly archives provide incremental snapshots by fiscal year and agency
- Available for both contracts and assistance awards

### File Split Behavior

Files are split at **1,000,000 rows per CSV** (confirmed: first file has exactly 1,000,000 data rows, remainder goes to second file).

---

## 9. Schema Design Implications

### Primary Key

`contract_transaction_unique_key` — confirmed unique per row. This is the natural primary key.

### Recommended Storage Approach

**Store all 297 columns as TEXT** — same strategy as SAM.gov. Rationale:
- Keeps ingestion lossless — no data lost to type coercion
- Dollar amounts, dates, and booleans can be cast at query time
- 297-column width is manageable (SAM.gov uses 142 columns with no issues; Postgres handles wide tables well)
- Avoids parsing edge cases during ingestion (mixed date formats in col 26, empty vs zero in dollar fields)

### Table Schema

```
usaspending_contracts (
    -- All 297 CSV columns stored as TEXT
    contract_transaction_unique_key TEXT,
    contract_award_unique_key TEXT,
    award_id_piid TEXT,
    ... (294 more columns) ...

    -- Delta-only columns (also TEXT, nullable)
    correction_delete_ind TEXT,
    agency_id TEXT,

    -- Extract metadata (same pattern as SAM.gov)
    extract_date DATE NOT NULL,
    extract_type TEXT NOT NULL,         -- 'FULL' or 'DELTA'
    source_filename TEXT NOT NULL,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    row_position INTEGER NOT NULL
)
```

### Composite Unique Key

```sql
UNIQUE (extract_date, contract_transaction_unique_key)
```

This supports loading multiple snapshots (e.g., monthly full downloads) without collision.

### Indexes (Recommended)

```sql
-- Primary lookup
CREATE INDEX idx_usc_transaction_key ON usaspending_contracts (contract_transaction_unique_key);
-- Award grouping
CREATE INDEX idx_usc_award_key ON usaspending_contracts (contract_award_unique_key);
-- SAM.gov join
CREATE INDEX idx_usc_recipient_uei ON usaspending_contracts (recipient_uei);
-- Time-series queries
CREATE INDEX idx_usc_action_date ON usaspending_contracts (action_date);
-- Agency filtering
CREATE INDEX idx_usc_awarding_agency ON usaspending_contracts (awarding_agency_code);
-- NAICS filtering
CREATE INDEX idx_usc_naics ON usaspending_contracts (naics_code);
```

### Business Type Flag Columns

The 86 boolean flag columns (196–284, excluding cols 215, 216, 234) are high-value for filtering but mostly `f`. Future optimization options:
- **JSONB consolidation:** Collapse all `t` flags into a single `business_type_flags JSONB` column for more efficient storage and querying
- **Materialized boolean columns:** Cast `t`/`f` to actual `BOOLEAN` type for the most commonly queried flags (e.g., `veteran_owned_business`, `woman_owned_business`, `small_disadvantaged_business`)

For initial ingestion, store as TEXT and optimize later.

### Delta Ingestion Strategy

1. Delta-only columns (`correction_delete_ind`, `agency_id`) are prepended at positions 1–2, shifting all standard columns by 2
2. Ingestion code must handle both schemas: detect 297 vs 299 columns and adjust column mapping
3. For `correction_delete_ind = 'D'`, mark the matching `contract_transaction_unique_key` as deleted rather than physically removing (soft delete with a `deleted_at` timestamp)

### Comparison with SAM.gov

| Property | SAM.gov | USASpending |
|---|---|---|
| Columns | 142 | 297 |
| Delimiter | Pipe (`|`) | Comma (CSV) |
| Header row | No | Yes |
| Boolean format | N/A | `t`/`f` |
| Multi-value fields | None | Semicolon-delimited (cols 41–44, 17) |
| Primary key | `unique_entity_id` | `contract_transaction_unique_key` |
| Join key | `unique_entity_id` | `recipient_uei` → SAM.gov `unique_entity_id` |
| Row count (current load) | 867K entities | 1.34M transactions (FY2026 partial) |
| File encoding | ASCII | ASCII |

---

**End of USASpending.gov Bulk Download Schema Comprehension**
