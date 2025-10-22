from typing import Optional, Dict, Any, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class CreateSpecificApiToolRequest(BaseModel):
    tool_display_name: str = Field(..., min_length=1)

    endpoint: str
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    headers: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = 30
    fixed_parameters: Optional[Dict[str, Any]] = None

    tool_description_id: Optional[UUID] = None
    tool_description_name: str = Field(..., min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    tool_description: Optional[str] = None
    tool_properties: Optional[Dict[str, Any]] = None
    required_tool_properties: Optional[List[str]] = None


class CreatedSpecificApiToolResponse(BaseModel):
    component_instance_id: UUID
    tool_display_name: Optional[str]
    tool_description_id: Optional[UUID]


class ApiToolListItem(BaseModel):
    component_instance_id: UUID
    tool_display_name: str
    description: Optional[str]  # tool_description (agent-facing description from ToolDescription)
    method: Optional[str]
    created_at: datetime
    updated_at: datetime


class ApiToolListResponse(BaseModel):
    tools: List[ApiToolListItem]


class ApiToolDetailResponse(CreateSpecificApiToolRequest):
    component_instance_id: UUID
    component_id: UUID
    tool_description_id: UUID
