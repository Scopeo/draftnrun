from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Discriminator, Field


class BooleanEvaluationResult(BaseModel):
    type: Literal["boolean"] = "boolean"
    result: bool
    justification: str


class ScoreEvaluationResult(BaseModel):
    type: Literal["score"] = "score"
    score: int = Field(ge=0)
    max_score: int = Field(ge=1)
    justification: str


class FreeTextEvaluationResult(BaseModel):
    type: Literal["free_text"] = "free_text"
    result: str
    justification: str


class ErrorEvaluationResult(BaseModel):
    type: Literal["error"] = "error"
    justification: str


EvaluationResult = Annotated[
    Union[
        BooleanEvaluationResult,
        ScoreEvaluationResult,
        FreeTextEvaluationResult,
        ErrorEvaluationResult,
    ],
    Discriminator("type"),
]


class JudgeEvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    judge_id: UUID
    version_output_id: UUID
    evaluation_result: "EvaluationResult"
    created_at: datetime
    updated_at: datetime
