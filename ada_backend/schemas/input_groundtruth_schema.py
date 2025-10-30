from datetime import datetime
from typing import Optional, List
import json
from uuid import UUID
from pydantic import BaseModel, field_validator
from enum import Enum

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

    @field_validator("input", mode="before")
    @classmethod
    def ensure_dict(cls, v):
        # DB may store input as text; accept both dict and JSON string
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                # Fallback to empty dict to avoid 422; adjust as needed
                return {}
        return v

    class Config:
        from_attributes = True


class InputGroundtruthResponseList(BaseModel):
    """Schema for multiple input-groundtruth responses."""

    inputs_groundtruths: List[InputGroundtruthResponse]


class ModeType(str, Enum):
    CONVERSATION = "conversation"
    RAW = "raw"
