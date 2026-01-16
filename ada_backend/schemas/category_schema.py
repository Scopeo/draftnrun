from uuid import UUID

from pydantic import BaseModel


class CategoryResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    icon: str | None
    display_order: int


class CategoryCreateSchema(BaseModel):
    name: str
    description: str | None = None
    icon: str | None = None
    display_order: int = 0


class CategoryUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    display_order: int | None = None
