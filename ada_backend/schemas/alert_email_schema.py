from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class AlertEmailCreate(BaseModel):
    email: EmailStr


class AlertEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    email: str
    created_at: datetime
