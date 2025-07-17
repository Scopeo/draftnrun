from typing import Optional, Any
from enum import StrEnum
from pydantic import BaseModel, Field
from openai.types.chat import ChatCompletionMessageToolCall
from uuid import UUID


class ChatMessage(BaseModel):
    role: str
    content: str | list
    tool_calls: Optional[list[ChatCompletionMessageToolCall]] = None
    tool_call_id: Optional[str] = None


class AgentPayload(BaseModel):
    messages: list[ChatMessage] | str
    error: Optional[str] = None
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    is_final: Optional[bool] = False

    @property
    def main_content(self) -> str:
        if isinstance(self.messages, str):
            return self.messages
        elif isinstance(self.messages, list) and len(self.messages) == 0:
            return ""
        elif isinstance(self.messages, list) and isinstance(self.messages[-1].content, str):
            return self.messages[-1].content
        elif isinstance(self.messages, list) and isinstance(self.messages[-1].content, list):
            return "\n".join([item["text"] for item in self.messages[-1].content if item.get("type") == "text"])
        else:
            raise ValueError("The 'messages' field can only be a string or a list of ChatMessage objects")

    @property
    def last_message(self) -> ChatMessage:
        if isinstance(self.messages, list) and len(self.messages) == 0:
            raise ValueError("No messages in payload")
        elif isinstance(self.messages, list):
            return self.messages[-1]
        elif isinstance(self.messages, str):
            return ChatMessage(role="assistant", content=self.messages)
        else:
            raise ValueError("No content in payload")

    @property
    def files_in_messages(self) -> list[dict]:
        if isinstance(self.messages, list) and isinstance(self.messages[-1].content, list):
            return [
                item["file"] for item in self.messages[-1].content if item.get("type") == "file" and "file" in item
            ]
        else:
            return []

    model_config = {"extra": "allow"}


class SplitPayload(BaseModel):
    agent_payloads: list[AgentPayload] = Field(default_factory=list)

    @property
    def main_content(self) -> str:
        return "\n".join([payload.main_content for payload in self.agent_payloads])


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
