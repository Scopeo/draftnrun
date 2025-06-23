from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass
class TracingSpanParams:
    project_id: str
    org_id: str
    llm_providers: list[str]


_tracing_context: ContextVar[Optional[TracingSpanParams]] = ContextVar("_tracing_context", default=None)


def set_tracing_span(project_id: str, org_id: str, llm_providers: list[str]) -> None:
    """Set current tracing context with project/org/llm info."""
    params = TracingSpanParams(project_id, org_id, llm_providers)
    _tracing_context.set(params)


def get_tracing_span() -> Optional[TracingSpanParams]:
    """Retrieve the current tracing context, if any."""
    return _tracing_context.get()
