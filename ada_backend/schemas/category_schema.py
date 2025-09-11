from uuid import UUID

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    description: str | None


class CategoryUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
