from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, field_validator

from ada_backend.schemas.integration_schema import IntegrationSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO


class ComponentSchema(BaseModel):
    id: UUID
    name: str


class SubComponentParamSchema(BaseModel):
    """Give information of a subcomponent"""

    version_id: UUID
    parameter_name: str
    is_optional: bool


class ComponentUseInfoSchema(BaseModel):
    version_id: UUID
    version_tag: str
    is_agent: bool
    is_protected: bool = False
    function_callable: bool = False
    can_use_function_calling: bool = False
    release_stage: str
    tool_parameter_name: Optional[str] = None
    subcomponents_info: list[SubComponentParamSchema]
    categories: List[str] = []
    icon: Optional[str] = None


class PortDefinitionSchema(BaseModel):
    name: str
    port_type: str
    is_canonical: bool
    description: Optional[str] = None


class ComponentWithParametersDTO(ComponentUseInfoSchema, ComponentSchema):
    description: Optional[str]
    tool_description: Optional[dict] = None
    integration: Optional[IntegrationSchema] = None
    parameters: List[ComponentParamDefDTO]
    port_definitions: List[PortDefinitionSchema] = []


class ComponentsResponse(BaseModel):
    components: list[ComponentWithParametersDTO]


class UpdateComponentReleaseStageRequest(BaseModel):
    release_stage: db.ReleaseStage

    @field_validator("release_stage", mode="before")
    @classmethod
    def normalize_release_stage(cls, v):
        if isinstance(v, str):
            try:
                return db.ReleaseStage(v.lower())
            except Exception:
                return v
        return v
