# SAM.gov Full Schema Test — Complete Field Inventory

**Date:** 2026-03-16
**Status:** SUCCESS (HTTP 200)
**Entity queried:** UEI `SWCCBS41L723` (C & C HOME CARE LLC)
**Response size:** ~110 KB / 2,649 lines of pretty-printed JSON

## Call Made

```
GET https://api.sam.gov/entity-information/v3/entities
  ?api_key=${SAM_GOV_API_KEY}
  &ueiSAM=SWCCBS41L723
  &includeSections=entityRegistration,coreData,assertions,repsAndCerts,pointsOfContact
```

**Note:** `generalInformation` was rejected as an invalid section name (HTTP 400). Removed and retried successfully. The valid sections are: `entityRegistration`, `coreData`, `assertions`, `repsAndCerts`, `pointsOfContact`.

---

## Section 1: entityRegistration

| Field | Type | Sample Value |
|---|---|---|
| `samRegistered` | string | `"Yes"` |
| `ueiSAM` | string | `"SWCCBS41L723"` |
| `entityEFTIndicator` | string/null | `null` |
| `cageCode` | string | `"9JC31"` |
| `dodaac` | string/null | `null` |
| `legalBusinessName` | string | `"C & C HOME CARE LLC"` |
| `dbaName` | string | `"C & C HOME CARE LLC"` |
| `purposeOfRegistrationCode` | string | `"Z2"` |
| `purposeOfRegistrationDesc` | string | `"All Awards"` |
| `registrationStatus` | string | `"Active"` |
| `evsSource` | string | `"E&Y"` |
| `registrationDate` | date string | `"2023-01-08"` |
| `lastUpdateDate` | date string | `"2026-01-08"` |
| `registrationExpirationDate` | date string | `"2027-01-06"` |
| `activationDate` | date string | `"2026-01-08"` |
| `ueiStatus` | string | `"Active"` |
| `ueiExpirationDate` | date/null | `null` |
| `ueiCreationDate` | date string | `"2023-01-08"` |
| `publicDisplayFlag` | string | `"Y"` |
| `exclusionStatusFlag` | string | `"N"` |
| `exclusionURL` | string/null | `null` |
| `dnbOpenData` | string/null | `null` |

---

## Section 2: coreData

### coreData.entityInformation

| Field | Type | Sample Value |
|---|---|---|
| `entityURL` | string/null | `null` |
| `entityDivisionName` | string/null | `null` |
| `entityDivisionNumber` | string/null | `null` |
| `entityStartDate` | date string | `"2020-01-30"` |
| `fiscalYearEndCloseDate` | string | `"12/31"` |
| `submissionDate` | date string | `"2026-01-06"` |

### coreData.physicalAddress

| Field | Type | Sample Value |
|---|---|---|
| `addressLine1` | string | `"7260 UNIVERSITY AVE NE STE 305"` |
| `addressLine2` | string/null | `null` |
| `city` | string | `"MINNEAPOLIS"` |
| `stateOrProvinceCode` | string | `"MN"` |
| `zipCode` | string | `"55432"` |
| `zipCodePlus4` | string | `"3129"` |
| `countryCode` | string | `"USA"` |

### coreData.mailingAddress

Same schema as physicalAddress. For this entity, identical values.

### coreData.congressionalDistrict

| Field | Type | Sample Value |
|---|---|---|
| `congressionalDistrict` | string | `"05"` |

### coreData.generalInformation

| Field | Type | Sample Value |
|---|---|---|
| `entityStructureCode` | string | `"2L"` |
| `entityStructureDesc` | string | `"Corporate Entity (Not Tax Exempt)"` |
| `entityTypeCode` | string | `"F"` |
| `entityTypeDesc` | string | `"Business or Organization"` |
| `profitStructureCode` | string | `"2X"` |
| `profitStructureDesc` | string | `"For Profit Organization"` |
| `organizationStructureCode` | string | `"LJ"` |
| `organizationStructureDesc` | string | `"Limited Liability Company"` |
| `stateOfIncorporationCode` | string | `"MN"` |
| `stateOfIncorporationDesc` | string | `"MINNESOTA"` |
| `countryOfIncorporationCode` | string | `"USA"` |
| `countryOfIncorporationDesc` | string | `"UNITED STATES"` |

### coreData.businessTypes.businessTypeList (array)

| Code | Description |
|---|---|
| `27` | Self Certified Small Disadvantaged Business |
| `2X` | For Profit Organization |
| `A5` | Veteran-Owned Business |
| `F` | Business or Organization |
| `LJ` | Limited Liability Company |
| `QF` | Service-Disabled Veteran-Owned Business |

Each entry: `{ businessTypeCode, businessTypeDesc }`

### coreData.businessTypes.sbaBusinessTypeList (array)

| Field | Type | Sample Value |
|---|---|---|
| `sbaBusinessTypeCode` | string/null | `null` |
| `sbaBusinessTypeDesc` | string/null | `null` |
| `certificationEntryDate` | date/null | `null` |
| `certificationExitDate` | date/null | `null` |

(All null for this entity — no active SBA certifications)

### coreData.financialInformation

| Field | Type | Sample Value |
|---|---|---|
| `creditCardUsage` | string | `"N"` |
| `debtSubjectToOffset` | string | `"N"` |

---

## Section 3: assertions

### assertions.goodsAndServices

| Field | Type | Sample Value |
|---|---|---|
| `primaryNaics` | string | `"621610"` |

#### assertions.goodsAndServices.naicsList (array of 8)

Each entry schema:

| Field | Type | Sample Value |
|---|---|---|
| `naicsCode` | string | `"621610"` |
| `naicsDescription` | string | `"Home Health Care Services"` |
| `sbaSmallBusiness` | string | `"Y"` |
| `naicsException` | string/null | `null` |

Full NAICS list for this entity:

| NAICS Code | Description | SBA Small Business |
|---|---|---|
| `238160` | Roofing Contractors | Y |
| `238210` | Electrical Contractors and Other Wiring Installation Contractors | Y |
| `333310` | Commercial and Service Industry Machinery Manufacturing | Y |
| `335132` | Commercial, Industrial, and Institutional Electric Lighting Fixture Manufacturing | Y |
| `561210` | Facilities Support Services | Y |
| `561720` | Janitorial Services | Y |
| `621610` | Home Health Care Services (PRIMARY) | Y |
| `811310` | Commercial and Industrial Machinery and Equipment Repair and Maintenance | Y |

#### assertions.goodsAndServices.pscList (array)

Each entry: `{ pscCode, pscDescription }` — all null for this entity.

### assertions.disasterReliefData

| Field | Type | Sample Value |
|---|---|---|
| `disasterRegistryFlag` | string | `"NO"` |
| `bondingFlag` | string | `"NO"` |

#### assertions.disasterReliefData.geographicalAreaServed (array)

Each entry:

| Field | Type | Sample Value |
|---|---|---|
| `geographicalAreaServedStateCode` | string/null | `null` |
| `geographicalAreaServedStateName` | string/null | `null` |
| `geographicalAreaServedCountyCode` | string/null | `null` |
| `geographicalAreaServedCountyName` | string/null | `null` |
| `geographicalAreaServedmetropolitanStatisticalAreaCode` | string/null | `null` |
| `geographicalAreaServedmetropolitanStatisticalAreaName` | string/null | `null` |

### assertions.ediInformation

| Field | Type | Sample Value |
|---|---|---|
| `ediInformationFlag` | string | `"N"` |

---

## Section 4: pointsOfContact

6 POC slots, each with identical schema:

| Field | Type |
|---|---|
| `firstName` | string/null |
| `middleInitial` | string/null |
| `lastName` | string/null |
| `title` | string/null |
| `addressLine1` | string/null |
| `addressLine2` | string/null |
| `city` | string/null |
| `stateOrProvinceCode` | string/null |
| `zipCode` | string/null |
| `zipCodePlus4` | string/null |
| `countryCode` | string/null |

### POC Slot Population

| Slot | Populated? | Name | Title |
|---|---|---|---|
| `governmentBusinessPOC` | Yes | Christopher Wallace | Mr |
| `electronicBusinessPOC` | Yes | Christopher Wallace | Mr |
| `governmentBusinessAlternatePOC` | No | — | — |
| `electronicBusinessAlternatePOC` | No | — | — |
| `pastPerformancePOC` | No | — | — |
| `pastPerformanceAlternatePOC` | No | — | — |

**No email or phone fields exist in the POC schema.**

---

## Section 5: repsAndCerts

The largest section (~2,300 lines). Contains FAR compliance questionnaire responses and financial assistance certifications.

### repsAndCerts.certifications.fARResponses (array)

Array of FAR provision responses. Each entry:

```
{
  "provisionId": "FAR 52.xxx-xx",
  "listOfAnswers": [
    {
      "section": "52.xxx-xx.x",
      "questionText": "...",
      "answerId": "...",
      "answerText": "Yes/No/...",
      "country": null,
      "company": null,
      "highestLevelOwnerCage": null,
      "immediateOwnerCage": null,
      "personDetails": null,
      "pointOfContact": null,
      "architectExperiencesList": [],
      "disciplineInfoList": [],
      "endProductsList": [],
      "foreignGovtEntitiesList": [],
      "formerFirmsList": [],
      "fscInfoList": [],
      "jointVentureCompaniesList": [],
      "laborSurplusConcernsList": [],
      "naicsList": [],
      "predecessorsList": [],
      "samFacilitiesList": [],
      "samPointsOfContactList": [],
      "servicesRevenuesList": [],
      "softwareList": [],
      "urlList": []
    }
  ]
}
```

#### FAR Provisions Present (23 total)

| Provision ID | Topic |
|---|---|
| `FAR 52.209-2` | Inverted domestic corporation |
| `FAR 52.204-26` | Covered telecommunications equipment |
| `FAR 52.209-5` | Debarment/suspension/conviction history |
| `FAR 52.203-2` | Persons determining bid prices (has `samPointsOfContactList` with CEO/President names+titles) |
| `FAR 52.215-6` | Additional plants/facilities |
| `FAR 52.214-14` | Additional plants/facilities (duplicate question) |
| `FAR 52.223-4` | EPA recovered material compliance |
| `FAR 52.223-9` | EPA recovered material compliance |
| `FAR 52.219-2` | Labor surplus area concern |
| `FAR 52.204-3` | TIN on file, org type (LLC), parent company |
| `FAR 52.212-3` | **Major provision** — small business reps, NAICS with `isPrimary`/`isSmallBusiness`/`hasSBAProtest`/`hasSizeChanged`, debarment, foreign products, HUBZone, tax liability, felony conviction, disadvantaged business |
| `FAR 52.219-1` | Small business size standard — repeats NAICS list with extended fields |
| `FAR 52.226-2` | Historically underutilized business zone |
| `FAR 52.227-15` | Technical data/software rights |
| `FAR 52.204-17` | Ownership/control by foreign govt |
| `FAR 52.204-20` | SSN collection/maintenance |
| `FAR 52.222-18` | Exemption from child labor laws |
| `FAR 52.209-11` | Entity information — highest/immediate owner |
| `FAR 52.225-2` | Buy American compliance |
| `FAR 52.225-4` | Buy American — foreign end products |
| `FAR 52.225-6` | Buy American — trade agreements |
| `FAR 52.222-48` | Equipment maintenance/calibration |
| `FAR 52.222-52` | Service contract labor standards |

#### Notable Populated Lists in repsAndCerts

**`samPointsOfContactList`** (in FAR 52.203-2) — persons determining bid prices:

| firstName | lastName | title |
|---|---|---|
| Christopher | Wallace | CEO |
| Christine | Wallace | President |

This is the only place in the entire response that has **actual job titles** (CEO, President) rather than honorifics.

**`naicsList`** (in FAR 52.212-3 and FAR 52.219-1) — extended NAICS with small business fields:

| Field | Type | Sample Value |
|---|---|---|
| `naicsCode` | string | `"621610"` |
| `naicsName` | string | `"Home Health Care Services"` |
| `isPrimary` | string | `"true"/"false"` |
| `isSmallBusiness` | string | `"Y"` |
| `exceptionCounter` | string/null | `null` |
| `hasSBAProtest` | string/null | `null` |
| `hasSizeChanged` | string/null | `null` |

### repsAndCerts.certifications.dFARResponses

Empty array `[]` for this entity. (DFARS responses would appear for defense contractors.)

### repsAndCerts.qualifications

| Field | Type | Sample Value |
|---|---|---|
| `architectEngineerResponses` | object/null | `null` |

### repsAndCerts.financialAssistanceCertifications

| Field | Type | Sample Value |
|---|---|---|
| `grantsCertificationStatus` | string | `"N"` |
| `grantsCertifyingResponse` | string | `"N"` |
| `certifierFirstName` | string | `"Christopher"` |
| `certifierLastName` | string | `"Wallace"` |
| `certifierMiddleInitial` | string/null | `null` |

### repsAndCerts.pdfLinks

| Field | Type | Sample Value |
|---|---|---|
| `farPDF` | URL string | `"https://api.sam.gov/SAM/file-download?api_key=REPLACE_WITH_API_KEY&pdfType=1&ueiSAM=SWCCBS41L723"` |
| `farAndDfarsPDF` | URL/null | `null` |
| `architectEngineeringPDF` | URL/null | `null` |
| `financialAssistanceCertificationsPDF` | URL/null | `null` |

---

## Top-Level Response Fields

| Field | Type | Sample Value |
|---|---|---|
| `totalRecords` | integer | `1` |
| `entityData` | array | (array of entity objects) |
| `links.selfLink` | URL string | pagination self-link |

---

## New Findings vs. Previous Test

Fields/data NOT present in the first test (entityRegistration + coreData + pointsOfContact only):

| Finding | Section | Value |
|---|---|---|
| **NAICS codes** | `assertions.goodsAndServices` | 8 NAICS codes with primary flag and SBA small business status |
| **Primary NAICS** | `assertions.goodsAndServices.primaryNaics` | `"621610"` |
| **PSC codes** | `assertions.goodsAndServices.pscList` | Field exists (null for this entity) |
| **Disaster relief registration** | `assertions.disasterReliefData` | Registry flag, bonding flag, geographic area served |
| **EDI capability** | `assertions.ediInformation` | `ediInformationFlag` |
| **Actual job titles (CEO, President)** | `repsAndCerts` FAR 52.203-2 `samPointsOfContactList` | Only source of real job titles |
| **Extended NAICS fields** | `repsAndCerts` FAR 52.212-3/52.219-1 | `isPrimary`, `isSmallBusiness`, `hasSBAProtest`, `hasSizeChanged` |
| **Small disadvantaged business self-cert** | `repsAndCerts` FAR 52.212-3 section c.4 | `"Yes"` |
| **FAR compliance Q&A** | `repsAndCerts.certifications.fARResponses` | 23 FAR provisions, debarment/conviction/tax history |
| **Ownership/control by foreign govt** | FAR 52.204-17 | No |
| **Highest/immediate owner CAGE** | FAR 52.209-11 answer schema | Fields exist but null for this entity |
| **Financial assistance certifications** | `repsAndCerts.financialAssistanceCertifications` | Grants cert status, certifier name |
| **PDF download links** | `repsAndCerts.pdfLinks` | FAR PDF available |

## What SAM.gov Does NOT Provide (Confirmed)

Even with ALL sections requested:

- **No email addresses** — not in any section, any field
- **No phone numbers** — not in any section, any field
- **No employee count** — no headcount, no FTE, no size metric
- **No revenue figures** — no annual revenue, no receipts, no financial size
- **No website URL** — `entityURL` field exists in coreData but null for this entity (may be populated for others)
- **No D-U-N-S number** — `dnbOpenData` field exists but null

## Schema Design Implications

For the Supabase table, the **high-value fields** to persist are:

### Tier 1 — Always persist
- `ueiSAM`, `cageCode`, `legalBusinessName`, `dbaName`
- `registrationStatus`, `registrationDate`, `lastUpdateDate`, `registrationExpirationDate`, `activationDate`
- `physicalAddress.*` (full address)
- `mailingAddress.*` (full address)
- `primaryNaics` + full `naicsList` (from assertions)
- `businessTypeList` (veteran-owned, SDB, profit structure, etc.)
- `stateOfIncorporationCode`, `countryOfIncorporationCode`
- `entityStructureDesc`, `organizationStructureDesc`, `profitStructureDesc`
- `congressionalDistrict`
- `entityStartDate`
- `exclusionStatusFlag`

### Tier 2 — Persist as JSONB
- `pointsOfContact` — all 6 slots (name, title, address)
- `sbaBusinessTypeList` — SBA certifications with entry/exit dates
- `disasterReliefData` — registry flag, bonding, geographic area
- `pscList` — product/service codes (when populated)
- `samPointsOfContactList` from FAR 52.203-2 — **only source of real job titles (CEO, President)**

### Tier 3 — Store raw, query rarely
- `repsAndCerts` — massive FAR/DFARS Q&A blob. Store as JSONB for compliance research but don't try to normalize it.

### Skip
- Individual FAR answer records (23 provisions x multiple questions each = hundreds of rows with minimal query value)
- `pdfLinks` (can be reconstructed from UEI + API key)
