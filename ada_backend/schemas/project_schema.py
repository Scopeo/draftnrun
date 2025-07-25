from typing import Any, List, Optional, Dict
from uuid import UUID
from pydantic import BaseModel, Field

from ada_backend.database.models import EnvType
from ada_backend.schemas.template_schema import InputTemplate


class ProjectSchema(BaseModel):
    project_id: UUID
    project_name: str
    description: Optional[str] = None
    companion_image_url: Optional[str] = None


class ProjectCreateSchema(ProjectSchema):
    template: Optional[InputTemplate] = None


class ProjectUpdateSchema(BaseModel):
    project_name: Optional[str] = None
    description: Optional[str] = None
    companion_image_url: Optional[str] = None


class ProjectResponse(ProjectSchema):
    organization_id: UUID
    created_at: str
    updated_at: str


class GraphRunnerEnvDTO(BaseModel):
    graph_runner_id: UUID
    env: Optional[EnvType] = None


class ProjectWithGraphRunnersSchema(ProjectResponse):
    graph_runners: List[GraphRunnerEnvDTO] = Field(default_factory=list)


class ChatResponse(BaseModel):
    message: str
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)


class ProjectDeleteResponse(BaseModel):
    project_id: UUID
    graph_runner_ids: list[UUID] = Field(default_factory=list)
    cleanup_results: Optional[Dict[str, Any]] = Field(
        default=None, description="Results of scheduled tasks and API key cleanup"
    )
