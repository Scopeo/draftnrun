from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class CreateSpecificApiToolRequest(BaseModel):
    tool_display_name: str = Field(..., min_length=1)

    endpoint: str
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    headers: Optional[Dict[str, Any]] = None
    timeout: Optional[int] = 30
    fixed_parameters: Optional[Dict[str, Any]] = None

    tool_description_name: str = Field(..., min_length=1, pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    tool_description: Optional[str] = None
    tool_properties: Optional[Dict[str, Any]] = None
    required_tool_properties: Optional[List[str]] = None


class CreatedSpecificApiToolResponse(BaseModel):
    component_version_id: UUID
    name: Optional[str]
    tool_description_id: Optional[UUID]
