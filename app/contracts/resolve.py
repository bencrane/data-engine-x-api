from pydantic import BaseModel


class ResolveDomainOutput(BaseModel):
    domain: str | None = None
    cleaned_company_name: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolveLinkedInOutput(BaseModel):
    company_linkedin_url: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolvePersonLinkedInOutput(BaseModel):
    person_linkedin_url: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"


class ResolveLocationOutput(BaseModel):
    company_city: str | None = None
    company_state: str | None = None
    company_country: str | None = None
    resolve_source: str | None = None
    source_provider: str = "revenueinfra"
