from fastapi import FastAPI
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from settings import settings


def setup_performance_instrumentation(app: FastAPI):
    """Sets up OpenTelemetry traces export to Tempo for performance monitoring."""

    resource = Resource(attributes={"service.name": "ada-backend"})

    tracer_provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint=settings.TEMPO_ENDPOINT)
    tracer_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global provider for auto-instrumentations
    trace_api.set_tracer_provider(tracer_provider)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="healthz,metrics",
    )
