from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, field_validator
from enum import Enum

from ada_backend.database.models import EnvType, RoleType


class Pagination(BaseModel):
    page: int
    size: int
    total_items: int
    total_pages: int


class InputGroundtruthCreate(BaseModel):
    """Schema for creating a new input-groundtruth entry."""

    input: str
    conversation_id: UUID
    role: Optional[RoleType] = None
    order: int


class InputGroundtruthWithVersionResponse(BaseModel):
    """Schema for input-groundtruth response with version output data."""

    input_id: UUID
    input: str
    groundtruth: Optional[str] = None
    output: Optional[str] = None
    version: Optional[EnvType] = None

    class Config:
        from_attributes = True


class PaginatedInputGroundtruthResponse(BaseModel):
    """Schema for paginated input-groundtruth responses with outputs."""

    pagination: Pagination
    inputs_groundtruths: List["InputGroundtruthResponse"]
    output_groundtruths: List["OutputGroundtruthResponse"] = []


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
    input: str
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
    """Schema for updating an input-groundtruth entry with ID and optional output."""

    id: UUID
    input: Optional[str] = None
    role: Optional[RoleType] = None
    order: Optional[int] = None


class OutputGroundtruthUpdateWithId(BaseModel):
    """Schema for updating an output groundtruth entry with ID."""

    id: UUID
    message_id: UUID
    message: Optional[str] = None


class InputGroundtruthDeleteList(BaseModel):
    """Schema for deleting multiple input-groundtruth entries."""

    input_groundtruth_ids: List[UUID]


class InputGroundtruthResponse(BaseModel):
    """Schema for input-groundtruth response."""

    id: UUID
    dataset_id: UUID
    input: str
    conversation_id: UUID
    role: Optional[RoleType] = None
    order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InputGroundtruthResponseList(BaseModel):
    """Schema for multiple input-groundtruth responses."""

    inputs_groundtruths: List[InputGroundtruthResponse]


class OutputGroundtruthResponse(BaseModel):
    """Schema for output groundtruth response."""

    id: UUID
    message: str
    message_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class OutputGroundtruthResponseList(BaseModel):
    """Schema for multiple output groundtruth responses."""

    output_groundtruths: List[OutputGroundtruthResponse]


class ModeType(str, Enum):
    CONVERSATION = "conversation"
    ROW = "row"
