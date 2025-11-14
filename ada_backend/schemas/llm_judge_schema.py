from datetime import datetime
from typing import Optional, List
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ada_backend.database.models import EvaluationType


class LLMJudgeCreate(BaseModel):
    name: str
    description: Optional[str] = None
    evaluation_type: EvaluationType
    llm_model_reference: str
    prompt_template: str
    temperature: Optional[float] = 0.0


class LLMJudgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    name: str
    description: Optional[str] = None
    evaluation_type: EvaluationType
    llm_model_reference: str
    prompt_template: str
    temperature: Optional[float] = 0.0
    created_at: datetime
    updated_at: datetime


class LLMJudgeListResponse(BaseModel):
    judges: List[LLMJudgeResponse]
