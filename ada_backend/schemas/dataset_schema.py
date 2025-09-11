from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


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
