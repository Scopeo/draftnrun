import contextvars
from typing import Optional

from engine.trace.trace_manager import TraceManager

trace_manager_var: contextvars.ContextVar[Optional[TraceManager]] = contextvars.ContextVar(
    "trace_manager", default=None
)


def set_trace_manager(tm: TraceManager):
    trace_manager_var.set(tm)


def get_trace_manager() -> Optional[TraceManager]:
    return trace_manager_var.get()
