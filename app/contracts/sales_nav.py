from pydantic import BaseModel


class SalesNavPersonItem(BaseModel):
    full_name: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    linkedin_url: str | None = None
    profile_urn: str | None = None
    geo_region: str | None = None
    summary: str | None = None
    current_title: str | None = None
    current_company_name: str | None = None
    current_company_id: str | None = None
    current_company_industry: str | None = None
    current_company_location: str | None = None
    position_start_month: int | None = None
    position_start_year: int | None = None
    tenure_at_position_years: int | None = None
    tenure_at_position_months: int | None = None
    tenure_at_company_years: int | None = None
    tenure_at_company_months: int | None = None
    open_link: bool | None = None


class SalesNavSearchOutput(BaseModel):
    results: list[SalesNavPersonItem] | None = None
    result_count: int | None = None
    total_available: int | None = None
    page: int | None = None
    source_url: str | None = None
    source_provider: str = "rapidapi_salesnav"
