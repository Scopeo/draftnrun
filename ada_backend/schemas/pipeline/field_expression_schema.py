"""Field expression schemas for API requests and responses."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class FieldExpressionUpdateSchema(BaseModel):
    """Nested under a component instance in GraphUpdateSchema."""

    port_definition_id: UUID
    expression_text: str


class FieldExpressionReadSchema(BaseModel):
    """Nested under a component instance in GraphGetResponse."""

    port_definition_id: UUID
    field_name: str
    expression_json: dict
    expression_text: Optional[str] = None
