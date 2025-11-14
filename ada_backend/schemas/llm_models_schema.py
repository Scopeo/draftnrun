from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime


class LLMModelResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    reference: str | None = None
    provider: str
    model_capacity: list[str] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LLMModelCreate(BaseModel):
    name: str
    description: str | None = None
    provider: str
    model_capacity: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)


class LLMModelUpdate(LLMModelCreate):
    id: UUID
