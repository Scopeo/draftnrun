"""
Pydantic schemas for deployment scheduling operations.
Django sync and deployment logic for schedule management.
"""

from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ScheduleSyncResponse(BaseModel):
    """Schema for schedule sync response."""

    schedule_id: int
    schedule_uuid: UUID
    action: str = Field(..., description="'created' or 'updated'")
    periodic_task_id: Optional[int] = Field(None, description="Django-celery-beat task ID")
    message: str


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