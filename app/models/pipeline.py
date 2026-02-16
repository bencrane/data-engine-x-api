# app/models/pipeline.py — Pipeline run schemas

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class StepResultStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepResult(BaseModel):
    id: str
    pipeline_run_id: str
    step_id: str
    step_order: int
    status: StepResultStatus
    input_data: dict[str, Any] | None = None
    output_data: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Config:
        from_attributes = True


class PipelineRun(BaseModel):
    id: str
    submission_id: str
    org_id: str
    status: PipelineStatus
    step_results: list[StepResult] = []
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
