# app/models/blueprint.py — Blueprint schemas

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class BlueprintStepConfig(BaseModel):
    position: int
    operation_id: str
    step_config: dict[str, Any] | None = None
    fan_out: bool = False
    is_enabled: bool = True


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


class Blueprint(BaseModel):
    id: str
    org_id: str
    name: str
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    steps: list[BlueprintStepConfig]

    class Config:
        from_attributes = True
