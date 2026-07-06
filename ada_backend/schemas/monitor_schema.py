from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel


class KPI(BaseModel):
    title: str
    color: str
    icon: str
    stats: str
    change: str


class KPISResponse(BaseModel):
    kpis: List[KPI]


class CostKPI(BaseModel):
    cost_per_call: Union[int, float]
    cost_per_conversation: Union[int, float]


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


class OrgTokenUsageByModel(BaseModel):
    model_id: Optional[UUID] = None
    provider: Optional[str] = None
    model_name: Optional[str] = None
    display_name: Optional[str] = None
    input_tokens: int
    output_tokens: int
    total_tokens: int


class OrgTokenUsageTotals(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class OrgTokenUsagePeriod(BaseModel):
    year: int
    month: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    by_model: list[OrgTokenUsageByModel]


class OrgTokenUsageResponse(BaseModel):
    organization_id: UUID
    periods: list[OrgTokenUsagePeriod]
    totals: OrgTokenUsageTotals
