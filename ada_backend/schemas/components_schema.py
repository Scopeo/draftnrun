from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import ReleaseStage
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
    release_stage: ReleaseStage
    tool_parameter_name: Optional[str] = None
    subcomponents_info: list[SubComponentParamSchema]
    categories: List[str] = []


class ComponentWithParametersDTO(ComponentUseInfoSchema, ComponentSchema):
    description: Optional[str]
    tool_description: Optional[dict] = None
    integration: Optional[IntegrationSchema] = None
    parameters: List[ComponentParamDefDTO]


class ComponentsResponse(BaseModel):
    components: list[ComponentWithParametersDTO]
