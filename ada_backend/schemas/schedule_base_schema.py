"""
Pydantic schemas for core scheduled workflow operations.
Basic CRUD operations for schedule management.
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

from ada_backend.database.models import ScheduledWorkflowType


class ScheduleCreateSchema(BaseModel):
    """Schema for creating a new scheduled workflow."""

    organization_id: UUID
    type: ScheduledWorkflowType
    cron_expression: str = Field(..., description="Cron expression (e.g., '*/5 * * * *')")
    timezone: str = Field(default="UTC", description="Timezone for the schedule")
    enabled: bool = Field(default=True, description="Whether the schedule is enabled")
    project_id: Optional[UUID] = Field(None, description="Project UUID (required for Project type)")
    args: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional arguments as JSON")


class ScheduleUpdateSchema(BaseModel):
    """Schema for updating a scheduled workflow."""

    cron_expression: Optional[str] = Field(None, description="Cron expression (e.g., '*/5 * * * *')")
    timezone: Optional[str] = Field(None, description="Timezone for the schedule")
    enabled: Optional[bool] = Field(None, description="Whether the schedule is enabled")
    project_id: Optional[UUID] = Field(None, description="Project UUID")
    args: Optional[Dict[str, Any]] = Field(None, description="Additional arguments as JSON")


class ScheduleResponse(BaseModel):
    """Schema for schedule response."""

    id: int
    uuid: UUID
    organization_id: UUID
    project_id: Optional[UUID]
    type: ScheduledWorkflowType
    cron_expression: str
    timezone: str
    enabled: bool
    args: str
    created_at: str
    updated_at: str


class ScheduleListResponse(BaseModel):
    """Schema for list of schedules response."""

    schedules: List[ScheduleResponse] = Field(default_factory=list)
    count: int = Field(0, description="Total number of schedules")


class ScheduleStatsResponse(BaseModel):
    """Schema for schedule statistics response."""

    total: int = Field(0, description="Total number of schedules")
    enabled: int = Field(0, description="Number of enabled schedules")
    disabled: int = Field(0, description="Number of disabled schedules")


class ScheduleDeleteResponse(BaseModel):
    """Schema for schedule deletion response."""

    schedule_id: int
    message: str = "Schedule deleted successfully" 