from __future__ import annotations

from pydantic import BaseModel


class CourtFilingItem(BaseModel):
    docket_id: int | None = None
    case_name: str | None = None
    case_name_short: str | None = None
    court: str | None = None
    court_citation: str | None = None
    docket_number: str | None = None
    date_filed: str | None = None
    date_terminated: str | None = None
    date_last_filing: str | None = None
    judge: str | None = None
    pacer_case_id: str | None = None
    party_names: list[str] | None = None
    attorneys: list[str] | None = None
    relevance_score: float | None = None
    url: str | None = None
    source_provider: str = "courtlistener"


class CourtFilingSearchOutput(BaseModel):
    results: list[CourtFilingItem]
    result_count: int
    source_provider: str = "courtlistener"


class BankruptcyFilingSearchOutput(BaseModel):
    results: list[CourtFilingItem]
    result_count: int
    source_provider: str = "courtlistener"


class DocketDetailOutput(BaseModel):
    docket_id: int | None = None
    case_name: str | None = None
    court_id: str | None = None
    docket_number: str | None = None
    date_filed: str | None = None
    date_terminated: str | None = None
    judge: str | None = None
    parties: list[str] | None = None
    url: str | None = None
    source_provider: str = "courtlistener"
