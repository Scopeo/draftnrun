from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class QAColumnCreate(BaseModel):
    column_name: str


class QAColumnResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    column_id: UUID
    column_name: str
    column_display_position: int
    default_role: Optional[str] = None

    class Config:
        from_attributes = True
