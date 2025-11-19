from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.database.models import EvaluationType


class LLMJudgeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    evaluation_type: EvaluationType
    llm_model_reference: str = "openai:gpt-5-mini"
    prompt_template: str
    temperature: Optional[float] = 1.0


class LLMJudgeResponse(LLMJudgeCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class LLMJudgeUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    evaluation_type: Optional[EvaluationType] = None
    llm_model_reference: Optional[str] = None
    prompt_template: Optional[str] = None
    temperature: Optional[float] = None
