from typing import Any, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

from ada_backend.database.models import EnvType, ProjectType
from ada_backend.schemas.template_schema import InputTemplate


class FileResponse(BaseModel):
    filename: str
    content_type: str
    size: int
    data: Optional[str] = None  # base64 if response_format="base64"
    url: Optional[str] = None  # presigned URL if response_format="url"
    s3_key: Optional[str] = None  # S3 key if response_format="s3_key"

    @model_validator(mode="after")
    def validate_data_or_url_or_s3_key(self):
        provided_fields = sum([self.data is not None, self.url is not None, self.s3_key is not None])
        if provided_fields != 1:
            raise ValueError("Exactly one of 'data', 'url', or 's3_key' must be provided")
        return self


class ProjectSchema(BaseModel):
    project_id: UUID
    project_name: str
    description: Optional[str] = None


class ProjectCreateSchema(ProjectSchema):
    template: Optional[InputTemplate] = None


class ProjectUpdateSchema(BaseModel):
    project_name: Optional[str] = None
    description: Optional[str] = None


class ProjectResponse(ProjectSchema):
    organization_id: UUID
    created_at: str
    updated_at: str


class GraphRunnerEnvDTO(BaseModel):
    graph_runner_id: UUID
    env: Optional[EnvType] = None
    tag_version: Optional[str] = None
    version_name: Optional[str] = None
    tag_name: Optional[str] = None
    change_log: Optional[str] = None


class ProjectWithGraphRunnersSchema(ProjectResponse):
    project_type: Optional[ProjectType] = None
    graph_runners: List[GraphRunnerEnvDTO] = Field(default_factory=list)
    is_template: bool = False


class ChatResponse(BaseModel):
    message: str
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None
    files: List[FileResponse] = Field(default_factory=list)


class ProjectDeleteResponse(BaseModel):
    project_id: UUID
    graph_runner_ids: list[UUID] = Field(default_factory=list)
