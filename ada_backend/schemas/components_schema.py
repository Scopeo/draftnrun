from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, field_validator

from ada_backend.schemas.integration_schema import IntegrationSchema
from ada_backend.schemas.parameter_schema import ComponentParamDefDTO
from ada_backend.database import models as db


class ComponentDTO(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    tool_description: Optional[dict] = None


class SubComponentParamSchema(BaseModel):
    """Give information of a subcomponent"""

    id: UUID
    parameter_name: str
    is_optional: bool


class ComponentUseInfoSchema(BaseModel):
    is_agent: bool
    is_protected: bool = False
    function_callable: bool = False
    can_use_function_calling: bool = False
    release_stage: str = db.ReleaseStage.BETA
    tool_parameter_name: Optional[str] = None
    subcomponents_info: list[SubComponentParamSchema]
    categories: List[str] = []


class ComponentWithParametersDTO(ComponentUseInfoSchema, ComponentDTO):
    integration: Optional[IntegrationSchema] = None
    parameters: List[ComponentParamDefDTO]


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
