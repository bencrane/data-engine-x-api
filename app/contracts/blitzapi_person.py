from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WaterfallIcpSearchOutput(BaseModel):
    results: list[Any]
    results_count: int
    source_provider: str = "blitzapi"


class EmployeeFinderOutput(BaseModel):
    results: list[Any]
    results_count: int
    pagination: dict[str, Any] | None = None
    source_provider: str = "blitzapi"


class FindWorkEmailOutput(BaseModel):
    work_email: str | None = None
    all_emails: list[Any] | None = None
    source_provider: str = "blitzapi"
