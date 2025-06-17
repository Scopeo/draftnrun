from typing import List, Union

from pydantic import BaseModel


class KPI(BaseModel):
    title: str
    color: str
    icon: str
    stats: str
    change: str


class KPISResponse(BaseModel):
    kpis: List[KPI]


class TraceKPIS(BaseModel):
    tokens_count: Union[int, float]
    token_comparison_percentage: float
    average_latency: Union[int, float]
    latency_comparison_percentage: float
    nb_request: int
    nb_request_comparison_percentage: float


class OccurenceQuestion(BaseModel):
    question: str
    occurence: int


class OccurenceQuestionsList(BaseModel):
    questions: list[OccurenceQuestion]
