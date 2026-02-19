"""Field expression schemas for API requests and responses."""

from enum import StrEnum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SuggestionKind(StrEnum):
    MODULE = "module"
    PROPERTY = "property"
    VARIABLE = "variable"


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
    query: str


class FieldExpressionSuggestion(BaseModel):
    id: str
    label: str
    insert_text: str
    kind: SuggestionKind
    description: Optional[str] = None
    variable_type: Optional[str] = None
    has_default: Optional[bool] = None


class FieldExpressionAutocompleteResponse(BaseModel):
    suggestions: list[FieldExpressionSuggestion] = []
