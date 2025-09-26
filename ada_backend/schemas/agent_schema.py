from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema, PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema


class ProjectAgentSchema(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None


class AgentInfoSchema(BaseModel):
    name: str
    description: Optional[str] = None
    organization_id: UUID
    system_prompt: str
    model_parameters: list[PipelineParameterReadSchema] = []
    tools: list[ComponentInstanceReadSchema] = []


class AgentUpdateSchema(AgentInfoSchema):
    model_config = ConfigDict(extra="ignore")

    model_parameters: list[PipelineParameterSchema] = []
    tools: list[ComponentInstanceSchema] = []
