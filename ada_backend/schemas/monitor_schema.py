from typing import List, Optional, Union

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
    token_comparison_percentage: Optional[float] = None
    average_latency: Optional[Union[int, float]] = None
    latency_comparison_percentage: Optional[float] = None
    nb_request: int
    nb_request_comparison_percentage: Optional[float] = None


class OccurenceQuestion(BaseModel):
    question: str
    occurence: int


class OccurenceQuestionsList(BaseModel):
    questions: list[OccurenceQuestion]
