# app/models/org.py — Org schemas

from datetime import datetime

from pydantic import BaseModel


class OrgBase(BaseModel):
    name: str


class OrgCreate(OrgBase):
    pass


class Org(OrgBase):
    id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
