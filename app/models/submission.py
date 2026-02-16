# app/models/submission.py — Submission schemas

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SubmissionBase(BaseModel):
    company_id: str
    recipe_id: str
    data: list[dict[str, Any]]


class SubmissionCreate(SubmissionBase):
    pass


class Submission(SubmissionBase):
    id: str
    org_id: str
    status: SubmissionStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
