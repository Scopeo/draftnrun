from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from settings import settings


def setup_performance_instrumentation(app: FastAPI):
    """Sets up OpenTelemetry traces export to Tempo for performance monitoring."""
    # TODO: Remove this test detection once we have proper test environment configuration
    # Skip performance instrumentation during tests to avoid TracerProvider conflicts
    import sys

    if "pytest" in sys.modules:
        return

    resource = Resource(attributes={"service.name": "ada-backend"})

    tracer_provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=settings.TEMPO_ENDPOINT)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider, excluded_urls="healthz,metrics")
