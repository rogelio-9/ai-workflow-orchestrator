import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class WorkflowCreate(BaseModel):
    name: str
    dag_json: dict[str, Any]
    created_by: uuid.UUID


class WorkflowRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    created_by: uuid.UUID
    dag_json: dict[str, Any]
    version: int
    created_at: datetime
    updated_at: datetime


class WorkflowUpdate(BaseModel):
    name: str | None = None
    dag_json: dict[str, Any] | None = None

class StepResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_id: uuid.UUID
    step_id: uuid.UUID
    status: str | None
    output_json: dict[str, Any] | None
    latency_ms: int | None
    llm_tokens: int | None
    error_message: str | None
    attempt: int | None
    created_at: datetime


class RunCreate(BaseModel):
    workflow_id: uuid.UUID
    input_vars: dict[str, Any] | None = None
    triggered_by: uuid.UUID | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    status: str
    input_vars: dict[str, Any] | None
    started_at: datetime | None
    ended_at: datetime | None
    triggered_by: uuid.UUID | None
    step_results: list[StepResultRead]