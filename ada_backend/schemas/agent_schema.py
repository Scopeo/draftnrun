from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.schemas.parameter_schema import PipelineParameterReadSchema, PipelineParameterSchema
from ada_backend.schemas.pipeline.base import ComponentInstanceSchema
from ada_backend.schemas.pipeline.get_pipeline_schema import ComponentInstanceReadSchema
from ada_backend.schemas.project_schema import GraphRunnerEnvDTO
from ada_backend.schemas.template_schema import InputTemplate


class ProjectAgentSchema(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    icon_color: Optional[str] = None
    template: Optional[InputTemplate] = None


class AgentInfoSchema(BaseModel):
    name: str
    description: Optional[str] = None
    organization_id: UUID
    system_prompt: str
    model_parameters: list[PipelineParameterReadSchema] = []
    tools: list[ComponentInstanceReadSchema] = []
    last_edited_time: Optional[datetime] = None
    last_edited_user_id: Optional[UUID] = None


class AgentUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    system_prompt: str
    model_parameters: list[PipelineParameterSchema] = []
    tools: list[ComponentInstanceSchema] = []


class AgentWithGraphRunnersSchema(ProjectAgentSchema):
    graph_runners: list[GraphRunnerEnvDTO] = []
