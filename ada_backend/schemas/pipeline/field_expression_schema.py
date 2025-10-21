"""Field expression schemas for API requests and responses."""

from typing import Optional
from pydantic import BaseModel


class FieldExpressionUpdateSchema(BaseModel):
    """Nested under a component instance in GraphUpdateSchema."""

    field_name: str
    expression_text: str


class FieldExpressionReadSchema(BaseModel):
    """Nested under a component instance in GraphGetResponse."""

    field_name: str
    expression_json: dict
    expression_text: Optional[str] = None
