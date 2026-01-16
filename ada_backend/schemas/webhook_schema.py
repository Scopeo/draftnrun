from enum import StrEnum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class WebhookProcessingStatus(StrEnum):
    DUPLICATE = "duplicate"
    ERROR = "error"
    RECEIVED = "received"


class WebhookProcessingResponseSchema(BaseModel):
    status: WebhookProcessingStatus
    processed: bool
    event_id: Optional[str] = None
    processed_triggers: int = Field(default=0, description="Number of workflows/agents triggered")


class IntegrationTriggerResponse(BaseModel):
    id: str
    webhook_id: str
    project_id: str
    events: Optional[Dict[str, Any]] = None
    filter_options: Optional[Dict[str, Any]] = None
