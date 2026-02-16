# app/models/company.py — Company schemas

from datetime import datetime

from pydantic import BaseModel


class CompanyBase(BaseModel):
    name: str
    external_id: str | None = None


class CompanyCreate(CompanyBase):
    pass


class Company(CompanyBase):
    id: str
    org_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
