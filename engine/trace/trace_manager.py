import logging
from typing import Optional

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
        self._organization_id = None
        self._organization_provider_keys = None

    @property
    def project_id(self) -> str:
        return self._project_id

    @project_id.setter
    def project_id(self, project_id: str):
        self._project_id = project_id

    @property
    def organization_id(self) -> str:
        """Get the organization ID."""
        return self._organization_id

    @organization_id.setter
    def organization_id(self, organization_id: str):
        """Set the organization ID."""
        self._organization_id = organization_id

    def start_span(
        self,
        name: str,
        project_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        organization_llm_providers: Optional[str] = None,
        **kwargs,
    ):
        """
        Context manager to start a span.
        Accepts project_id, organization_id, and organization_llm_providers directly
        as arguments to add them as span attributes.
        """
        attributes: Attributes = kwargs.pop("attributes", {})

        if project_id:
            attributes["project_id"] = project_id
        if organization_id:
            attributes["organization_id"] = organization_id
        if organization_llm_providers:
            attributes["organization_llm_providers"] = organization_llm_providers

        kwargs["attributes"] = attributes
        return self.tracer.start_as_current_span(name, **kwargs)

    @property
    def organization_llm_providers(self) -> list:
        """Get the organization key providers."""
        return self._organization_provider_keys

    @organization_llm_providers.setter
    def organization_llm_providers(self, organization_key_providers: list):
        """Set the organization key providers."""
        self._organization_provider_keys = organization_key_providers

    @classmethod
    def from_config(cls, config: dict):
        """Create a TraceManager from a configuration dictionary."""
        return cls(
            project_name=config["project_name"],
        )
