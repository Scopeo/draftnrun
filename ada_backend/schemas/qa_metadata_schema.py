from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel


class QAColumnCreate(BaseModel):
    """Schema for creating a new custom column."""

    column_name: str


class QAColumnRename(BaseModel):
    """Schema for renaming a custom column."""

    column_name: str


class QAColumnResponse(BaseModel):
    """Schema for QA column response."""

    id: UUID
    dataset_id: UUID
    column_id: UUID
    column_name: str
    index_position: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class QAColumnListResponse(BaseModel):
    """Schema for multiple QA column responses."""

    columns: List[QAColumnResponse]
