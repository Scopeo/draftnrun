from datetime import datetime
from typing import List
from uuid import UUID

from pydantic import BaseModel


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
