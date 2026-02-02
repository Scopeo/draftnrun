from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class QAColumnResponse(BaseModel):
    id: UUID
    dataset_id: UUID
    column_id: UUID
    column_name: str
    column_position: int

    class Config:
        from_attributes = True
