"""Port instance schemas for API requests and responses."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FieldExpressionSchema(BaseModel):
    """Schema for field expression data."""

    id: Optional[UUID] = None
    expression_json: dict


class InputPortInstanceSchema(BaseModel):
    """Schema for input port instance."""

    id: Optional[UUID] = None
    name: str
    port_definition_id: Optional[UUID] = None
    field_expression_id: Optional[UUID] = None
    field_expression: Optional[FieldExpressionSchema] = None
    description: Optional[str] = None


class InputPortInstanceCreateSchema(BaseModel):
    """Schema for creating an input port instance."""

    name: str
    port_definition_id: Optional[UUID] = None
    expression_json: Optional[dict] = None
    description: Optional[str] = None
