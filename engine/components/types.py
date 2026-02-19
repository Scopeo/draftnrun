from enum import StrEnum
from typing import TYPE_CHECKING, Any, Dict, Optional
from uuid import UUID

from openai.types.chat import ChatCompletionMessageToolCall
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ada_backend.database.models import PortSetupMode


class NodeData(BaseModel):
    """The universal data packet flowing between nodes."""

    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="The data payload being passed between nodes",
    )
    ctx: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution context and variables for the current node execution",
    )


class ChatMessage(BaseModel):
    role: str
    content: Optional[str | list] = None
    tool_calls: Optional[list[ChatCompletionMessageToolCall]] = None
    tool_call_id: Optional[str] = None

    def to_string(self) -> str:
        """Convert ChatMessage to string by returning the content field."""
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            # Handle list content (e.g., from multimodal messages)
            return " ".join(str(item) for item in self.content if item)
        return ""


class AgentPayload(BaseModel):
    messages: list[ChatMessage]
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    is_final: Optional[bool] = False

    @property
    def last_message(self) -> ChatMessage:
        return self.messages[-1]

    def to_string(self) -> str:
        """Extract string content from AgentPayload, prioritizing last user message."""
        if not self.messages:
            return ""

        # Find the last user message
        for message in reversed(self.messages):
            if message.role == "user" and message.content:
                return message.to_string()

        # Fallback to last message regardless of role
        if self.messages:
            return self.messages[-1].to_string()

        return ""

    model_config = {"extra": "allow"}


class URLDisplayType(StrEnum):
    blank = "blank"
    download = "download"
    viewer = "viewer"
    no_show = "no_show"


class SourceChunk(BaseModel):
    name: str
    document_name: Optional[str] = None
    content: str
    url: Optional[str] = None
    url_display_type: URLDisplayType = URLDisplayType.viewer
    tool_name: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_string(self) -> str:
        """Convert SourceChunk to string by returning the content field."""
        return self.content


class SourcedResponse(BaseModel):
    response: str
    sources: list[SourceChunk]
    is_successful: Optional[bool] = None

    def to_string(self) -> str:
        """Convert SourcedResponse to string by returning the response field."""
        return self.response


class TermDefinition(BaseModel):
    term: str
    definition: str


class DocumentContent(BaseModel):
    document_name: str
    content_document: str


class ToolDescription(BaseModel):
    name: str
    description: str
    tool_properties: dict[str, dict[str, Any]]
    required_tool_properties: list[str]

    @property
    def openai_format(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.tool_properties,
                    "required": self.required_tool_properties,
                },
            },
        }

    @property
    def is_tool(self) -> bool:
        return self.tool_properties != {}

    @property
    def parameters(self) -> dict:
        return self.openai_format.get("function", {}).get("parameters", {})


class ComponentAttributes(BaseModel):
    component_instance_name: str
    component_instance_id: Optional[UUID] = None


class ToolPortConfigurationSchema(BaseModel):
    id: Optional[UUID] = None
    parameter_id: Optional[UUID] = None  # References parameter ID (port_definition.id for INPUT parameters)
    setup_mode: "PortSetupMode"  # Imported from ada_backend.database.models
    field_expression_id: Optional[UUID] = None
    expression_json: Optional[dict] = None  # For creating new field expressions
    ai_name_override: Optional[str] = None
    ai_description_override: Optional[str] = None
    is_required_override: Optional[bool] = None
    # Custom port fields
    custom_port_name: Optional[str] = None
    custom_port_description: Optional[str] = None
    custom_parameter_type: Optional[str] = None
    custom_ui_component_properties: Optional[dict] = None
