from typing import Optional, Any
from enum import StrEnum
from pydantic import BaseModel, Field
from openai.types.chat import ChatCompletionMessageToolCall
from uuid import UUID


class ChatMessage(BaseModel):
    role: str
    content: Optional[str | list] = None
    tool_calls: Optional[list[ChatCompletionMessageToolCall]] = None
    tool_call_id: Optional[str] = None


class AgentPayload(BaseModel):
    messages: list[ChatMessage]
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    is_final: Optional[bool] = False

    @property
    def last_message(self) -> ChatMessage:
        return self.messages[-1]

    model_config = {"extra": "allow"}


class URLDisplayType(StrEnum):
    blank = "blank"
    download = "download"
    viewer = "viewer"
    no_show = "no_show"


class SourceChunk(BaseModel):
    name: str
    document_name: str
    content: str
    url: Optional[str] = None
    url_display_type: URLDisplayType = URLDisplayType.viewer
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourcedResponse(BaseModel):
    response: str
    sources: list[SourceChunk]
    is_successful: Optional[bool] = None


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
