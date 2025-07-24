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
    full_content: Optional[list[ChatMessage] | str] = None
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_final: Optional[bool] = False

    @property
    def content(self) -> str:
        if isinstance(self.full_content, str):
            return self.full_content
        elif isinstance(self.full_content, list) and isinstance(self.full_content[-1].content, str):
            return self.full_content[-1].content
        elif isinstance(self.full_content, list) and isinstance(self.full_content[-1].content, list):
            return "\n".join([item["text"] for item in self.full_content[-1].content if item.get("type") == "text"])
        else:
            raise ValueError("No content in payload")

    @property
    def last_message(self) -> ChatMessage:
        if isinstance(self.full_content, list):
            return self.full_content[-1]
        elif isinstance(self.full_content, str):
            return ChatMessage(role="assistant", content=self.full_content)
        else:
            raise ValueError("No content in payload")

    @property
    def files_in_messages(self) -> list[dict]:
        if isinstance(self.full_content, list) and isinstance(self.full_content[-1].content, list):
            return [
                item["file"] for item in self.full_content[-1].content if item.get("type") == "file" and "file" in item
            ]
        else:
            return []

    model_config = {"extra": "allow"}


class SplitPayload(BaseModel):
    agent_payloads: list[AgentPayload] = Field(default_factory=list)

    @property
    def content(self) -> str:
        return "\n".join([payload.content for payload in self.agent_payloads])


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
