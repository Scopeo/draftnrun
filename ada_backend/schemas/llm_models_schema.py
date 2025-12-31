from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ModelCapabilityEnum(str, Enum):
    """Enum for model capabilities that can be selected"""

    FILE = "file"
    IMAGE = "image"
    CONSTRAINED_OUTPUT = "constrained_output"
    FUNCTION_CALLING = "function_calling"
    WEB_SEARCH = "web_search"
    OCR = "ocr"
    EMBEDDING = "embedding"
    COMPLETION = "completion"
    REASONING = "reasoning"


class ModelCapabilityOption(BaseModel):
    """Model capability option for selection"""

    value: str
    label: str


class ModelCapabilitiesResponse(BaseModel):
    """Response containing all available model capabilities"""

    capabilities: list[ModelCapabilityOption]


class LLMModelCreate(BaseModel):
    display_name: str
    description: str | None = None
    provider: str
    model_name: str
    model_capacity: list[ModelCapabilityEnum] | None = Field(
        default=None,
        description="List of model capabilities.",
    )
    credits_per_input_token: Optional[float] = None
    credits_per_output_token: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)


class LLMModelResponse(LLMModelCreate):
    id: UUID
    created_at: datetime
    updated_at: datetime

    def get_reference(self) -> str:
        return f"{self.provider}:{self.model_name}"


class LLMModelUpdate(LLMModelCreate):
    pass
