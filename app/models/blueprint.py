# app/models/blueprint.py — Blueprint schemas

from datetime import datetime

from pydantic import BaseModel


class BlueprintStepConfig(BaseModel):
    step_id: str
    order: int
    config: dict | None = None


class BlueprintBase(BaseModel):
    name: str
    description: str | None = None
    steps: list[BlueprintStepConfig]


class BlueprintCreate(BlueprintBase):
    pass


class BlueprintUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[BlueprintStepConfig] | None = None
    is_active: bool | None = None


class Blueprint(BlueprintBase):
    id: str
    org_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
