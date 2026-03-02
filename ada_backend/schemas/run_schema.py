from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.database.models import CallType, RunStatus


class RunCreateSchema(BaseModel):
    """Schema for creating a run (input_payload optional; project_id comes from path)."""

    input_payload: Optional[dict[str, Any]] = None
    trigger: CallType = CallType.API


class RunUpdateStatusSchema(BaseModel):
    """Schema for updating run status, error, and/or trace_id."""

    status: RunStatus
    error: Optional[str] = None
    trace_id: Optional[str] = None


class RunResponseSchema(BaseModel):
    """Response schema for a run."""

    id: UUID
    project_id: UUID
    status: RunStatus
    trigger: CallType
    trace_id: Optional[str] = None
    input_payload: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
