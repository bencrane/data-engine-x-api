# SBA Data Inspection Report

**Generated:** 2026-03-13

## 1. File Metadata
- **File:** `sba_7a_fy2020_present.csv`
- **Size:** 135.3 MB

## 2. Row & Column Overview
- **Rows:** 357,866
- **Columns:** 43

### Full Column Manifest
1. `asofdate`
2. `program`
3. `l2locid`
4. `borrname`
5. `borrstreet`
6. `borrcity`
7. `borrstate`
8. `borrzip`
9. `bankname`
10. `bankfdicnumber`
11. `bankncuanumber`
12. `bankstreet`
13. `bankcity`
14. `bankstate`
15. `bankzip`
16. `grossapproval`
17. `sbaguaranteedapproval`
18. `approvaldate`
19. `approvalfiscalyear`
20. `firstdisbursementdate`
21. `processingmethod`
22. `subprogram`
23. `initialinterestrate`
24. `fixedorvariableinterestind`
25. `terminmonths`
26. `naicscode`
27. `naicsdescription`
28. `franchisecode`
29. `franchisename`
30. `projectcounty`
31. `projectstate`
32. `sbadistrictoffice`
33. `congressionaldistrict`
34. `businesstype`
35. `businessage`
36. `loanstatus`
37. `paidinfulldate`
38. `chargeoffdate`
39. `grosschargeoffamount`
40. `revolverstatus`
41. `jobssupported`
42. `collateralind`
43. `soldsecmrktind`

## 3. Manufacturing & Recency Filter Counts
*Total records parsed: 357,866*

- **Manufacturing (NAICS 31-33):** 22,430
- **Recent (Approved in 2025/2026):** 68,435
- **Manufacturing + Recent Intersection:** 3,864

## 4. Sample Manufacturing Loan Records
*Format: [Name] | [State] | NAICS: [Code] | Amount: [Value] | Date: [Approval Date]*

- | AK | NAICS: 311710 | Amount: 300000 | Date: 10/23/2019
- | CA | NAICS: 321999 | Amount: 2072000 | Date: 10/23/2019
- | MN | NAICS: 337122 | Amount: 107000 | Date: 10/23/2019
- | NC | NAICS: 312120 | Amount: 241000 | Date: 8/19/2020
- | TX | NAICS: 323111 | Amount: 799500 | Date: 8/19/2020

*(Note: The `borrname` column seems to be masked or empty for some early FOIA rows in this payload. We should ensure we fetch recent records where Borrower Name might be present, or check if the dataset explicitly masks names for older or specific loans. The logic in the Python script captured an empty string for the borrower name in the top 5 samples)*

## 5. Potential Use Case & Schema Mapping
Based on our requirement for lead contact records and company size profiling:

- **Borrower Name & Address:** 
  Map `borrname`, `borrstreet`, `borrcity`, `borrstate`, `borrzip`. (Crucial for lead matching).
- **NAICS Code:** 
  `naicscode` directly maps to our Manufacturing filters.
- **Size Proxy (Loan Amount):** 
  `grossapproval` (Gross amount provides a scale reference for company growth/needs).
- **Recency (Approval Date):** 
  `approvaldate` (For segmenting recent actions to find timely triggers).
- **Lender Information:** 
  `bankname`, `bankstate` (Useful for enrichment or tracing financial partners).
- **Other valuable insights:** 
  `businesstype` (e.g. CORPORATION), `jobssupported` (Another great size proxy), `naicsdescription`.

## 6. Borrower Name & Address Completeness Check
An additional check was run on the 68,435 recent loan records (Approved in 2025/2026) to determine if this dataset is viable for outbound lead generation.

### 6.1 Name & Address Completeness
For the specific subset of recent manufacturing loans (N = 3,864), completeness is phenomenally high:

- **Borrower Name Present:** 100.0% (all 68,435 recent records across all NAICS had names)
- **Full Address Present (Name, Street, City, State, Zip):** 100.0% (3,864 / 3,864)
- **Partial Address Present (Name, City, State minimally):** 100.0% (3,864 / 3,864)

### 6.2 Sample Manufacturing Records
Below are 10 real sample records of recent manufacturing loans demonstrating the available data shape:

1. **Zytron Control Products Inc.** | Ewing, NJ | NAICS: 335999 (All Other Miscellaneous Electrical Equipment and C)
   Loan: $350,000 | Approved: 7/18/2025 | Lender: First Bank
   Jobs: 18 | Type: CORPORATION | Age: Existing or more than 2 years old

2. **JENA25 LLC** | MORAINE, OH | NAICS: 332710 (Machine Shops)
   Loan: $663,000 | Approved: 7/18/2025 | Lender: Truliant FCU
   Jobs: 31 | Type: CORPORATION | Age: New Business or 2 years or less

3. **C & C Food Group LLC** | FREDERICK, MD | NAICS: 311811 (Retail Bakeries)
   Loan: $25,000 | Approved: 7/18/2025 | Lender: Manufacturers and Traders Trust Company
   Jobs: 4 | Type: CORPORATION | Age: Startup, Loan Funds will Open Business

4. **SYER METAL WORKS LLC** | LAS VEGAS, NV | NAICS: 332999 (All Other Miscellaneous Fabricated Metal Product M)
   Loan: $25,000 | Approved: 7/18/2025 | Lender: Zions Bank, A Division of
   Jobs: 15 | Type: CORPORATION | Age: Existing or more than 2 years old

5. **KJSS Global Inc** | SANTA FE SPRINGS, CA | NAICS: 332215 (Metal Kitchen Cookware, Utensil, Cutlery, and Flat)
   Loan: $250,000 | Approved: 7/18/2025 | Lender: Northeast Bank
   Jobs: 10 | Type: CORPORATION | Age: Existing or more than 2 years old

6. **Jena Tool Inc.** | MORAINE, OH | NAICS: 332710 (Machine Shops)
   Loan: $1,014,200 | Approved: 7/18/2025 | Lender: Truliant FCU
   Jobs: 31 | Type: CORPORATION | Age: Change of Ownership

7. **NEST STUDIO LLC** | FLORHAM PARK, NJ | NAICS: 332510 (Hardware Manufacturing)
   Loan: $150,000 | Approved: 7/18/2025 | Lender: BayFirst National Bank
   Jobs: 0 | Type: CORPORATION | Age: Existing or more than 2 years old

8. **QUALITY COMPOUND MANUFACTURING LLC** | ELYRIA, OH | NAICS: 325998 (All Other Miscellaneous Chemical Product and Prepa)
   Loan: $100,000 | Approved: 7/18/2025 | Lender: The Huntington National Bank
   Jobs: 0 | Type: CORPORATION | Age: Existing or more than 2 years old

9. **Motive Power Marine LLC** | TACOMA, WA | NAICS: 336611 (Ship Building and Repairing)
   Loan: $350,000 | Approved: 8/7/2025 | Lender: Wells Fargo Bank National Association
   Jobs: 0 | Type: CORPORATION | Age: Existing or more than 2 years old

10. **Zuech Industries Inc** | SALISBURY, NH | NAICS: 334519 (Other Measuring and Controlling Device Manufacturi)
    Loan: $508,000 | Approved: 8/7/2025 | Lender: BayFirst National Bank
    Jobs: 3 | Type: CORPORATION | Age: Change of Ownership

### 6.3 Cross-Reference Identifiers
An inspection of all 43 schema fields reveals **no unique federal entity identifiers** (e.g., UEI, DUNS, EIN, TIN). The fields are solely localized to SBA/Loan metrics (`l2locid`, `franchisecode`, `bankfdicnumber`). 

Linking this dataset to SAM.gov or USASpending will require **fuzzy matching** on Company Name, City, and State, or external enrichment (e.g., sending the Name + Address to Apollo or Enigma API to retrieve a firmographic profile or EIN).

### 6.4 Verdict
**Is this dataset usable for outbound lead generation? YES.**
The 100% address and name completion rate on recent records makes this an extremely high-fidelity lead source for target segmentation, especially given the exact loan amount and jobs supported parameters which are excellent size proxies.
