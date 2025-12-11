from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WidgetTheme(BaseModel):
    primary_color: str = Field(default="#6366F1", pattern=r"^#[0-9A-Fa-f]{6}$")
    secondary_color: str = Field(default="#4F46E5", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    text_color: str = Field(default="#1F2937", pattern=r"^#[0-9A-Fa-f]{6}$")
    border_radius: int = 12
    font_family: str = "Inter, system-ui, sans-serif"
    logo_url: Optional[str] = None


class WidgetConfigBase(BaseModel):
    theme: WidgetTheme = Field(default_factory=WidgetTheme)
    header_message: Optional[str] = None
    first_messages: list[str] = Field(default_factory=list, max_length=20)
    suggestions: list[str] = Field(default_factory=list, max_length=20)
    placeholder_text: str = "Type a message..."
    powered_by_visible: bool = True


class WidgetConfig(WidgetConfigBase):
    rate_limit_config: int = 10
    rate_limit_chat: int = 5
    allowed_origins: list[str] = Field(default_factory=list, max_length=50)


class WidgetCreateSchema(BaseModel):
    name: str
    project_id: UUID
    config: Optional[WidgetConfig] = Field(default_factory=WidgetConfig)


class WidgetUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: Optional[str] = None
    is_enabled: Optional[bool] = None
    config: Optional[WidgetConfig] = None


class WidgetSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    widget_key: str
    project_id: UUID
    organization_id: UUID
    name: str
    is_enabled: bool
    config: WidgetConfig
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WidgetPublicConfigSchema(WidgetConfigBase):
    widget_key: str
    name: str


class WidgetChatRequest(BaseModel):
    message: str = Field(max_length=10000)
    history: list[dict] = Field(default_factory=list)
    conversation_id: Optional[str] = None


class WidgetChatResponse(BaseModel):
    response: str
    conversation_id: str
    trace_id: Optional[str] = None
    artifacts: Optional[dict] = None
    error: Optional[str] = None
