import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from ada_backend.database.models import ProjectType

GITHUB_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]+$")


class GitSyncImportRequest(BaseModel):
    github_owner: str = Field(..., description="GitHub repository owner (user or organization)")
    github_repo_name: str = Field(..., description="GitHub repository name")
    branch: str = Field(default="main", description="Branch to watch")
    github_installation_id: int = Field(..., description="GitHub App installation ID")
    project_type: ProjectType = Field(default=ProjectType.WORKFLOW, description="Type of project to create")

    @field_validator("github_owner")
    @classmethod
    def validate_github_owner(cls, v: str) -> str:
        if not v or not GITHUB_NAME_RE.match(v):
            raise ValueError("github_owner must be a valid GitHub username or organization name")
        return v

    @field_validator("github_repo_name")
    @classmethod
    def validate_github_repo_name(cls, v: str) -> str:
        if not v or not GITHUB_NAME_RE.match(v):
            raise ValueError("github_repo_name must be a valid GitHub repository name")
        return v

    @field_validator("branch")
    @classmethod
    def validate_branch(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("branch must be a non-empty string")
        return v

    @field_validator("github_installation_id")
    @classmethod
    def validate_github_installation_id(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("github_installation_id must be a positive integer")
        return v


class GitSyncImportResult(BaseModel):
    graph_folder: str
    project_id: UUID
    project_name: str
    config_id: UUID
    status: str


class GitSyncImportResponse(BaseModel):
    imported: list[GitSyncImportResult]
    skipped: list[str] = Field(default_factory=list, description="Folders already linked to a project")


class GitHubRepoSummary(BaseModel):
    full_name: str = ""
    name: str = ""
    owner: str = ""
    default_branch: str = "main"
    private: bool = False


class GitHubAppInfoResponse(BaseModel):
    configured: bool
    install_url: str | None = None


class GitSyncConfigResponse(BaseModel):
    id: UUID
    organization_id: UUID
    project_id: UUID
    github_owner: str
    github_repo_name: str
    graph_folder: str
    branch: str
    github_installation_id: int
    last_sync_at: datetime | None = None
    last_sync_status: str | None = None
    last_sync_commit_sha: str | None = None
    last_sync_error: str | None = None
    created_at: datetime
    updated_at: datetime
