"""
Pydantic schemas for cron component configuration.
Component-specific cron functionality and scheduling.
"""

from uuid import UUID
from pydantic import BaseModel, Field


class CronComponentConfig(BaseModel):
    """Schema for cron component configuration."""

    component_instance_id: UUID
    cron_expression: str = Field(..., description="Cron expression (e.g., '0 9 * * *')")
    timezone: str = Field(default="UTC", description="Timezone for the schedule")
    enabled: bool = Field(default=True, description="Whether the cron component is enabled")


class ScheduleActionResult(BaseModel):
    """Schema for schedule action result."""

    action: str = Field(..., description="'created' or 'updated'")
