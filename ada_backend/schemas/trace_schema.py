from uuid import UUID

from pydantic import BaseModel

from ada_backend.database.models import CallType, EnvType


class TraceSpan(BaseModel):
    span_id: str
    name: str
    span_kind: str
    start_time: str
    end_time: str
    input: list
    output: list
    documents: list
    model_name: str
    tool_info: dict
    status_code: str
    cumulative_llm_token_count_prompt: int
    cumulative_llm_token_count_completion: int
    llm_token_count_prompt: int | None
    llm_token_count_completion: int | None
    children: list["TraceSpan"]
    environment: EnvType | None
    call_type: CallType | None
    graph_runner_id: UUID | None
    tag_name: str | None = None
    conversation_id: str | None = None
    trace_id: str | None = None
    total_credits: float | None = None

    @classmethod
    def from_dict(cls, data: dict) -> "TraceSpan":
        attributes = data.get("attributes", {})
        return cls(
            span_id=data["span_id"],
            name=data["name"],
            span_kind=data["span_kind"],
            start_time=data["start_time"],
            end_time=data["end_time"],
            input=data.get("input", []),
            output=data.get("output", []),
            documents=data.get("documents", []),
            model_name=data.get("model_name", ""),
            status_code=data["status_code"],
            cumulative_llm_token_count_prompt=data["cumulative_llm_token_count_prompt"],
            cumulative_llm_token_count_completion=data["cumulative_llm_token_count_completion"],
            llm_token_count_prompt=data.get("llm_token_count_prompt"),
            llm_token_count_completion=data.get("llm_token_count_completion"),
            children=[cls.from_dict(child) for child in data.get("children", [])],
            environment=data.get("environment"),
            call_type=data.get("call_type"),
            graph_runner_id=data.get("graph_runner_id"),
            tag_name=data.get("tag_name"),
            conversation_id=attributes.get("conversation_id"),
            trace_id=data.get("trace_id"),
            total_credits=data.get("total_credits"),
        )


class RootTraceSpan(BaseModel):
    trace_id: str
    span_id: str
    name: str
    span_kind: str
    start_time: str
    end_time: str
    input: list
    output: list
    status_code: str
    cumulative_llm_token_count_prompt: int
    cumulative_llm_token_count_completion: int
    llm_token_count_prompt: int | None
    llm_token_count_completion: int | None
    environment: EnvType | None
    call_type: CallType | None
    graph_runner_id: UUID | None
    tag_name: str | None = None
    conversation_id: str | None = None
    total_credits: float | None = None


class Pagination(BaseModel):
    page: int
    size: int
    total_items: int
    total_pages: int


class PaginatedRootTracesResponse(BaseModel):
    pagination: Pagination
    traces: list[RootTraceSpan]
