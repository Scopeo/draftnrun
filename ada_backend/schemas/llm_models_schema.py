from pydantic import BaseModel, ConfigDict
from uuid import UUID


class LLMModelsResponse(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    reference: str
    provider: str
    model_capacity: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)


class LLMModelsCreate(BaseModel):
    name: str
    description: str | None = None
    provider: str
    model_capacity: list[str] | None = None

    model_config = ConfigDict(from_attributes=True)


class LLMModelsUpdate(LLMModelsCreate):
    id: UUID
