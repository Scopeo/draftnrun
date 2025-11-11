from datetime import datetime
from typing import Optional, List, Literal
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
    """Schema for creating input-groundtruth entry from conversation or trace history."""

    source: Literal["conversation", "trace"]
    conversation_id: Optional[UUID] = None
    trace_id: Optional[str] = None
    message_index: int

    @field_validator("conversation_id")
    @classmethod
    def validate_conversation_id(cls, v, info):
        """Validate that conversation_id is provided when source is conversation."""
        source = info.data.get("source")
        if source == "conversation" and not v:
            raise ValueError("conversation_id is required when source is 'conversation'")
        if source == "trace" and v:
            raise ValueError("conversation_id should not be provided when source is 'trace'")
        return v

    @field_validator("trace_id")
    @classmethod
    def validate_trace_id(cls, v, info):
        """Validate that trace_id is provided when source is trace."""
        source = info.data.get("source")
        if source == "trace" and not v:
            raise ValueError("trace_id is required when source is 'trace'")
        if source == "conversation" and v:
            raise ValueError("trace_id should not be provided when source is 'conversation'")
        return v


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
