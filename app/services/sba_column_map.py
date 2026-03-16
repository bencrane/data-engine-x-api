# app/services/sba_column_map.py — SBA 7(a) loan CSV column mapping
#
# Generated from foia-7a-fy2020-present-asof-250930.csv header row (43 columns).
# All CSV headers are already valid lowercase Postgres identifiers — identity mapping.
# Do not edit manually — regenerate from the CSV header if schema changes.

from __future__ import annotations


SBA_COLUMNS: list[dict] = [
    {"position": 1, "csv_header_name": "asofdate", "db_column_name": "asofdate", "description": "Data-as-of date for the quarterly snapshot (MM/DD/YYYY)"},
    {"position": 2, "csv_header_name": "program", "db_column_name": "program", "description": "SBA loan program (e.g. 7A)"},
    {"position": 3, "csv_header_name": "l2locid", "db_column_name": "l2locid", "description": "SBA internal location ID"},
    {"position": 4, "csv_header_name": "borrname", "db_column_name": "borrname", "description": "Borrower business name"},
    {"position": 5, "csv_header_name": "borrstreet", "db_column_name": "borrstreet", "description": "Borrower street address"},
    {"position": 6, "csv_header_name": "borrcity", "db_column_name": "borrcity", "description": "Borrower city"},
    {"position": 7, "csv_header_name": "borrstate", "db_column_name": "borrstate", "description": "Borrower state (2-letter code)"},
    {"position": 8, "csv_header_name": "borrzip", "db_column_name": "borrzip", "description": "Borrower ZIP code"},
    {"position": 9, "csv_header_name": "bankname", "db_column_name": "bankname", "description": "Lending bank name"},
    {"position": 10, "csv_header_name": "bankfdicnumber", "db_column_name": "bankfdicnumber", "description": "Bank FDIC number"},
    {"position": 11, "csv_header_name": "bankncuanumber", "db_column_name": "bankncuanumber", "description": "Bank NCUA number"},
    {"position": 12, "csv_header_name": "bankstreet", "db_column_name": "bankstreet", "description": "Bank street address"},
    {"position": 13, "csv_header_name": "bankcity", "db_column_name": "bankcity", "description": "Bank city"},
    {"position": 14, "csv_header_name": "bankstate", "db_column_name": "bankstate", "description": "Bank state"},
    {"position": 15, "csv_header_name": "bankzip", "db_column_name": "bankzip", "description": "Bank ZIP code"},
    {"position": 16, "csv_header_name": "grossapproval", "db_column_name": "grossapproval", "description": "Gross loan approval amount"},
    {"position": 17, "csv_header_name": "sbaguaranteedapproval", "db_column_name": "sbaguaranteedapproval", "description": "SBA guaranteed portion of the loan"},
    {"position": 18, "csv_header_name": "approvaldate", "db_column_name": "approvaldate", "description": "Loan approval date (MM/DD/YYYY)"},
    {"position": 19, "csv_header_name": "approvalfiscalyear", "db_column_name": "approvalfiscalyear", "description": "Fiscal year of approval"},
    {"position": 20, "csv_header_name": "firstdisbursementdate", "db_column_name": "firstdisbursementdate", "description": "Date of first loan disbursement"},
    {"position": 21, "csv_header_name": "processingmethod", "db_column_name": "processingmethod", "description": "Loan processing method"},
    {"position": 22, "csv_header_name": "subprogram", "db_column_name": "subprogram", "description": "SBA sub-program designation"},
    {"position": 23, "csv_header_name": "initialinterestrate", "db_column_name": "initialinterestrate", "description": "Initial interest rate on the loan"},
    {"position": 24, "csv_header_name": "fixedorvariableinterestind", "db_column_name": "fixedorvariableinterestind", "description": "Fixed or variable interest rate indicator"},
    {"position": 25, "csv_header_name": "terminmonths", "db_column_name": "terminmonths", "description": "Loan term in months"},
    {"position": 26, "csv_header_name": "naicscode", "db_column_name": "naicscode", "description": "NAICS industry code (6-digit)"},
    {"position": 27, "csv_header_name": "naicsdescription", "db_column_name": "naicsdescription", "description": "NAICS industry description"},
    {"position": 28, "csv_header_name": "franchisecode", "db_column_name": "franchisecode", "description": "Franchise code (if applicable)"},
    {"position": 29, "csv_header_name": "franchisename", "db_column_name": "franchisename", "description": "Franchise name (if applicable)"},
    {"position": 30, "csv_header_name": "projectcounty", "db_column_name": "projectcounty", "description": "County of the project"},
    {"position": 31, "csv_header_name": "projectstate", "db_column_name": "projectstate", "description": "State of the project"},
    {"position": 32, "csv_header_name": "sbadistrictoffice", "db_column_name": "sbadistrictoffice", "description": "SBA district office"},
    {"position": 33, "csv_header_name": "congressionaldistrict", "db_column_name": "congressionaldistrict", "description": "Congressional district"},
    {"position": 34, "csv_header_name": "businesstype", "db_column_name": "businesstype", "description": "Business type (e.g. CORPORATION)"},
    {"position": 35, "csv_header_name": "businessage", "db_column_name": "businessage", "description": "Business age category"},
    {"position": 36, "csv_header_name": "loanstatus", "db_column_name": "loanstatus", "description": "Current loan status"},
    {"position": 37, "csv_header_name": "paidinfulldate", "db_column_name": "paidinfulldate", "description": "Date loan was paid in full"},
    {"position": 38, "csv_header_name": "chargeoffdate", "db_column_name": "chargeoffdate", "description": "Date loan was charged off"},
    {"position": 39, "csv_header_name": "grosschargeoffamount", "db_column_name": "grosschargeoffamount", "description": "Gross charge-off amount"},
    {"position": 40, "csv_header_name": "revolverstatus", "db_column_name": "revolverstatus", "description": "Revolver status indicator"},
    {"position": 41, "csv_header_name": "jobssupported", "db_column_name": "jobssupported", "description": "Number of jobs supported by the loan"},
    {"position": 42, "csv_header_name": "collateralind", "db_column_name": "collateralind", "description": "Collateral indicator"},
    {"position": 43, "csv_header_name": "soldsecmrktind", "db_column_name": "soldsecmrktind", "description": "Sold on secondary market indicator"},
]

SBA_DB_COLUMN_NAMES: list[str] = [c["db_column_name"] for c in SBA_COLUMNS]

SBA_COLUMN_COUNT: int = len(SBA_COLUMNS)

SBA_CSV_TO_DB_MAP: dict[str, str] = {
    c["csv_header_name"]: c["db_column_name"] for c in SBA_COLUMNS
}


if __name__ == "__main__":
    print(f"SBA column count: {SBA_COLUMN_COUNT}")
    assert SBA_COLUMN_COUNT == 43, f"Expected 43 columns, got {SBA_COLUMN_COUNT}"
    assert SBA_COLUMNS[0]["db_column_name"] == "asofdate", f"First column should be asofdate"
    assert SBA_COLUMNS[-1]["db_column_name"] == "soldsecmrktind", f"Last column should be soldsecmrktind"
    assert len(set(SBA_DB_COLUMN_NAMES)) == 43, "Duplicate db_column_names found"
    print("First 3:", [(c["csv_header_name"], c["db_column_name"]) for c in SBA_COLUMNS[:3]])
    print("Last 3:", [(c["csv_header_name"], c["db_column_name"]) for c in SBA_COLUMNS[-3:]])
    print("All assertions passed.")
