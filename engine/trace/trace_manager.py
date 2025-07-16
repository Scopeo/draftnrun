import logging

from openinference.semconv.resource import ResourceAttributes
from opentelemetry import trace as trace_api
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk import trace as trace_sdk

from engine.trace.sql_exporter import SQLSpanExporter
from engine.trace.span_context import get_tracing_span

LOGGER = logging.getLogger(__name__)


def setup_tracer(
    project_name: str,
) -> tuple[trace_api.Tracer, trace_sdk.TracerProvider]:
    """Set up a tracer with the given project name and collector endpoint."""

    resource = Resource(
        attributes={
            ResourceAttributes.PROJECT_NAME: project_name,
        }
    )

    tracer_provider = trace_sdk.TracerProvider(resource=resource)

    # Add error handling for SQL exporter initialization
    try:
        sql_exporter = SQLSpanExporter()
        tracer_provider.add_span_processor(BatchSpanProcessor(sql_exporter))
        LOGGER.info(f"SQL exporter initialized for project: {project_name}")
    except Exception as e:
        LOGGER.error(f"Failed to initialize SQL exporter: {e}")
        # Continue without database persistence

    tracer = tracer_provider.get_tracer(__name__)

    LOGGER.info(f"Tracer setup for project: {project_name}")
    return tracer, tracer_provider


# TODO: Rename so it's clear that these are the traces for user agents
class TraceManager:
    """A manager to handle traces and spans"""

    def __init__(
        self,
        project_name: str,
    ):

        LOGGER.info("Setting up trace manager")

        self.tracer, self.tracer_provider = setup_tracer(
            project_name=project_name,
        )

    def start_span(
        self,
        name: str,
        isolate_context: bool = False,
        **kwargs,
    ):
        """
        Context manager to start a span.

        Args:
            name: Name of the span
            isolate_context: If True, creates a root span with no parent (for trace isolation)
            **kwargs: Additional arguments passed to start_as_current_span.
        """
        attributes = kwargs.pop("attributes", {})
        params = get_tracing_span()

        if params:
            attributes["project_id"] = params.project_id
            attributes["organization_id"] = params.organization_id
            attributes["organization_llm_providers"] = params.organization_llm_providers
            attributes["conversation_id"] = params.conversation_id

        # Handle trace isolation for root spans
        if isolate_context:
            kwargs["context"] = Context()

        return self.tracer.start_as_current_span(
            name=name,
            attributes=attributes,
            **kwargs,
        )

    def force_flush(self):
        """Force flush all pending spans to the exporter."""
        self.tracer_provider.force_flush()

    @classmethod
    def from_config(cls, config: dict):
        """Create a TraceManager from a configuration dictionary."""
        return cls(
            project_name=config["project_name"],
        )
