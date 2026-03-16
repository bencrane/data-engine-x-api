# Executor Directive: USASpending.gov Bulk Download Schema Comprehension

**Context:** You are working on `data-engine-x-api`. Read `CLAUDE.md` before starting.

**Scope clarification on autonomy:** You are expected to make strong engineering decisions within the scope defined below. What you must not do is drift outside this scope, run deploy commands, or take actions not covered by this directive. Within scope, use your best judgment.

**Background:** We are adding USASpending.gov federal contract award data as a new data source for data-engine-x, alongside the SAM.gov entity registration data we have already ingested (867K entities loaded). Before building any tables or ingestion pipelines, we need a complete schema comprehension of the USASpending bulk download CSV format — the same treatment we gave SAM.gov in `docs/SAM_GOV_EXTRACT_SCHEMA_COMPREHENSION.md`.

Real bulk download files are already on disk. No API calls are needed.

---

## Reference Documents (Read Before Starting)

**Must read — prior test results:**
- `docs/USASPENDING_SAM_API_TEST_REPORT.md` — API test report with sample data, field observations, endpoint quirks, pagination behavior
- `docs/BULK_DATA_INSPECTION_REPORT.md` — Bulk download inspection from a prior test (reported 242 columns — actual count is 297, see below)

**Must read — USASpending API documentation:**
- All files in `api-reference-docs-new/usa-spending.gov/` — read every file in every subdirectory. Key sections:
  - `01-general/` — introductory tutorial, API usage patterns
  - `02-endpoints-and-methods/07-bulk-download/` — bulk download endpoint
  - `02-endpoints-and-methods/09-download/` — download endpoints
  - `02-endpoints-and-methods/18-search/` — search endpoint field definitions
  - `02-endpoints-and-methods/05-awards/` — award detail response schema
  - `02-endpoints-and-methods/15-recipient/` — recipient detail schema
  - `02-endpoints-and-methods/16-references/` — data dictionary endpoint

**Must read — SAM.gov comprehension report (format reference):**
- `docs/SAM_GOV_EXTRACT_SCHEMA_COMPREHENSION.md` — This is the template for the level of detail expected.

---

## Data Sources (Already On Disk)

**Do not make any API calls for this directive.** The files are downloaded.

### Full FY2026 Contracts

**ZIP:** `/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip`

Contents:
- `FY2026_All_Contracts_Full_20260307_1.csv` — 2,125,169,552 bytes (2.1 GB)
- `FY2026_All_Contracts_Full_20260307_2.csv` — 724,510,285 bytes (725 MB)

**Column count: 297** (confirmed from header row). Has a header row (first line = column names).

### Delta (All Fiscal Years)

**ZIP:** `/Users/benjamincrane/Downloads/FY(All)_All_Contracts_Delta_20260306.zip`

Contents:
- `FY(All)_All_Contracts_Delta_20260308_1.csv` — 2.4 GB
- `FY(All)_All_Contracts_Delta_20260308_2.csv` — 2.5 GB
- `FY(All)_All_Contracts_Delta_20260308_3.csv` — 643 MB

**Column count: 299** (297 base + 2 delta-only columns: `agency_id`, `correction_delete_ind`).

### Pre-Verified Column List (Full File — 297 Columns)

These are the actual CSV header names from `FY2026_All_Contracts_Full_20260307_1.csv`, in order:

```
1. contract_transaction_unique_key
2. contract_award_unique_key
3. award_id_piid
4. modification_number
5. transaction_number
6. parent_award_agency_id
7. parent_award_agency_name
8. parent_award_id_piid
9. parent_award_modification_number
10. federal_action_obligation
11. total_dollars_obligated
12. total_outlayed_amount_for_overall_award
13. base_and_exercised_options_value
14. current_total_value_of_award
15. base_and_all_options_value
16. potential_total_value_of_award
17. disaster_emergency_fund_codes_for_overall_award
18. outlayed_amount_from_COVID-19_supplementals_for_overall_award
19. obligated_amount_from_COVID-19_supplementals_for_overall_award
20. outlayed_amount_from_IIJA_supplemental_for_overall_award
21. obligated_amount_from_IIJA_supplemental_for_overall_award
22. action_date
23. action_date_fiscal_year
24. period_of_performance_start_date
25. period_of_performance_current_end_date
26. period_of_performance_potential_end_date
27. ordering_period_end_date
28. solicitation_date
29. awarding_agency_code
30. awarding_agency_name
31. awarding_sub_agency_code
32. awarding_sub_agency_name
33. awarding_office_code
34. awarding_office_name
35. funding_agency_code
36. funding_agency_name
37. funding_sub_agency_code
38. funding_sub_agency_name
39. funding_office_code
40. funding_office_name
41. treasury_accounts_funding_this_award
42. federal_accounts_funding_this_award
43. object_classes_funding_this_award
44. program_activities_funding_this_award
45. foreign_funding
46. foreign_funding_description
47. sam_exception
48. sam_exception_description
49. recipient_uei
50. recipient_duns
51. recipient_name
52. recipient_name_raw
53. recipient_doing_business_as_name
54. cage_code
55. recipient_parent_uei
56. recipient_parent_duns
57. recipient_parent_name
58. recipient_parent_name_raw
59. recipient_country_code
60. recipient_country_name
61. recipient_address_line_1
62. recipient_address_line_2
63. recipient_city_name
64. prime_award_transaction_recipient_county_fips_code
65. recipient_county_name
66. prime_award_transaction_recipient_state_fips_code
67. recipient_state_code
68. recipient_state_name
69. recipient_zip_4_code
70. prime_award_transaction_recipient_cd_original
71. prime_award_transaction_recipient_cd_current
72. recipient_phone_number
73. recipient_fax_number
74. primary_place_of_performance_country_code
75. primary_place_of_performance_country_name
76. primary_place_of_performance_city_name
77. prime_award_transaction_place_of_performance_county_fips_code
78. primary_place_of_performance_county_name
79. prime_award_transaction_place_of_performance_state_fips_code
80. primary_place_of_performance_state_code
81. primary_place_of_performance_state_name
82. primary_place_of_performance_zip_4
83. prime_award_transaction_place_of_performance_cd_original
84. prime_award_transaction_place_of_performance_cd_current
85. award_or_idv_flag
86. award_type_code
87. award_type
88. idv_type_code
89. idv_type
90. multiple_or_single_award_idv_code
91. multiple_or_single_award_idv
92. type_of_idc_code
93. type_of_idc
94. type_of_contract_pricing_code
95. type_of_contract_pricing
96. transaction_description
97. prime_award_base_transaction_description
98. action_type_code
99. action_type
100. solicitation_identifier
101. number_of_actions
102. inherently_governmental_functions
103. inherently_governmental_functions_description
104. product_or_service_code
105. product_or_service_code_description
106. contract_bundling_code
107. contract_bundling
108. dod_claimant_program_code
109. dod_claimant_program_description
110. naics_code
111. naics_description
112. recovered_materials_sustainability_code
113. recovered_materials_sustainability
114. domestic_or_foreign_entity_code
115. domestic_or_foreign_entity
116. dod_acquisition_program_code
117. dod_acquisition_program_description
118. information_technology_commercial_item_category_code
119. information_technology_commercial_item_category
120. epa_designated_product_code
121. epa_designated_product
122. country_of_product_or_service_origin_code
123. country_of_product_or_service_origin
124. place_of_manufacture_code
125. place_of_manufacture
126. subcontracting_plan_code
127. subcontracting_plan
128. extent_competed_code
129. extent_competed
130. solicitation_procedures_code
131. solicitation_procedures
132. type_of_set_aside_code
133. type_of_set_aside
134. evaluated_preference_code
135. evaluated_preference
136. research_code
137. research
138. fair_opportunity_limited_sources_code
139. fair_opportunity_limited_sources
140. other_than_full_and_open_competition_code
141. other_than_full_and_open_competition
142. number_of_offers_received
143. commercial_item_acquisition_procedures_code
144. commercial_item_acquisition_procedures
145. small_business_competitiveness_demonstration_program
146. simplified_procedures_for_certain_commercial_items_code
147. simplified_procedures_for_certain_commercial_items
148. a76_fair_act_action_code
149. a76_fair_act_action
150. fed_biz_opps_code
151. fed_biz_opps
152. local_area_set_aside_code
153. local_area_set_aside
154. price_evaluation_adjustment_preference_percent_difference
155. clinger_cohen_act_planning_code
156. clinger_cohen_act_planning
157. materials_supplies_articles_equipment_code
158. materials_supplies_articles_equipment
159. labor_standards_code
160. labor_standards
161. construction_wage_rate_requirements_code
162. construction_wage_rate_requirements
163. interagency_contracting_authority_code
164. interagency_contracting_authority
165. other_statutory_authority
166. program_acronym
167. parent_award_type_code
168. parent_award_type
169. parent_award_single_or_multiple_code
170. parent_award_single_or_multiple
171. major_program
172. national_interest_action_code
173. national_interest_action
174. cost_or_pricing_data_code
175. cost_or_pricing_data
176. cost_accounting_standards_clause_code
177. cost_accounting_standards_clause
178. government_furnished_property_code
179. government_furnished_property
180. sea_transportation_code
181. sea_transportation
182. undefinitized_action_code
183. undefinitized_action
184. consolidated_contract_code
185. consolidated_contract
186. performance_based_service_acquisition_code
187. performance_based_service_acquisition
188. multi_year_contract_code
189. multi_year_contract
190. contract_financing_code
191. contract_financing
192. purchase_card_as_payment_method_code
193. purchase_card_as_payment_method
194. contingency_humanitarian_or_peacekeeping_operation_code
195. contingency_humanitarian_or_peacekeeping_operation
196. alaskan_native_corporation_owned_firm
197. american_indian_owned_business
198. indian_tribe_federally_recognized
199. native_hawaiian_organization_owned_firm
200. tribally_owned_firm
201. veteran_owned_business
202. service_disabled_veteran_owned_business
203. woman_owned_business
204. women_owned_small_business
205. economically_disadvantaged_women_owned_small_business
206. joint_venture_women_owned_small_business
207. joint_venture_economic_disadvantaged_women_owned_small_bus
208. minority_owned_business
209. subcontinent_asian_asian_indian_american_owned_business
210. asian_pacific_american_owned_business
211. black_american_owned_business
212. hispanic_american_owned_business
213. native_american_owned_business
214. other_minority_owned_business
215. contracting_officers_determination_of_business_size
216. contracting_officers_determination_of_business_size_code
217. emerging_small_business
218. community_developed_corporation_owned_firm
219. labor_surplus_area_firm
220. us_federal_government
221. federally_funded_research_and_development_corp
222. federal_agency
223. us_state_government
224. us_local_government
225. city_local_government
226. county_local_government
227. inter_municipal_local_government
228. local_government_owned
229. municipality_local_government
230. school_district_local_government
231. township_local_government
232. us_tribal_government
233. foreign_government
234. organizational_type
235. corporate_entity_not_tax_exempt
236. corporate_entity_tax_exempt
237. partnership_or_limited_liability_partnership
238. sole_proprietorship
239. small_agricultural_cooperative
240. international_organization
241. us_government_entity
242. community_development_corporation
243. domestic_shelter
244. educational_institution
245. foundation
246. hospital_flag
247. manufacturer_of_goods
248. veterinary_hospital
249. hispanic_servicing_institution
250. receives_contracts
251. receives_financial_assistance
252. receives_contracts_and_financial_assistance
253. airport_authority
254. council_of_governments
255. housing_authorities_public_tribal
256. interstate_entity
257. planning_commission
258. port_authority
259. transit_authority
260. subchapter_scorporation
261. limited_liability_corporation
262. foreign_owned
263. for_profit_organization
264. nonprofit_organization
265. other_not_for_profit_organization
266. the_ability_one_program
267. private_university_or_college
268. state_controlled_institution_of_higher_learning
269. 1862_land_grant_college
270. 1890_land_grant_college
271. 1994_land_grant_college
272. minority_institution
273. historically_black_college
274. tribal_college
275. alaskan_native_servicing_institution
276. native_hawaiian_servicing_institution
277. school_of_forestry
278. veterinary_college
279. dot_certified_disadvantage
280. self_certified_small_disadvantaged_business
281. small_disadvantaged_business
282. c8a_program_participant
283. historically_underutilized_business_zone_hubzone_firm
284. sba_certified_8a_joint_venture
285. highly_compensated_officer_1_name
286. highly_compensated_officer_1_amount
287. highly_compensated_officer_2_name
288. highly_compensated_officer_2_amount
289. highly_compensated_officer_3_name
290. highly_compensated_officer_3_amount
291. highly_compensated_officer_4_name
292. highly_compensated_officer_4_amount
293. highly_compensated_officer_5_name
294. highly_compensated_officer_5_amount
295. usaspending_permalink
296. initial_report_date
297. last_modified_date
```

### Delta-Only Additional Columns (2 extra, total 299)

The delta file has the same 297 columns plus:
- `agency_id` — agency identifier for routing
- `correction_delete_ind` — indicates whether the row is a correction (`C`) or deletion (`D`). Critical for delta processing.

### Pre-Verified Sample Data (5 Rows, Key Fields)

```
Row 1: PIID=89303020DMA000020 mod=P00010 action=M (OTHER ADMIN) | $0.00 obligation | UEI=GHDAN1FNERA8 | THE MATTHEWS GROUP INC | NAICS=236220 | DOE | 2025-11-03
Row 2: PIID=36C24824F0020 mod=P00003 action=G (EXERCISE OPTION) | $268,432.70 obligation | UEI=J49CN39QTNW3 | GOVERNMENT SCIENTIFIC SOURCE INC | NAICS=334516 | VA | 2025-10-01
Row 3: PIID=12444223A0042 mod=P00002 action=G (EXERCISE OPTION) | $0.00 obligation | UEI=ZVNNZ9ASJDP2 | ECO-RESTORE LLC | NAICS=115310 | USDA | 2025-10-28
Row 4: PIID=1202RZ25K6473 mod=P00011 action=B (SUPPLEMENTAL) | $839.88 obligation | UEI=R5NWZ87HPLX4 | GPC CONSOLIDATED REPORTING | NAICS=457210 | USDA | 2025-10-10
Row 5: PIID=89233125FNA400701 mod=P00002 action=M (OTHER ADMIN) | $0.00 obligation | UEI=WN8JFVZTBCA5 | MINBURN TECHNOLOGY GROUP, LLC | NAICS=541519 | DOE | 2025-10-15
```

Key observations from sample data:
- `recipient_uei` is populated (12-char, matches SAM.gov UEI format)
- `action_type_code`: M = admin action, G = exercise option, B = supplemental agreement
- `federal_action_obligation` is the per-action dollar amount (can be $0 for admin actions)
- `total_dollars_obligated` is the cumulative award obligation
- `modification_number` format: P00010, P00003, etc.
- `contract_transaction_unique_key` appears to be the natural unique key per row
- `contract_award_unique_key` groups all transactions under one award
- Dates are YYYY-MM-DD format
- `last_modified_date` includes timezone: `2025-11-03 16:44:15+00`

---

## Deliverable: Schema Comprehension Report

Save to `docs/USASPENDING_EXTRACT_SCHEMA_COMPREHENSION.md`.

The report must include the following sections, modeled after `docs/SAM_GOV_EXTRACT_SCHEMA_COMPREHENSION.md`:

### Section 1: File Format Details

- File type (CSV), encoding, delimiter, quote character
- Header row presence (yes — unlike SAM.gov)
- File naming conventions: `FY{year}_All_Contracts_Full_{date}_{part}.csv` for full, `FY(All)_All_Contracts_Delta_{date}_{part}.csv` for delta
- Multi-file splits (the full FY2026 download has 2 CSV files, the delta has 3)
- Compression format (ZIP)
- Full file size: ~2.8 GB across 2 CSVs for FY2026
- Delta file size: ~5.5 GB across 3 CSVs for all-FY delta

### Section 2: Complete Field Map (All 297 Columns)

Read the first 20 data rows from `/Users/benjamincrane/Downloads/FY2026_All_Contracts_Full_20260306.zip` (first CSV inside the ZIP) to observe actual data types and patterns for each column.

Also call `GET https://api.usaspending.gov/api/v2/references/data_dictionary/` to get official field definitions. Save the response to `/tmp/usaspending_data_dictionary.json`. **This is the one API call authorized in this directive** — USASpending has no auth and no rate limits.

For every column, document:

| # | Column Name | Data Type | Description | Sample Value |
|---|---|---|---|---|

Group columns logically by category:
- **Award identification** (cols 1-9): unique keys, PIID, parent award, modification number
- **Dollar amounts** (cols 10-21): obligations, outlays, options values, COVID/IIJA supplementals
- **Dates** (cols 22-28): action date, period of performance, solicitation date
- **Awarding/funding agency** (cols 29-44): agency hierarchy (code + name pairs), treasury/federal accounts
- **SAM exception** (cols 45-48): foreign funding, SAM registration exceptions
- **Recipient** (cols 49-73): UEI, DUNS (deprecated), name, parent, address, phone/fax, congressional district
- **Place of performance** (cols 74-84): country, city, state, zip, congressional district
- **Award type & IDV** (cols 85-95): award/IDV flag, type codes, contract pricing
- **Transaction details** (cols 96-101): description, action type, solicitation ID
- **Product/service classification** (cols 102-111): PSC, NAICS, contract bundling, DoD codes
- **Procurement policy flags** (cols 112-195): ~80 coded fields for competition, set-aside, regulatory compliance, contract characteristics
- **Business type flags** (cols 196-284): ~89 boolean/flag columns for recipient business classifications (veteran-owned, woman-owned, minority-owned, small business types, organizational types, educational institutions, government entities, etc.)
- **Executive compensation** (cols 285-294): top 5 highly compensated officers (name + amount pairs)
- **Metadata** (cols 295-297): USASpending permalink, initial report date, last modified date

### Section 3: Key Fields for Our Use Case

Call out these specific fields with detailed notes:
- `contract_transaction_unique_key` (col 1) — the natural unique key per transaction row
- `contract_award_unique_key` (col 2) — groups all transactions under one award
- `recipient_uei` (col 49) — the join key to SAM.gov `unique_entity_id`
- `recipient_name` (col 51) — contractor name
- `award_id_piid` (col 3) — Procurement Instrument Identifier (human-readable award ID)
- Dollar amount fields — explain the difference between:
  - `federal_action_obligation` (col 10) — per-action amount
  - `total_dollars_obligated` (col 11) — cumulative obligation
  - `current_total_value_of_award` (col 14) — current total
  - `base_and_all_options_value` (col 15) — base + all options (potential ceiling)
  - `potential_total_value_of_award` (col 16) — max potential value
- `naics_code` (col 110) and `naics_description` (col 111)
- `awarding_agency_name` (col 30), `awarding_sub_agency_name` (col 32), `awarding_office_name` (col 34)
- `action_date` (col 22) — when the action occurred
- `action_type_code` (col 98) / `action_type` (col 99) — new award vs modification
- `contracting_officers_determination_of_business_size` (col 215) / code (col 216)
- Place of performance: `primary_place_of_performance_state_code` (col 80), city (col 76), zip (col 82)
- `recipient_parent_uei` (col 55) — parent company UEI (also joins to SAM.gov)
- `cage_code` (col 54) — CAGE code (also in SAM.gov data)

### Section 4: SAM.gov Join Key

- Confirm `recipient_uei` maps to SAM.gov `unique_entity_id`
- Note that `recipient_parent_uei` can also join to SAM.gov for parent company lookup
- Note `cage_code` as a secondary join key
- Note any caveats: legacy DUNS records (col 50 `recipient_duns`), null UEIs, SAM exceptions
- Explain how to link: `usaspending.recipient_uei = sam_gov_entities.unique_entity_id`

### Section 5: How Multiple Actions on the Same Award Work

- `contract_transaction_unique_key` is unique per row (per action)
- `contract_award_unique_key` groups all actions on the same award
- Same `award_id_piid` appears with different `modification_number` and `action_date` values
- `action_type_code` values observed: M (admin action), G (exercise option), B (supplemental agreement) — document all known codes
- `federal_action_obligation` is the **incremental** amount for that action (can be $0 for admin changes)
- `total_dollars_obligated` is the **cumulative** amount for the award as of that action
- Primary key for the table should be `contract_transaction_unique_key` (already unique per row)
- To get the "latest state" of an award: filter to the most recent `action_date` per `contract_award_unique_key`

### Section 6: Fields Requiring Special Parsing

- Columns 196-284: ~89 business type flag columns — determine if these are boolean strings ("t"/"f"), "TRUE"/"FALSE", "Y"/"N", or something else
- Columns 41-44: treasury/federal accounts, object classes, program activities — may contain pipe-delimited or semicolon-delimited lists within a single CSV cell
- Dollar amounts: confirm decimal format, negative values for deobligations
- Date columns: confirm format (YYYY-MM-DD for action_date, timestamp with timezone for last_modified_date)
- `disaster_emergency_fund_codes_for_overall_award` (col 17) — likely a delimited list of DEFC codes
- Coded fields with paired description columns (e.g., `action_type_code` + `action_type`) — document all code/description pairs

### Section 7: Full vs Delta File Differences

- Full file: 297 columns, all FY2026 contract transactions
- Delta file: 299 columns (297 + `agency_id` + `correction_delete_ind`)
- `correction_delete_ind`: `C` = correction (upsert), `D` = deletion (remove). Document this field.
- Multi-file splits: both full and delta split across multiple CSVs. Same schema per file, just row pagination.
- Also compare bulk download CSV fields vs the ~23 fields from `POST /api/v2/search/spending_by_award/`

### Section 8: Data Volume Expectations

- FY2026 full download: ~2.8 GB across 2 CSVs (Oct 2025 - March 2026, ~6 months)
- Extrapolated full FY: ~5-6 GB, likely millions of transaction rows
- Delta download (all FYs): ~5.5 GB across 3 CSVs
- Monthly archive availability: document what `POST /api/v2/bulk_download/list_monthly_files/` returns (from the API docs, do not call it)
- Row count: read and report the actual row count from the first CSV (or estimate from file size)

### Section 9: Schema Design Implications

Based on all findings, provide:
- Primary key: `contract_transaction_unique_key` (confirmed unique per row)
- Recommended approach: store all 297 columns as TEXT (same strategy as SAM.gov) — keeps ingestion lossless
- Delta-only columns (`correction_delete_ind`, `agency_id`) should also be included
- Extract metadata columns needed (same pattern as SAM.gov): `extract_date`, `extract_type` (FULL/DELTA), `source_filename`, `ingested_at`, `row_position`
- Composite unique key: `(extract_date, contract_transaction_unique_key)` to support loading multiple snapshots
- Business type flag columns (89 of them) — note that these are high-value for filtering but mostly boolean; future work could normalize into a JSONB column
- The 297-column width is manageable (SAM.gov was 142 and works fine; Postgres handles wide tables)

---

## What is NOT in scope

- No database tables. No migrations. No ingestion code.
- No modifications to any existing code.
- No SAM.gov API calls.
- No deploy commands. Do not push.
- The one authorized API call is `GET https://api.usaspending.gov/api/v2/references/data_dictionary/` for field definitions.

## Commit convention

One commit for the report. Do not push.

## When done

Report back with:
(a) Data sources used (local CSV files, data dictionary API, or both)
(b) Total column count confirmed (297 full, 299 delta)
(c) Key field summary: recipient_uei presence, dollar amount fields, primary key recommendation
(d) The SAM.gov join key confirmation
(e) Row count from the FY2026 full file
(f) Business type flag column format (boolean representation)
(g) Anything surprising or concerning about the schema
