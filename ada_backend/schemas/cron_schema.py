from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from ada_backend.database.models import CronStatus, CronEntrypoint


class CronJobBase(BaseModel):
    """Base schema for cron job data."""

    name: str = Field(..., description="Human-readable name for the cron job")
    cron_expr: str = Field(..., description="Cron expression (e.g., '0 9 * * 1-5')")
    tz: str = Field(..., description="IANA timezone (e.g., 'America/Santiago')")
    entrypoint: CronEntrypoint = Field(..., description="Function entrypoint to execute")
    payload: Dict[str, Any] = Field(default_factory=dict, description="JSON payload for the entrypoint")


class CronJobCreate(CronJobBase):
    """Schema for creating a new cron job."""

    pass


class CronJobUpdate(BaseModel):
    """Schema for updating an existing cron job."""

    name: Optional[str] = Field(None, description="New name for the cron job")
    cron_expr: Optional[str] = Field(None, description="New cron expression")
    tz: Optional[str] = Field(None, description="New timezone")
    entrypoint: Optional[CronEntrypoint] = Field(None, description="New entrypoint")
    payload: Optional[Dict[str, Any]] = Field(None, description="New payload")
    is_enabled: Optional[bool] = Field(None, description="Whether the cron job is enabled")


class CronJobResponse(CronJobBase):
    """Schema for cron job responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class CronRunResponse(BaseModel):
    """Schema for cron run responses."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cron_id: UUID
    scheduled_for: datetime
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: CronStatus
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


class CronJobWithRuns(CronJobResponse):
    """Schema for cron job with recent runs."""

    recent_runs: List[CronRunResponse] = Field(default_factory=list, description="Recent execution runs")


class CronJobListResponse(BaseModel):
    """Schema for listing cron jobs."""

    cron_jobs: List[CronJobResponse]
    total: int


class CronRunListResponse(BaseModel):
    """Schema for listing cron runs."""

    runs: List[CronRunResponse]
    total: int


class CronJobDeleteResponse(BaseModel):
    """Schema for cron job deletion response."""

    id: UUID
    message: str = "Cron job deleted successfully"


class CronJobPauseResponse(BaseModel):
    """Schema for cron job pause/resume response."""

    id: UUID
    is_enabled: bool
    message: str
