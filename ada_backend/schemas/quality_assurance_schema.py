from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class InputGroundtruthCreate(BaseModel):
    """Schema for creating a new input-groundtruth entry."""

    input: str
    groundtruth: Optional[str] = None


class InputGroundtruthWithVersionResponse(BaseModel):
    """Schema for input-groundtruth response with version output data."""

    input_id: UUID
    input: str
    groundtruth: Optional[str] = None
    output: Optional[str] = None
    version_id: Optional[UUID] = None
    version: Optional[str] = None

    class Config:
        from_attributes = True


# Run endpoint schemas
class QARunRequest(BaseModel):
    """Schema for QA run request."""

    version_id: UUID
    input_ids: List[UUID]


class QARunResult(BaseModel):
    """Schema for individual QA run result."""

    input_id: UUID
    input: str
    groundtruth: Optional[str] = None
    output: str
    version_id: UUID
    version: str
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
    input: Optional[str] = None
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
    input: str
    groundtruth: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class InputGroundtruthResponseList(BaseModel):
    """Schema for multiple input-groundtruth responses."""

    inputs_groundtruths: List[InputGroundtruthResponse]


# Dataset schemas
class DatasetCreateList(BaseModel):
    """Schema for creating multiple datasets."""

    datasets: List[str]


class DatasetUpdateWithId(BaseModel):
    """Schema for updating a dataset with ID."""

    id: UUID
    dataset_name: Optional[str] = None


class DatasetUpdateList(BaseModel):
    """Schema for updating multiple datasets."""

    datasets: List[DatasetUpdateWithId]


class DatasetDeleteList(BaseModel):
    """Schema for deleting multiple datasets."""

    dataset_ids: List[UUID]


class DatasetResponse(BaseModel):
    """Schema for dataset response."""

    id: UUID
    project_id: UUID
    dataset_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DatasetListResponse(BaseModel):
    """Schema for multiple dataset responses."""

    datasets: List[DatasetResponse]


# Project Version schemas
class VersionByProjectCreateList(BaseModel):
    """Schema for creating multiple project versions."""

    versions: List[str]


class VersionByProjectResponse(BaseModel):
    """Schema for project version response."""

    id: UUID
    project_id: UUID
    version: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VersionByProjectListResponse(BaseModel):
    """Schema for multiple project version responses."""

    versions: List[VersionByProjectResponse]


class VersionDeleteList(BaseModel):
    """Schema for deleting multiple project versions."""

    version_ids: List[UUID]
