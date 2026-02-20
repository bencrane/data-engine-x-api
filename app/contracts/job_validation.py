from pydantic import BaseModel


class JobValidationOutput(BaseModel):
    validation_result: str | None = None
    confidence: str | None = None
    indeed_found: bool | None = None
    indeed_match_count: int | None = None
    indeed_any_expired: bool | None = None
    indeed_matched_by: str | None = None
    linkedin_found: bool | None = None
    linkedin_match_count: int | None = None
    linkedin_matched_by: str | None = None
    source_provider: str = "revenueinfra"
