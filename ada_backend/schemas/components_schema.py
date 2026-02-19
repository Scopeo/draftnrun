from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, field_validator

from ada_backend.database import models as db
from ada_backend.database.models import ReleaseStage
from ada_backend.schemas.category_schema import CategoryResponse
from ada_backend.schemas.integration_schema import IntegrationSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO, ParameterGroupSchema


class ComponentSchema(BaseModel):
    id: UUID
    name: str


class SubComponentParamSchema(BaseModel):
    """Give information of a subcomponent"""

    component_version_id: UUID
    parameter_name: str
    is_optional: bool


class ComponentVersionUseInfoSchema(BaseModel):
    component_version_id: UUID
    version_tag: str
    is_agent: bool
    is_protected: bool = False
    function_callable: bool = False
    can_use_function_calling: bool = False
    release_stage: ReleaseStage
    tool_parameter_name: Optional[str] = None
    subcomponents_info: list[SubComponentParamSchema]
    category_ids: List[UUID] = []
    icon: Optional[str] = None


class PortDefinitionSchema(BaseModel):
    name: str
    port_type: str
    is_canonical: bool
    description: Optional[str] = None
    nullable: bool
    default: Optional[Any] = None
    is_tool_input: bool = True


class ComponentWithParametersDTO(ComponentVersionUseInfoSchema, ComponentSchema):
    description: Optional[str]
    tool_description: Optional[dict] = None
    integration: Optional[IntegrationSchema] = None
    parameters: List[ComponentParamDefDTO]
    port_definitions: List[PortDefinitionSchema] = []
    parameter_groups: List[ParameterGroupSchema] = []
    credits_per_call: Optional[float] = None
    credits_per: Optional[dict] = None


class ComponentsResponse(BaseModel):
    components: list[ComponentWithParametersDTO]
    categories: list[CategoryResponse]


class UpdateComponentFieldsRequest(BaseModel):
    is_agent: Optional[bool] = None
    function_callable: Optional[bool] = None
    category_ids: Optional[List[UUID]] = None
    release_stage: Optional[ReleaseStage] = None

    @field_validator("release_stage", mode="before")
    @classmethod
    def normalize_release_stage(cls, v):
        if v is None:
            return v
        if isinstance(v, str):
            try:
                return db.ReleaseStage(v.lower())
            except Exception:
                return v
        return v


class ComponentFieldsOptionsResponse(BaseModel):
    """Available options for component metadata fields."""

    release_stages: List[str]
    categories: List[CategoryResponse]
