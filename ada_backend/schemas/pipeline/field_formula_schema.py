"""Field formula schemas for API requests and responses."""

from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class FieldFormulaUpdateSchema(BaseModel):
    """Formula for a single field on a component instance (PUT request)."""

    component_instance_id: UUID
    field_name: str
    formula_text: str


class FieldFormulaReadSchema(BaseModel):
    """Field formula returned by GET endpoints."""

    component_instance_id: UUID
    field_name: str
    formula_json: dict
    # Optional convenience field for UI; normalized text representation
    formula_text: Optional[str] = None
