from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ada_backend.database.models import CallType, EnvType, RunStatus


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
    env: Optional[EnvType] = None
    webhook_id: Optional[UUID] = None
    integration_trigger_id: Optional[UUID] = None
    event_id: Optional[str] = None
    trace_id: Optional[str] = None
    result_id: Optional[str] = None
    error: Optional[dict] = None
    retry_group_id: Optional[UUID] = None
    attempt_number: int = Field(default=1, ge=1)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @field_validator("error", mode="before")
    @classmethod
    def _coerce_error(cls, v: object) -> object:
        if isinstance(v, str):
            return {"message": v}
        return v


class RunListPagination(BaseModel):
    """Pagination metadata for run list."""

    page: int = Field(description="Current page (1-based)")
    page_size: int = Field(description="Number of items per page")
    total_items: int = Field(description="Total number of runs")
    total_pages: int = Field(description="Total number of pages")


class AsyncRunAcceptedSchema(BaseModel):
    """Response when an async run is accepted (202)."""

    run_id: UUID
    status: str = "pending"


class OrgRunResponseSchema(BaseModel):
    id: UUID
    project_id: UUID
    project_name: str
    status: RunStatus
    trigger: CallType
    env: Optional[EnvType] = None
    trace_id: Optional[str] = None
    error: Optional[dict] = None
    retry_group_id: Optional[UUID] = None
    attempt_number: int = Field(default=1, ge=1)
    attempt_count: int = Field(default=1, ge=1)
    input_available: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime

    @field_validator("error", mode="before")
    @classmethod
    def _coerce_error(cls, v: object) -> object:
        if isinstance(v, str):
            return {"message": v}
        return v


class OrgRunListResponse(BaseModel):
    runs: list[OrgRunResponseSchema]
    pagination: RunListPagination


class RunRetrySchema(BaseModel):
    env: Optional[EnvType] = None
    graph_runner_id: Optional[UUID] = None

    @model_validator(mode="after")
    def validate_target(self):
        if self.env is None and self.graph_runner_id is None:
            raise ValueError("Either env or graph_runner_id must be provided")
        return self
