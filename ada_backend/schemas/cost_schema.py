from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional


class UsageCreateSchema(BaseModel):
    project_id: UUID
    year: int
    month: int
    credits_used: float


class UsageReadSchema(UsageCreateSchema):
    id: UUID
    created_at: datetime
    updated_at: datetime


class LLMCost(BaseModel):
    credits_per_second: Optional[float] = None
    credits_per_call: Optional[float] = None
    credits_per_input_token: Optional[float] = None
    credits_per_output_token: Optional[float] = None


class LLMCostResponse(LLMCost):
    id: UUID
    llm_model_id: UUID
