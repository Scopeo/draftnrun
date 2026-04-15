import dataclasses
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID

import sentry_sdk
from e2b_code_interpreter import AsyncSandbox

from ada_backend.database.models import CallType, EnvType

LOGGER = logging.getLogger(__name__)


@dataclass
class TracingSpanParams:
    project_id: str = ""
    organization_id: str = ""
    organization_llm_providers: list[str] = field(default_factory=list)
    conversation_id: Optional[str] = None
    uuid_for_temp_folder: Optional[str] = None
    environment: Optional[EnvType] = None
    call_type: Optional[CallType] = None
    trace_id: Optional[str] = None
    graph_runner_id: Optional[UUID] = None
    tag_name: Optional[str] = None
    cron_id: Optional[str] = None
    shared_sandbox: Optional["AsyncSandbox"] = None


_tracing_context: ContextVar[Optional[TracingSpanParams]] = ContextVar("_tracing_context", default=None)

_SPAN_FIELDS = {f.name for f in dataclasses.fields(TracingSpanParams)}
SENTRY_TAG_FIELDS = (
    "cron_id",
    "trace_id",
    "project_id",
    "organization_id",
    "environment",
    "call_type",
    "graph_runner_id",
    "tag_name",
)


def _sync_to_sentry(params: TracingSpanParams) -> None:
    isolation_scope = sentry_sdk.get_isolation_scope()
    for field_name in SENTRY_TAG_FIELDS:
        field_value = getattr(params, field_name)
        if field_value is None:
            isolation_scope.remove_tag(field_name)
            continue
        sentry_sdk.set_tag(field_name, str(field_value))


def set_tracing_span(**kwargs) -> None:
    """Set or merge tracing context fields.

    When a context already exists, only the provided fields are updated;
    all other fields (e.g. cron_id set upstream) are preserved.
    """
    invalid = set(kwargs) - _SPAN_FIELDS
    if invalid:
        LOGGER.warning("Unknown tracing span fields: %s", sorted(invalid))
        raise TypeError(f"Unknown tracing span fields: {invalid}")
    existing = _tracing_context.get()
    if existing:
        params = dataclasses.replace(existing, **kwargs)
    else:
        params = TracingSpanParams(**kwargs)
    _tracing_context.set(params)
    _sync_to_sentry(params)


def get_tracing_span() -> Optional[TracingSpanParams]:
    """Retrieve the current tracing context, if any."""
    return _tracing_context.get()
