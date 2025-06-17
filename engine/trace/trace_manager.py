import logging

from openinference.semconv.resource import ResourceAttributes
from openinference.instrumentation.openai import OpenAIInstrumentor
from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk import trace as trace_sdk

from engine.trace.sql_exporter import SQLSpanExporter


LOGGER = logging.getLogger(__name__)


def setup_tracer(
    project_name: str,
) -> trace_api.Tracer:
    """Setup a tracer with the given project name and collector endpoint."""

    resource = Resource(
        attributes={
            ResourceAttributes.PROJECT_NAME: project_name,
        }
    )

    tracer_provider = trace_sdk.TracerProvider(resource=resource)
    sql_exporter = SQLSpanExporter()
    tracer_provider.add_span_processor(BatchSpanProcessor(sql_exporter))

    trace_api.set_tracer_provider(tracer_provider=tracer_provider)

    tracer = trace_api.get_tracer(__name__)

    OpenAIInstrumentor().instrument()

    LOGGER.info(f"Tracer setup for project: {project_name}")
    return tracer


class TraceManager:
    """A manager to handle traces and spans"""

    def __init__(
        self,
        project_name: str,
    ):

        LOGGER.info("Setting up trace manager")

        self.tracer = setup_tracer(
            project_name=project_name,
        )
        self._project_id = None

    @property
    def project_id(self) -> str:
        return self._project_id

    @project_id.setter
    def project_id(self, project_id: str):
        self._project_id = project_id

    def start_span(self, *args, **kwargs):
        """Context manager to start a span."""
        return self.tracer.start_as_current_span(*args, **kwargs)

    @classmethod
    def from_config(cls, config: dict):
        """Create a TraceManager from a configuration dictionary."""
        return cls(
            project_name=config["project_name"],
        )
