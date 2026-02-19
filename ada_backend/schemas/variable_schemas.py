from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from ada_backend.database.models import VariableType

# --- Variable Definitions ---


class VariableDefinitionUpsertRequest(BaseModel):
    type: VariableType
    description: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    editable: bool = True
    display_order: int = 0


class VariableDefinitionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: Optional[UUID] = None
    name: str
    type: VariableType
    description: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    editable: bool = True
    display_order: int = 0
    created_at: str
    updated_at: str


# --- Variable Sets ---


class VariableSetUpsertRequest(BaseModel):
    values: dict[str, Any]


class VariableSetResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: Optional[UUID] = None
    set_id: str
    values: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str


class VariableSetListResponse(BaseModel):
    variable_sets: list[VariableSetResponse]
