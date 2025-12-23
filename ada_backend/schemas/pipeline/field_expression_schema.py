"""Field expression schemas for API requests and responses."""

from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import PortType
from engine.field_expressions.autocomplete import FieldExpressionSuggestionKind


class FieldExpressionUpdateSchema(BaseModel):
    """Nested under a component instance in GraphUpdateSchema."""

    field_name: str
    expression_text: str


class FieldExpressionReadSchema(BaseModel):
    """Nested under a component instance in GraphGetResponse."""

    field_name: str
    expression_json: dict
    expression_text: Optional[str] = None


class FieldExpressionAutocompleteRequest(BaseModel):
    target_instance_id: UUID
    expression_text: str
    cursor_offset: int


class FieldExpressionSuggestionDetail(BaseModel):
    instance_id: UUID | None = None
    instance_name: Optional[str] = None
    port_name: Optional[str] = None
    port_type: PortType | None = None
    key: Optional[str] = None


class FieldExpressionSuggestion(BaseModel):
    label: str
    insert_text: str
    kind: FieldExpressionSuggestionKind
    detail: FieldExpressionSuggestionDetail


class FieldExpressionAutocompleteResponse(BaseModel):
    suggestions: list[FieldExpressionSuggestion] = []
