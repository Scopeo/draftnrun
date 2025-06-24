from functools import wraps

from prometheus_client import Counter

from engine.trace.span_context import get_tracing_span

agent_calls = Counter(
    "agent_calls_total",
    "Number of times an agent is called",
    ["class_name", "project_id"],
)


def track_calls(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        class_name = self.__class__.__name__
        params = get_tracing_span()
        agent_calls.labels(class_name=class_name, project_id=str(params.project_id)).inc()
        return func(self, *args, **kwargs)

    return wrapper
