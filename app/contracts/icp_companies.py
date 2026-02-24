from pydantic import BaseModel


class IcpCompanyItem(BaseModel):
    company_name: str | None = None
    domain: str | None = None
    company_description: str | None = None


class FetchIcpCompaniesOutput(BaseModel):
    company_count: int | None = None
    results: list[IcpCompanyItem] | None = None
    source_provider: str = "revenueinfra"
