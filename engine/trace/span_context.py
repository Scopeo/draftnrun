from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional

from ada_backend.database.models import EnvType, CallType


@dataclass
class TracingSpanParams:
    project_id: str
    organization_id: str
    organization_llm_providers: list[str]
    conversation_id: Optional[str] = None
    uuid_for_temp_folder: Optional[str] = None
    environment: Optional[EnvType] = None
    call_type: Optional[CallType] = None
    trace_id: Optional[str] = None
    graph_runner_id: Optional[str] = None
    tag_name: Optional[str] = None


_tracing_context: ContextVar[Optional[TracingSpanParams]] = ContextVar("_tracing_context", default=None)


def set_tracing_span(
    project_id: str,
    organization_id: str,
    organization_llm_providers: list[str],
    conversation_id: Optional[str] = None,
    uuid_for_temp_folder: Optional[str] = None,
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    graph_runner_id: Optional[str] = None,
    tag_name: Optional[str] = None,
) -> None:
    """Set current tracing context with project/org/llm info."""
    params = TracingSpanParams(
        project_id=project_id,
        organization_id=organization_id,
        organization_llm_providers=organization_llm_providers,
        conversation_id=conversation_id,
        uuid_for_temp_folder=uuid_for_temp_folder,
        environment=environment,
        call_type=call_type,
        graph_runner_id=graph_runner_id,
        tag_name=tag_name,
    )
    _tracing_context.set(params)


def get_tracing_span() -> Optional[TracingSpanParams]:
    """Retrieve the current tracing context, if any."""
    return _tracing_context.get()
