# SAM.gov Extract Schema Comprehension

**Date:** 2026-03-16
**Sources read:**
- `SAM_MASTER_EXTRACT_MAPPING_Feb2025.json` (primary — 368 columns)
- `SAM_REPS_AND_CERTS_MAPPING.json` (FAR/DFARS provision mapping)
- `SAM_Exclusions_Public_Extract_Layout_V2.json` (31-column exclusions extract)
- `February_2025_Data_Dictionary.docx` (field definitions, valid values)
- Entity Management API docs (`01-entity-management-api/` — endpoints, response schema, sensitivity levels, rate limits)

---

## 1. Extract File Format

| Property | Value |
|---|---|
| File type | `.dat` (pipe-delimited flat file), delivered in `.ZIP` |
| Delimiter | Pipe `\|` between columns |
| Repeating fields | Tilde `~` separates multiple values within a single column |
| Caret separator | `^` used within disaster response string (nested sub-fields) |
| Header row | **No** — positional columns only, matched by column_order |
| Encoding | UTF-8 |
| Total columns | **362** data columns + 6 reserved flex fields (347-361) + end-of-record indicator (362) = **368 total positions** |
| End of record | Column 362: `!end` marker (max 4 chars) |

### File Naming

**Monthly full dump:** `SAM_PUBLIC_MONTHLY_YYYYMMDD.dat` (or similar; contains all records with SAM Extract Code `A` (Active) or `E` (Expired))

**Daily delta:** Same format, SAM Extract Code values:
- `1` = Deleted/Deactivated — sends only UEI, EFT, CAGE, DODAAC, Extract Code, Purpose
- `2` = New Active — sends complete record
- `3` = Updated Active — sends complete record
- `4` = Expired — sends only UEI, EFT, CAGE, DODAAC, Extract Code, Purpose

### Sensitivity Tiers

The extract has **three file variants** based on access level:
- **Public** — ~172 columns populated (names, addresses, NAICS, business types, POC names/addresses)
- **FOUO (CUI)** — adds **196 additional columns**: POC email/phone/fax, parent hierarchy, employee count, revenue, security levels, EDI, EVS monitoring
- **Sensitive** — adds banking/TIN/SSN fields on top of FOUO

Our public API key returns **Public-level data only**. This is why the JSON API test showed no email, phone, employee count, or revenue.

---

## 2. Complete Field Map (368 columns)

### Registration & Identity (Columns 1-15)

| Col | Field | Type | Max | Sensitivity | Notes |
|---|---|---|---|---|---|
| 1 | UNIQUE ENTITY ID | STRING | 12 | Public | 12-char alphanumeric UEI |
| 2 | BLANK (DEPRECATED) | STRING | — | Public | Former DUNS slot |
| 3 | ENTITY EFT INDICATOR | STRING | 4 | Public | Multi-bank account identifier |
| 4 | CAGE CODE | STRING | 5 | Public | |
| 5 | DODAAC | STRING | 9 | Public | DoD only |
| 6 | SAM EXTRACT CODE | STRING | 1 | Public | A/E (monthly), 1/2/3/4 (daily) |
| 7 | PURPOSE OF REGISTRATION | STRING | 2 | Public | Z1-Z5 |
| 8 | INITIAL REGISTRATION DATE | YYYYMMDD | 8 | Public | |
| 9 | REGISTRATION EXPIRATION DATE | YYYYMMDD | 8 | Public | |
| 10 | LAST UPDATE DATE | YYYYMMDD | 8 | Public | |
| 11 | ACTIVATION DATE | YYYYMMDD | 8 | Public | |
| 12 | LEGAL BUSINESS NAME | STRING | 120 | Public | |
| 13 | DBA NAME | STRING | 120 | Public | |
| 14 | ENTITY DIVISION NAME | STRING | 60 | Public | |
| 15 | ENTITY DIVISION NUMBER | STRING | 10 | Public | |

### Physical Address (Columns 16-24)

| Col | Field | Type | Max | Sensitivity |
|---|---|---|---|---|
| 16 | PHYSICAL ADDRESS LINE 1 | STRING | 150 | Public |
| 17 | PHYSICAL ADDRESS LINE 2 | STRING | 150 | Public |
| 18 | PHYSICAL ADDRESS CITY | STRING | 40 | Public |
| 19 | PHYSICAL ADDRESS PROVINCE OR STATE | STRING | 55 | Public |
| 20 | PHYSICAL ADDRESS ZIP/POSTAL CODE | STRING | 50 | Public |
| 21 | PHYSICAL ADDRESS ZIP CODE +4 | Numeric | 4 | Public |
| 22 | PHYSICAL ADDRESS COUNTRY CODE | STRING | 3 | Public |
| 23 | PHYSICAL ADDRESS CONGRESSIONAL DISTRICT | Numeric | 10 | Public |
| 24 | D&B OPEN DATA FLAG | Y/N | 1 | Public |

### Entity Characteristics (Columns 25-35)

| Col | Field | Type | Max | Sensitivity | Notes |
|---|---|---|---|---|---|
| 25 | ENTITY START DATE | YYYYMMDD | 8 | Public | |
| 26 | FISCAL YEAR END CLOSE DATE | MMDD | 4 | Public | |
| 27 | COMPANY SECURITY LEVEL | STRING | 2 | **FOUO** | 90/92/93/94 |
| 28 | HIGHEST EMPLOYEE SECURITY LEVEL | STRING | 2 | **FOUO** | 90/92/93/94 |
| 29 | ENTITY URL | STRING | 200 | Public | **Website!** |
| 30 | ENTITY STRUCTURE | STRING | 2 | Public | 2J/2K/2L/8H/2A/CY/X6/ZZ |
| 31 | STATE OF INCORPORATION | STRING | 2 | Public | |
| 32 | COUNTRY OF INCORPORATION | STRING | 3 | Public | |
| 33 | BUSINESS TYPE COUNTER | Numeric | 4 | Public | Count of business types |
| 34 | BUS TYPE STRING | ~SEP | 220 | Public | Tilde-separated business type codes |
| 35 | AGENCY BUSINESS PURPOSE | STRING | 1 | **FOUO** | IGT only (1/2/3) |

### NAICS & PSC (Columns 36-40)

| Col | Field | Type | Max | Sensitivity | Notes |
|---|---|---|---|---|---|
| 36 | PRIMARY NAICS | STRING | 6 | Public | |
| 37 | NAICS CODE COUNTER | Numeric | 4 | Public | |
| 38 | NAICS CODE STRING | ~SEP | 12000 | Public | Format: `XXXXXXY~XXXXXXN~...` (6-digit code + Y/N small biz flag + optional N exception) |
| 39 | PSC CODE COUNTER | Numeric | 4 | Public | |
| 40 | PSC CODE STRING | ~SEP | 2500 | Public | Tilde-separated PSC codes |

**NAICS String format:** Each NAICS entry in the tilde-separated string is: `{6-digit-code}{Y|N}` where Y/N = SBA small business. If there's an exception: `{code}{Y|N}{N}` (second char = exception flag). Example: `333611Y~333612N~541340YN` (last one has exception).

### Financial & Mailing (Columns 41-49)

| Col | Field | Type | Max | Sensitivity |
|---|---|---|---|---|
| 41 | CREDIT CARD USAGE | Y/N | 1 | Public |
| 42 | CORRESPONDENCE FLAG | M/F/E | 1 | Public |
| 43 | MAILING ADDRESS LINE 1 | STRING | 150 | Public |
| 44 | MAILING ADDRESS LINE 2 | STRING | 150 | Public |
| 45 | MAILING ADDRESS CITY | STRING | 40 | Public |
| 46 | MAILING ADDRESS ZIP/POSTAL CODE | STRING | 50 | Public |
| 47 | MAILING ADDRESS ZIP CODE +4 | Numeric | 4 | Public |
| 48 | MAILING ADDRESS COUNTRY | STRING | 3 | Public |
| 49 | MAILING ADDRESS STATE OR PROVINCE | STRING | 55 | Public |

### Points of Contact (Columns 50-170)

**8 POC slots**, each with 16 fields (name, title, address, phone, fax, email). POC slots:

| POC Slot | Columns | Name Public? | Phone | Email | Sensitivity |
|---|---|---|---|---|---|
| **Govt Business POC** | 50-65 | Public | **FOUO** (61-64) | **FOUO** (65) | Mixed |
| **Alt Govt Business POC** | 66-81 | Public | **FOUO** (77-80) | **FOUO** (81) | Mixed |
| **Past Performance POC** | 82-97 | Public | **FOUO** (93-96) | **FOUO** (97) | Mixed |
| **Alt Past Performance POC** | 98-113 | Public | **FOUO** (109-112) | **FOUO** (113) | Mixed |
| **Electronic Business POC** | 114-129 | Public | **FOUO** (125-128) | **FOUO** (129) | Mixed |
| **Alt Electronic Business POC** | 130-145 | Public | **FOUO** (141-144) | **FOUO** (145) | Mixed |
| **Party Performing Cert POC** | 146-161 | **FOUO** | **FOUO** (157-160) | **FOUO** (161) | All FOUO |
| **Sole Proprietorship POC** | 162-170 | **FOUO** | **FOUO** (166-169) | **FOUO** (170) | All FOUO |

**Each POC slot fields (using Govt Business POC as example):**

| Offset | Field | Max | Sensitivity |
|---|---|---|---|
| +0 | FIRST NAME | 65 | Public |
| +1 | MIDDLE INITIAL | 3 | Public |
| +2 | LAST NAME | 65 | Public |
| +3 | TITLE | 50 | Public |
| +4 | ST ADD 1 | 150 | Public |
| +5 | ST ADD 2 | 150 | Public |
| +6 | CITY | 40 | Public |
| +7 | ZIP/POSTAL CODE | 50 | Public |
| +8 | ZIP CODE +4 | 4 | Public |
| +9 | COUNTRY CODE | 3 | Public |
| +10 | STATE OR PROVINCE | 55 | Public |
| +11 | U.S. PHONE | 30 | **FOUO** |
| +12 | U.S. PHONE EXT | 25 | **FOUO** |
| +13 | NON-U.S. PHONE | 30 | **FOUO** |
| +14 | FAX U.S. ONLY | 30 | **FOUO** |
| +15 | EMAIL | 80 | **FOUO** |

### Parent Hierarchy (Columns 171-209) — ALL FOUO

| Parent Level | Name Col | UEI Col | Address Cols | Phone Col |
|---|---|---|---|---|
| **Immediate Parent** | 171 | 172 | 173-178 | 179 |
| **HQ Parent** | 180 | 181 | 183-188 | 189 |
| **Domestic Parent** | 190 | 191 | 193-198 | 199 |
| **Ultimate Parent** | 200 | 201 | 203-208 | 209 |

(Columns 182, 192, 202 are deprecated DUNS blanks)

### EVS Monitoring (Columns 210-220) — ALL FOUO

| Col | Field |
|---|---|
| 210 | EVS OUT OF BUSINESS INDICATOR |
| 211 | EVS MONITORING LAST UPDATED |
| 212 | EVS MONITORING STATUS |
| 213 | EVS MONITORING LEGAL BUSINESS NAME |
| 214 | EVS MONITORING DBA |
| 215-220 | EVS MONITORING ADDRESS (6 fields) |

### EDI Information (Columns 221-235) — ALL FOUO

| Col | Field |
|---|---|
| 221 | EDI (Y/N) |
| 222 | EDI VAN PROVIDER |
| 223 | ISA QUALIFIER |
| 224 | ISA IDENTIFIER |
| 225 | FUNCTIONAL GROUP IDENTIFIER |
| 226 | 820S REQUEST FLAG |
| 227-235 | EDI POC (name, phone, fax, email) |

### Tax & Financial (Columns 236-258) — Mixed Sensitivity

| Col | Field | Sensitivity | Notes |
|---|---|---|---|
| 236 | TAX IDENTIFIER TYPE | Sensitive | |
| 237 | TAX IDENTIFIER NUMBER | Sensitive | SSN/TIN/EIN |
| **238** | **AVERAGE NUMBER OF EMPLOYEES** | **FOUO** | **Worldwide employees** |
| **239** | **AVERAGE ANNUAL REVENUE** | **FOUO** | **5-year average** |
| 240 | FINANCIAL INSTITUTE | Sensitive | Bank name |
| 241 | ACCOUNT NUMBER | Sensitive | |
| 242 | ABA ROUTING ID | Sensitive | |
| 243 | ACCOUNT TYPE | Sensitive | C=Checking, S=Savings |
| 244 | LOCKBOX NUMBER | Sensitive | |
| 245 | AUTHORIZATION DATE | Sensitive | |
| 246 | EFT WAIVER | Sensitive | |
| 247-250 | ACH phone/fax/email | Sensitive | |
| 251-258 | REMITTANCE address | Sensitive | |

### Accounts Receivable POC (Columns 259-267) — ALL FOUO

Name, phone, fax, email for AR contact.

### Accounts Payable POC (Columns 268-283) — ALL FOUO

Full name, address, phone, fax, email for AP contact.

### Additional Fields (Columns 284-308)

| Col | Field | Sensitivity | Notes |
|---|---|---|---|
| 284 | MPIN | Sensitive | Deprecated |
| 285 | NAICS EXCEPTION COUNTER | Public | |
| 286 | NAICS EXCEPTION STRING | Public | ~SEP format |
| 287 | DEBT SUBJECT TO OFFSET FLAG | Public | Y/N |
| 288 | EXCLUSION STATUS FLAG | Public | Y/N |
| 289 | SBA BUSINESS TYPES COUNTER | Public | |
| 290 | SBA BUSINESS TYPES STRING | Public | ~SEP: `{code}~{desc}~{entry_date}~{exit_date}` |
| 291 | SAM NUMERICS COUNTER | FOUO | |
| 292 | SAM NUMERICS CODE STRING | FOUO | ~SEP |
| 293 | NO PUBLIC DISPLAY FLAG | Public | |
| 294 | DISASTER RESPONSE COUNTER | Public | |
| 295 | DISASTER RESPONSE STRING | Public | ~SEP with ^ sub-delimiter |
| 296 | ANNUAL IGT REVENUE | FOUO | IGT registrations only |
| 297 | AGENCY LOCATION CODE | Public | |
| 298 | DISBURSING OFFICE SYMBOL | Public | |
| 299 | MERCHANT ID 1 | Public | |
| 300 | MERCHANT ID 2 | Public | |
| 301 | ACCOUNTING STATION | Public | |
| 302-308 | Federal hierarchy (source, dept, agency, office) | FOUO | |

### Eliminations POC (Columns 309-324) — ALL FOUO

Full name, address, phone, fax, email for Eliminations contact.

### Sales POC (Columns 325-340) — ALL FOUO

Full name, address, phone, fax, email for Sales contact.

### Tail Fields (Columns 341-362)

| Col | Field | Sensitivity |
|---|---|---|
| 341 | TAXPAYER NAME | Sensitive |
| 342 | ENTITY EVS SOURCE | Public |
| 343 | HQ PARENT EVS SOURCE | FOUO |
| 344 | DOMESTIC PARENT EVS SOURCE | FOUO |
| 345 | ULTIMATE PARENT EVS SOURCE | FOUO |
| 346 | IMMEDIATE PARENT EVS SOURCE | FOUO |
| 347-361 | FLEX FIELDS 6-20 | Reserved |
| 362 | END OF RECORD INDICATOR | Public |

---

## 3. Key Fields for Our Use Case

### Identity & Registration

| Field | Column | Notes |
|---|---|---|
| **UEI** | 1 | 12-char alphanumeric, primary key |
| **Legal Business Name** | 12 | Max 120 chars |
| **DBA Name** | 13 | Max 120 chars |
| **CAGE Code** | 4 | 5-char |
| **SAM Extract Code** | 6 | A=Active, E=Expired |
| **Registration Date** | 8 | YYYYMMDD |
| **Expiration Date** | 9 | YYYYMMDD |
| **Last Update Date** | 10 | YYYYMMDD |
| **Activation Date** | 11 | YYYYMMDD |
| **Entity Start Date** | 25 | YYYYMMDD |

### Addresses

| Field | Columns |
|---|---|
| **Physical Address** | 16-22 (line1, line2, city, state, zip, zip+4, country) |
| **Congressional District** | 23 |
| **Mailing Address** | 43-49 (line1, line2, city, zip, zip+4, country, state) |

### Industry Classification

| Field | Column | Notes |
|---|---|---|
| **Primary NAICS** | 36 | 6-digit code |
| **NAICS Code String** | 38 | Tilde-separated, each entry = `{code}{Y\|N}` small biz flag |
| **NAICS Code Counter** | 37 | How many NAICS entries |
| **NAICS Exception String** | 286 | NAICS exception details |
| **PSC Code String** | 40 | Tilde-separated product/service codes |

### Entity Structure & Business Types

| Field | Column | Notes |
|---|---|---|
| **Entity Structure** | 30 | 2J/2K/2L/8H/2A/CY/X6/ZZ |
| **State of Incorporation** | 31 | 2-char state code |
| **Country of Incorporation** | 32 | 3-char country code |
| **Business Type String** | 34 | Tilde-separated codes (e.g. `23~27~2X~A5~LJ~QF`) |
| **SBA Business Types String** | 290 | Tilde-separated: code, description, entry date, exit date |
| **Exclusion Status Flag** | 288 | Y/N |
| **Debt Subject to Offset** | 287 | Y/N |

### Entity URL (Website)

| Field | Column | Notes |
|---|---|---|
| **Entity URL** | 29 | Max 200 chars. Sample: `http://www.usbank.com` |

This field exists and is populated for many entities. Our JSON API test returned `null` because C & C HOME CARE LLC didn't provide one, but it's a real field.

### Points of Contact

| Slot | Name Cols | Email Col | Phone Col | Sensitivity |
|---|---|---|---|---|
| Govt Business POC | 50-53 | **65** | **61** | Name=Public, Contact=**FOUO** |
| Alt Govt Business POC | 66-69 | **81** | **77** | Name=Public, Contact=**FOUO** |
| Past Performance POC | 82-85 | **97** | **93** | Name=Public, Contact=**FOUO** |
| Alt Past Performance POC | 98-101 | **113** | **109** | Name=Public, Contact=**FOUO** |
| Electronic Business POC | 114-117 | **129** | **125** | Name=Public, Contact=**FOUO** |
| Alt Electronic Business POC | 130-133 | **145** | **141** | Name=Public, Contact=**FOUO** |
| Party Performing Cert POC | 146-149 | **161** | **157** | All **FOUO** |
| Sole Proprietorship POC | 162-165 | **170** | **166** | All **FOUO** |

### Email — YES, it exists (14 email columns total, ALL FOUO)

| Column | Email Field |
|---|---|
| 65 | GOVT BUS POC EMAIL |
| 81 | ALT GOVT BUS POC EMAIL |
| 97 | PAST PERF POC EMAIL |
| 113 | ALT PAST PERF POC EMAIL |
| 129 | ELEC BUS POC EMAIL |
| 145 | ALT ELEC POC BUS EMAIL |
| 161 | PARTY PERFORMING CERTIFICATION POC EMAIL |
| 170 | SOLE PROPRIETORSHIP POC EMAIL |
| 235 | EDI POC EMAIL |
| 250 | ACH EMAIL |
| 267 | ACCOUNTS RECEIVABLE POC EMAIL |
| 283 | ACCOUNTS PAYABLE POC EMAIL |
| 324 | ELIMINATIONS POC EMAIL |
| 340 | SALES POC EMAIL |

**ALL email fields are FOUO sensitivity.** They are not available through our current public API key.

### Phone — YES, it exists (32 phone columns total, ALL FOUO)

Each POC slot has U.S. Phone, U.S. Phone Ext, Non-U.S. Phone, and Fax. Plus parent hierarchy phones (179, 189, 199, 209), ACH phones (247-248), and POC-specific phones for EDI, AR, AP, Eliminations, Sales.

**ALL phone fields are FOUO sensitivity.**

### Employee Count & Revenue — YES, they exist (FOUO)

| Column | Field | Sensitivity | Definition |
|---|---|---|---|
| **238** | **AVERAGE NUMBER OF EMPLOYEES** | **FOUO** | Worldwide employees for all affiliates/branches. Must be >= Location Employees. |
| **239** | **AVERAGE ANNUAL REVENUE** | **FOUO** | 5-year average annual receipts, all worldwide affiliates/branches, rounded to nearest dollar. |

### Parent Company Hierarchy — YES, 4 levels (ALL FOUO)

| Level | Name Col | UEI Col | Phone Col |
|---|---|---|---|
| Immediate Parent | 171 | 172 | 179 |
| HQ Parent | 180 | 181 | 189 |
| Domestic Parent | 190 | 191 | 199 |
| Ultimate Parent | 200 | 201 | 209 |

---

## 4. Fields in Extract but NOT in JSON API (or Vice Versa)

### In Extract but NOT in our JSON API test

These fields exist in the bulk extract but were **not returned** by the JSON API with our public API key:

| Field | Column(s) | Reason Not in API |
|---|---|---|
| **Email (all 14 fields)** | 65,81,97,113,129,145,161,170,235,250,267,283,324,340 | **FOUO** — requires Federal System Account with "Read FOUO" permission |
| **Phone (all 32 fields)** | 61-64,77-80,93-96,109-112,125-128,141-144,157-160,166-169,179,189,199,209,231-234,247-249,263-266,279-282,320-323,336-339 | **FOUO** |
| **Average Number of Employees** | 238 | **FOUO** |
| **Average Annual Revenue** | 239 | **FOUO** |
| **Parent Hierarchy (4 levels)** | 171-209 | **FOUO** |
| **EVS Monitoring (10 fields)** | 210-220 | **FOUO** |
| **Company/Employee Security Levels** | 27-28 | **FOUO** |
| **Agency Business Purpose** | 35 | **FOUO** |
| **EDI Information (15 fields)** | 221-235 | **FOUO** |
| **Entity URL** | 29 | Was in API (returned `null` for this entity — field exists but entity didn't provide) |
| **Entity Division Name/Number** | 14-15 | In API (returned `null`) |
| **Party Performing Cert POC** | 146-161 | **FOUO** — 7th POC slot not in public API |
| **Sole Proprietorship POC** | 162-170 | **FOUO** — 8th POC slot not in public API |
| **Accounts Receivable POC** | 259-267 | **FOUO** |
| **Accounts Payable POC** | 268-283 | **FOUO** |
| **Eliminations POC** | 309-324 | **FOUO** |
| **Sales POC** | 325-340 | **FOUO** |
| **Banking/Financial (all)** | 240-258 | **Sensitive** |
| **Tax ID** | 236-237 | **Sensitive** |
| **Taxpayer Name** | 341 | **Sensitive** |
| **NAICS Exception details** | 285-286 | Public — exists but we didn't check for it in API |
| **SBA Business Types w/ dates** | 289-290 | Public — richer than API's `sbaBusinessTypeList` |
| **Disaster Response details** | 294-295 | Public — has geographic sub-details with ^ delimiter |
| **Federal Hierarchy** | 302-308 | **FOUO** |
| **Correspondence Flag** | 42 | Public — not in API response |

### In JSON API but NOT in Extract

| API Field | Section | Notes |
|---|---|---|
| `repsAndCerts` (entire section) | repsAndCerts | **Separate extract file** — not in master entity extract |
| `samPointsOfContactList` with job titles (CEO/President) | repsAndCerts FAR 52.203-2 | Only in reps & certs, which is a separate extract |
| `submissionDate` | coreData.entityInformation | Not a column in the master extract |
| `dnbOpenData` | entityRegistration | Extract has `D&B OPEN DATA FLAG` (col 24) — same data, different name |
| `integrityInformation` / `proceedingsData` | Available in API v3+ | Not in master extract |

---

## 5. Reps and Certs Extract

### Separate file

Reps and Certs data is in a **separate extract file**, NOT part of the master entity extract. The `SAM_REPS_AND_CERTS_MAPPING.json` maps all FAR and DFARS provisions.

### Contents

The reps & certs mapping includes:
- **FAR provisions** — same 23+ provisions we saw in the API test (52.203-2, 52.204-3, 52.204-17, 52.204-20, 52.209-2, 52.209-5, 52.209-11, 52.212-3, 52.214-14, 52.215-6, 52.219-1, 52.219-2, 52.222-18, 52.222-48, 52.222-52, 52.223-4, 52.223-9, 52.225-2, 52.225-4, 52.225-6, 52.226-2, 52.227-15, plus additional ones)
- **DFARS provisions** — defense-specific provisions (empty for non-defense entities)

### Job titles in reps & certs

Yes — **FAR 52.203-2** contains `samPointsOfContactList` with `firstName`, `lastName`, and **`title`** (actual job title like CEO, President). This is available through both the API and the reps & certs extract.

---

## 6. Data Volume Expectations

### Record counts

Based on SAM.gov documentation:
- The Entity Management API can return up to **10,000 records** per synchronous query
- The Extract API can return up to **1,000,000 records** per async extract
- The monthly full dump contains **all** registered entities (active + expired)
- As of 2024-2025, SAM.gov has approximately **900,000+ active entity registrations**

### File sizes

- Monthly public extract: estimated **2-5 GB** uncompressed (368 columns x ~900K rows)
- Monthly FOUO extract: larger due to additional populated columns
- Daily deltas: much smaller (typically thousands of records)

### Refresh schedule

| Extract | Frequency | Contents |
|---|---|---|
| Monthly full | 1st of each month | All records (Active + Expired), complete data |
| Daily delta | Every day | Only changed records (new/updated/deleted/expired) |

### API Rate Limits

| Account Type | Daily Limit |
|---|---|
| Non-federal, no SAM role | 10 requests/day |
| Non-federal with SAM role | 1,000/day |
| Federal user | 1,000/day |
| Non-federal System Account | 1,000/day |
| Federal System Account | 10,000/day |

---

## 7. JSON API Sensitivity Levels & Access

### The Critical Finding

**Email, phone, employee count, revenue, and parent hierarchy ALL EXIST in SAM.gov data — but they are classified as FOUO (CUI).**

To access them via the API, we need:
1. A **Federal System Account** with "Read FOUO" permission, OR
2. The **FOUO bulk extract files** (requires the same access level)

### API Access Tiers

| Tier | Access Method | What You Get |
|---|---|---|
| **Public** | Personal API key (what we have) | Names, addresses, NAICS, business types, POC names/addresses, registration dates |
| **FOUO** | Federal System Account + "Read FOUO" | **+ Email, phone, employee count, revenue, parent hierarchy, security levels, EDI** |
| **Sensitive** | Federal System Account + "Read Sensitive" + POST with Basic Auth | **+ Banking, TIN/SSN, taxpayer name** |

### What to prioritize

For our use case, the **FOUO tier** is the game-changer. It unlocks:
- **14 email addresses** per entity (POC emails)
- **32 phone numbers** per entity (POC phones)
- **Employee count** (worldwide)
- **Annual revenue** (5-year average)
- **4-level parent hierarchy** (immediate, HQ, domestic, ultimate parent — each with name, UEI, address, phone)
- **EVS out-of-business indicator**

---

## 8. Exclusions Extract (Lower Priority)

Separate file: `SAM_Exclusions_Public_V2_Extract_YYDDD.ZIP` (CSV format)

31 columns: Classification, Name, Person name (prefix/first/middle/last/suffix), Address (4 lines + city/state/country/zip), Open Data Flag, UEI, Exclusion Program, Excluding Agency, CT Code, Exclusion Type, Additional Comments, Active Date, Termination Date, Record Status, Cross-Reference, SAM Number, CAGE, NPI, Creation Date.

---

## 9. Schema Design Implications (Updated from API-Only Assessment)

### With Public API Key (Current State)

Same as our previous assessment — Tier 1 core fields only. No email, phone, employee count, revenue.

### With FOUO Access (Target State)

If we obtain FOUO access, the Supabase schema should include:

**Tier 1 — Normalize into columns:**
- Everything from current Public tier, PLUS:
- `avg_employees` (integer) — col 238
- `avg_annual_revenue` (numeric) — col 239
- `entity_url` (text) — col 29
- `immediate_parent_uei`, `immediate_parent_name` — cols 171-172
- `ultimate_parent_uei`, `ultimate_parent_name` — cols 200-201
- `evs_out_of_business` (boolean) — col 210

**Tier 2 — Store as JSONB:**
- `points_of_contact` — all 8 POC slots with name, title, address, email, phone
- `parent_hierarchy` — all 4 parent levels with full details
- `sba_certifications` — from SBA business types string (col 290) with entry/exit dates
- `evs_monitoring` — EVS monitoring data

**Tier 3 — Store raw:**
- `reps_and_certs` — FAR/DFARS Q&A blob (from separate extract or API call)
