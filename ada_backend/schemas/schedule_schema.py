"""
Pydantic schemas for scheduled workflow operations.
Follows the same patterns as project_schema.py.
"""

from typing import Any, List, Optional, Dict
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


class ScheduleSyncResponse(BaseModel):
    """Schema for schedule sync response."""

    schedule_id: int
    schedule_uuid: UUID
    action: str = Field(..., description="'created' or 'updated'")
    periodic_task_id: Optional[int] = Field(None, description="Django-celery-beat task ID")
    message: str


class CronComponentConfig(BaseModel):
    """Schema for cron component configuration."""

    component_instance_id: UUID
    cron_expression: str = Field(..., description="Cron expression (e.g., '0 9 * * *')")
    timezone: str = Field(default="UTC", description="Timezone for the schedule")
    enabled: bool = Field(default=True, description="Whether the cron component is enabled")


class ScheduleActionResult(BaseModel):
    """Schema for schedule action result."""

    action: str = Field(..., description="'created' or 'updated'")


class DeploymentSchedulingError(BaseModel):
    """Schema for deployment scheduling error."""

    component_instance_id: Optional[UUID] = Field(None, description="Component instance ID if applicable")
    schedule_id: Optional[int] = Field(None, description="Schedule ID if applicable")
    error: str = Field(..., description="Error message")


class DeploymentSchedulingResponse(BaseModel):
    """Schema for deployment scheduling response."""

    project_id: UUID
    graph_runner_id: UUID
    previous_production_graph_id: Optional[UUID] = Field(None, description="Previous production graph runner ID")
    schedules_updated: int = Field(0, description="Number of schedules updated/created")
    schedules_removed: int = Field(0, description="Number of schedules deleted")
    schedules_errors: List[DeploymentSchedulingError] = Field(
        default_factory=list, description="List of errors encountered"
    )
    message: str = Field("Scheduling handled successfully", description="Summary message")
