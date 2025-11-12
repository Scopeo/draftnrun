from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator

from ada_backend.database.models import EnvType


class Pagination(BaseModel):
    page: int
    size: int
    total_items: int
    total_pages: int


class InputGroundtruthCreate(BaseModel):
    """Schema for creating a new input-groundtruth entry."""

    input: dict
    groundtruth: Optional[str] = None


class InputGroundtruthFromHistoryCreate(BaseModel):
    """Schema for creating input-groundtruth entry from trace history."""

    trace_id: str
    message_index: int


class InputGroundtruthWithVersionResponse(BaseModel):
    """Schema for input-groundtruth response with version output data."""

    input_id: UUID
    input: dict
    groundtruth: Optional[str] = None
    output: Optional[str] = None
    version: Optional[EnvType] = None

    class Config:
        from_attributes = True


class PaginatedInputGroundtruthResponse(BaseModel):
    """Schema for paginated input-groundtruth responses."""

    pagination: Pagination
    inputs_groundtruths: List["InputGroundtruthResponse"]


# Run endpoint schemas
class QARunRequest(BaseModel):
    """Schema for QA run request.

    Uses graph_runner_id to run a specific version of the workflow.
    """

    graph_runner_id: UUID
    input_ids: Optional[List[UUID]] = None
    run_all: bool = False

    @field_validator("input_ids")
    @classmethod
    def validate_input_ids(cls, v, info):
        """Validate that either input_ids is provided or run_all is True."""
        run_all = info.data.get("run_all", False)

        if run_all and v:
            raise ValueError("Cannot specify both run_all=True and input_ids. Choose one option.")

        if not run_all and not v:
            raise ValueError("Must specify either input_ids or set run_all=True.")

        return v


class QARunResult(BaseModel):
    """Schema for individual QA run result."""

    input_id: UUID
    input: dict
    groundtruth: Optional[str] = None
    output: str
    graph_runner_id: UUID
    success: bool
    error: Optional[str] = None

    class Config:
        from_attributes = True


class QARunSummary(BaseModel):
    """Schema for QA run summary."""

    total: int
    passed: int
    failed: int
    success_rate: float


class QARunResponse(BaseModel):
    """Schema for QA run response."""

    results: List[QARunResult]
    summary: QARunSummary


# List-based operation schemas
class InputGroundtruthCreateList(BaseModel):
    """Schema for creating multiple input-groundtruth entries."""

    inputs_groundtruths: List[InputGroundtruthCreate]


class InputGroundtruthUpdateWithId(BaseModel):
    """Schema for updating an input-groundtruth entry with ID."""

    id: UUID
    input: Optional[dict] = None
    groundtruth: Optional[str] = None


class InputGroundtruthUpdateList(BaseModel):
    """Schema for updating multiple input-groundtruth entries."""

    inputs_groundtruths: List[InputGroundtruthUpdateWithId]


class InputGroundtruthDeleteList(BaseModel):
    """Schema for deleting multiple input-groundtruth entries."""

    input_groundtruth_ids: List[UUID]


class InputGroundtruthResponse(BaseModel):
    """Schema for input-groundtruth response."""

    id: UUID
    dataset_id: UUID
    input: dict
    groundtruth: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InputGroundtruthResponseList(BaseModel):
    """Schema for multiple input-groundtruth responses."""

    inputs_groundtruths: List[InputGroundtruthResponse]
