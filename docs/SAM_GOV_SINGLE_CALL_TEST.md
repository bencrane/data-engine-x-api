# SAM.gov API Single Call Test

**Date:** 2026-03-16
**Status:** SUCCESS (HTTP 200)
**Entity queried:** UEI `SWCCBS41L723` (C & C HOME CARE LLC)

## Call Made

```
GET https://api.sam.gov/entity-information/v3/entities
  ?api_key=${SAM_GOV_API_KEY}
  &ueiSAM=SWCCBS41L723
  &includeSections=entityRegistration,coreData,pointsOfContact
```

## Points of Contact Assessment

### Email addresses: NO — field does not exist in schema
### Phone numbers: NO — field does not exist in schema
### Contact names: YES
### Contact titles: YES (but just honorific, e.g. "Mr" — not job title/role)

The `pointsOfContact` section contains **6 POC slots**, each with the same field schema:
- `firstName`, `middleInitial`, `lastName`, `title`
- `addressLine1`, `addressLine2`, `city`, `stateOrProvinceCode`, `zipCode`, `zipCodePlus4`, `countryCode`

**There are no email or phone fields in any POC object.** SAM.gov's public API v3 does not expose contact email or phone — only name, honorific title, and mailing address.

### POC Slots

| Slot | Populated? | Name |
|---|---|---|
| `governmentBusinessPOC` | Yes | Christopher Wallace |
| `electronicBusinessPOC` | Yes | Christopher Wallace |
| `governmentBusinessAlternatePOC` | No | — |
| `electronicBusinessAlternatePOC` | No | — |
| `pastPerformancePOC` | No | — |
| `pastPerformanceAlternatePOC` | No | — |

## Full Response Field Inventory

### Top Level
- `totalRecords`: 1
- `entityData`: array of 1 entity
- `links.selfLink`: pagination self-link

### entityRegistration
| Field | Value |
|---|---|
| `samRegistered` | "Yes" |
| `ueiSAM` | "SWCCBS41L723" |
| `entityEFTIndicator` | null |
| `cageCode` | "9JC31" |
| `dodaac` | null |
| `legalBusinessName` | "C & C HOME CARE LLC" |
| `dbaName` | "C & C HOME CARE LLC" |
| `purposeOfRegistrationCode` | "Z2" |
| `purposeOfRegistrationDesc` | "All Awards" |
| `registrationStatus` | "Active" |
| `evsSource` | "E&Y" |
| `registrationDate` | "2023-01-08" |
| `lastUpdateDate` | "2026-01-08" |
| `registrationExpirationDate` | "2027-01-06" |
| `activationDate` | "2026-01-08" |
| `ueiStatus` | "Active" |
| `ueiExpirationDate` | null |
| `ueiCreationDate` | "2023-01-08" |
| `publicDisplayFlag` | "Y" |
| `exclusionStatusFlag` | "N" |
| `exclusionURL` | null |
| `dnbOpenData` | null |

### coreData.entityInformation
| Field | Value |
|---|---|
| `entityURL` | null |
| `entityDivisionName` | null |
| `entityDivisionNumber` | null |
| `entityStartDate` | "2020-01-30" |
| `fiscalYearEndCloseDate` | "12/31" |
| `submissionDate` | "2026-01-06" |

### coreData.physicalAddress
| Field | Value |
|---|---|
| `addressLine1` | "7260 UNIVERSITY AVE NE STE 305" |
| `addressLine2` | null |
| `city` | "MINNEAPOLIS" |
| `stateOrProvinceCode` | "MN" |
| `zipCode` | "55432" |
| `zipCodePlus4` | "3129" |
| `countryCode` | "USA" |

### coreData.mailingAddress
Same as physical address.

### coreData.congressionalDistrict
`"05"`

### coreData.generalInformation
| Field | Value |
|---|---|
| `entityStructureCode` | "2L" |
| `entityStructureDesc` | "Corporate Entity (Not Tax Exempt)" |
| `entityTypeCode` | "F" |
| `entityTypeDesc` | "Business or Organization" |
| `profitStructureCode` | "2X" |
| `profitStructureDesc` | "For Profit Organization" |
| `organizationStructureCode` | "LJ" |
| `organizationStructureDesc` | "Limited Liability Company" |
| `stateOfIncorporationCode` | "MN" |
| `stateOfIncorporationDesc` | "MINNESOTA" |
| `countryOfIncorporationCode` | "USA" |
| `countryOfIncorporationDesc` | "UNITED STATES" |

### coreData.businessTypes.businessTypeList
| Code | Description |
|---|---|
| 27 | Self Certified Small Disadvantaged Business |
| 2X | For Profit Organization |
| A5 | Veteran-Owned Business |
| F | Business or Organization |
| LJ | Limited Liability Company |
| QF | Service-Disabled Veteran-Owned Business |

### coreData.businessTypes.sbaBusinessTypeList
Single entry, all null fields (no SBA certifications).

### coreData.financialInformation
| Field | Value |
|---|---|
| `creditCardUsage` | "N" |
| `debtSubjectToOffset` | "N" |

### pointsOfContact
See POC assessment above. Each of the 6 slots has identical field schema: `firstName`, `middleInitial`, `lastName`, `title`, `addressLine1`, `addressLine2`, `city`, `stateOrProvinceCode`, `zipCode`, `zipCodePlus4`, `countryCode`.

## Bottom Line

SAM.gov public API v3 is **useful for**:
- Entity registration status and dates
- CAGE codes and UEI validation
- Physical/mailing addresses
- Business type classifications (veteran-owned, SBA, profit structure, org structure)
- State/country of incorporation
- POC names and mailing addresses
- Congressional district

SAM.gov public API v3 **does NOT provide**:
- Email addresses (not in any section)
- Phone numbers (not in any section)
- NAICS codes (not in the sections we requested — may be in `assertions` section)
- Revenue/employee count
- Website URL (field exists but null for this entity)

To get NAICS codes, we would need to add `assertions` to the `includeSections` parameter in a future call.
