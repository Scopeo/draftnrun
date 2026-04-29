from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptCreateSchema(BaseModel):
    name: str
    description: Optional[str] = None
    content: str = Field(min_length=1)
    sections: Optional[list["PromptSectionInputSchema"]] = None


class PromptUpdateSchema(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PromptVersionCreateSchema(BaseModel):
    content: str = Field(min_length=1)
    change_description: Optional[str] = None
    sections: Optional[list["PromptSectionInputSchema"]] = None


class PromptSectionInputSchema(BaseModel):
    placeholder: str
    section_prompt_id: UUID
    section_prompt_version_id: UUID


class PromptSectionResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    placeholder: str
    section_prompt_id: UUID
    section_prompt_version_id: UUID
    section_prompt_name: Optional[str] = None
    section_version_number: Optional[int] = None
    latest_version_number: Optional[int] = None
    is_latest: bool = True
    position: int


class PromptVersionResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    prompt_id: UUID
    version_number: int
    content: str
    change_description: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    sections: list[PromptSectionResponseSchema] = []


class PromptVersionSummarySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    change_description: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime


class PromptResponseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: Optional[str] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    latest_version: Optional[PromptVersionSummarySchema] = None


class PromptDetailResponseSchema(PromptResponseSchema):
    versions: list[PromptVersionSummarySchema] = []


class PromptPinRequestSchema(BaseModel):
    prompt_version_id: UUID


class PromptPinResponseSchema(BaseModel):
    port_name: str
    component_instance_id: UUID
    component_instance_name: Optional[str] = None
    prompt_id: UUID
    prompt_name: str
    pinned_version_id: UUID
    pinned_version_number: int
    latest_version_number: int
    is_latest: bool


class PromptUsageSchema(BaseModel):
    project_id: UUID
    project_name: str
    component_instance_id: UUID
    component_instance_name: Optional[str] = None
    port_name: str
    pinned_version_id: UUID
    pinned_version_number: int


class DiffOperation(BaseModel):
    op: Literal["equal", "insert", "delete", "replace"]
    from_start: int
    from_end: int
    to_start: int
    to_end: int


class PromptDiffResponseSchema(BaseModel):
    from_version_number: int
    to_version_number: int
    from_content: str
    to_content: str
    operations: list[DiffOperation]
