from __future__ import annotations

from pydantic import BaseModel


class SECFilingInfo(BaseModel):
    filing_date: str | None = None
    report_date: str | None = None
    accession_number: str | None = None
    document_url: str | None = None
    items: list[str] | None = None


class FetchSECFilingsOutput(BaseModel):
    cik: str | None = None
    ticker: str | None = None
    company_name: str | None = None
    latest_10k: SECFilingInfo | None = None
    latest_10q: SECFilingInfo | None = None
    recent_8k_executive_changes: list[SECFilingInfo] | None = None
    recent_8k_earnings: list[SECFilingInfo] | None = None
    recent_8k_material_contracts: list[SECFilingInfo] | None = None
    source_provider: str = "revenueinfra"


class SECAnalysisOutput(BaseModel):
    filing_type: str
    document_url: str | None = None
    domain: str | None = None
    company_name: str | None = None
    analysis: str
    source_provider: str = "revenueinfra"
