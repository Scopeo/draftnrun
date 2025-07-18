from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel


class QuestionAnswerBase(BaseModel):
    """Base schema for question-answer data."""

    question: str
    groundtruth: str


class QuestionAnswerCreate(QuestionAnswerBase):
    """Schema for creating a new question-answer entry."""

    pass


class QuestionAnswerUpdate(BaseModel):
    """Schema for updating a question-answer entry."""

    question: Optional[str] = None
    groundtruth: Optional[str] = None


class QuestionAnswerResponse(QuestionAnswerBase):
    """Schema for question-answer response."""

    id: UUID
    organization_id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# List-based operation schemas
class QuestionAnswerCreateList(BaseModel):
    """Schema for creating multiple question-answer entries."""

    questions_answers: List[QuestionAnswerCreate]


class QuestionAnswerResponseList(BaseModel):
    """Schema for multiple question-answer responses."""

    questions_answers: List[QuestionAnswerResponse]
