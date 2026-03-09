from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ada_backend.database.models import CallType, RunStatus


class RunCreateSchema(BaseModel):
    trigger: CallType = CallType.API


class RunUpdateStatusSchema(BaseModel):
    """Schema for updating run status, error, and/or trace_id."""

    status: RunStatus
    error: Optional[dict] = None
    trace_id: Optional[str] = None


class RunResponseSchema(BaseModel):
    """Response schema for a run."""

    id: UUID
    project_id: UUID
    status: RunStatus
    trigger: CallType
    webhook_id: Optional[UUID] = None
    integration_trigger_id: Optional[UUID] = None
    trace_id: Optional[str] = None
    result_id: Optional[str] = None
    error: Optional[dict] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunListPagination(BaseModel):
    """Pagination metadata for run list."""

    page: int = Field(description="Current page (1-based)")
    page_size: int = Field(description="Number of items per page")
    total_items: int = Field(description="Total number of runs")
    total_pages: int = Field(description="Total number of pages")


class RunListResponse(BaseModel):
    """Paginated response for listing runs of a project."""

    runs: list[RunResponseSchema]
    pagination: RunListPagination
