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
    run_id: Optional[str] = None
    shared_sandbox: Optional["AsyncSandbox"] = None


_tracing_context: ContextVar[Optional[TracingSpanParams]] = ContextVar("_tracing_context", default=None)

_SPAN_FIELDS = {f.name for f in dataclasses.fields(TracingSpanParams)}

# Maps TracingSpanParams fields to Sentry tag keys; 'environment' becomes 'env' to avoid conflicts.
# All other fields use their original names.
SENTRY_TAG_FIELDS: dict[str, str] = {
    "run_id": "run_id",
    "cron_id": "cron_id",
    "trace_id": "trace_id",
    "project_id": "project_id",
    "organization_id": "organization_id",
    "environment": "env",
    "call_type": "call_type",
    "graph_runner_id": "graph_runner_id",
    "tag_name": "tag_name",
}

_invalid_sentry_fields = set(SENTRY_TAG_FIELDS) - _SPAN_FIELDS
if _invalid_sentry_fields:
    raise RuntimeError(
        f"SENTRY_TAG_FIELDS contains attributes not defined on TracingSpanParams: " f"{sorted(_invalid_sentry_fields)}"
    )


def _sync_to_sentry(params: TracingSpanParams) -> None:
    isolation_scope = sentry_sdk.get_isolation_scope()
    for attr_name, sentry_key in SENTRY_TAG_FIELDS.items():
        field_value = getattr(params, attr_name)
        if field_value is None:
            isolation_scope.remove_tag(sentry_key)
            isolation_scope.remove_attribute(sentry_key)
            continue
        str_value = str(field_value)
        isolation_scope.set_tag(sentry_key, str_value)
        isolation_scope.set_attribute(sentry_key, str_value)


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


def reset_tracing_span() -> None:
    """Clear the tracing context and matching Sentry tags/attributes on the current isolation scope.

    Intended for top-level execution boundaries where a thread or task is reused across
    independent runs (e.g. `RunQueueWorker.process_payload`). Do not call this inside a
    single logical run: normal code should rely on `set_tracing_span`'s merge semantics
    so that upstream fields (cron_id, project_id, ...) keep propagating.
    """
    _tracing_context.set(None)
    isolation_scope = sentry_sdk.get_isolation_scope()
    for sentry_key in SENTRY_TAG_FIELDS.values():
        isolation_scope.remove_tag(sentry_key)
        isolation_scope.remove_attribute(sentry_key)


def get_tracing_span() -> Optional[TracingSpanParams]:
    """Retrieve the current tracing context, if any."""
    return _tracing_context.get()
