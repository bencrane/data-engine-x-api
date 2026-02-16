# app/models/recipe.py — Recipe schemas

from datetime import datetime

from pydantic import BaseModel


class RecipeStepConfig(BaseModel):
    step_id: str
    order: int
    config: dict | None = None


class RecipeBase(BaseModel):
    name: str
    description: str | None = None
    steps: list[RecipeStepConfig]


class RecipeCreate(RecipeBase):
    pass


class RecipeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    steps: list[RecipeStepConfig] | None = None
    is_active: bool | None = None


class Recipe(RecipeBase):
    id: str
    org_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
