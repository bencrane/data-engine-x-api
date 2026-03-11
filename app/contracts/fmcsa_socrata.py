from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


class FMCSASocrataQueryOutput(BaseModel):
    dataset_name: str
    dataset_id: str
    identifier_type_used: Literal["dot_number", "mc_number"]
    identifier_value_used: str
    result_count: int
    matched_rows: list[dict[str, Any]]
    source_provider: str = "socrata"
