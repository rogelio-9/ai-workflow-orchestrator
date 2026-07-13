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