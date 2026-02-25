from pydantic import BaseModel


class IcpTitleItem(BaseModel):
    title: str
    buyer_role: str | None = None
    reasoning: str | None = None


class ExtractIcpTitlesOutput(BaseModel):
    company_domain: str | None = None
    company_name: str | None = None
    titles: list[IcpTitleItem] | None = None
    title_count: int | None = None
    usage: dict | None = None
    source_provider: str = "modal_anthropic"
