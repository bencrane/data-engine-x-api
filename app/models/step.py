# app/models/step.py — Step registry schemas

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class StepBase(BaseModel):
    name: str
    slug: str
    description: str | None = None
    modal_function_name: str
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None


class StepCreate(StepBase):
    pass


class StepUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    modal_function_name: str | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    is_active: bool | None = None


class Step(StepBase):
    id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
