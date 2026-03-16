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
    project_ids: Optional[list[UUID]] = Field(
        default=None,
        description="Project IDs to scope this definition to. Omit to leave unchanged. Send [] to make global.",
    )


class VariableDefinitionResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_ids: list[UUID] = []
    name: str
    type: VariableType
    description: Optional[str] = None
    required: bool = False
    default_value: Optional[str] = None
    has_default_value: bool = False
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
    variable_type: VariableType = VariableType.VARIABLE
    values: dict[str, Any] = Field(default_factory=dict)
    oauth_connection_id: Optional[UUID] = None
    created_at: str
    updated_at: str


class VariableSetListResponse(BaseModel):
    variable_sets: list[VariableSetResponse]


class SetIdsResponse(BaseModel):
    set_ids: list[str]
