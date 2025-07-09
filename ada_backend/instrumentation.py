from fastapi import FastAPI
from opentelemetry import trace as trace_api
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import ReadableSpan

from engine.trace.filtered_span_processor import FilteredSpanProcessor
from engine.trace.trace_manager import USER_AGENT_TRACE_TYPE
from settings import settings


def setup_performance_instrumentation(app: FastAPI):
    """Sets up OpenTelemetry traces export to Tempo for performance monitoring."""

    # Use existing global tracer provider
    tracer_provider = trace_api.get_tracer_provider()

    def ada_backend_filter(span: ReadableSpan) -> bool:
        """Filter to only export backend service spans (non-user-agent) to Tempo"""
        trace_type = span.attributes.get("trace.type") if span.attributes else None
        return trace_type != USER_AGENT_TRACE_TYPE

    otlp_exporter = OTLPSpanExporter(endpoint=settings.TEMPO_ENDPOINT)
    filtered_processor = FilteredSpanProcessor(
        exporter=otlp_exporter,
        filter_func=ada_backend_filter,
    )
    tracer_provider.add_span_processor(filtered_processor)

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=tracer_provider,
        excluded_urls="healthz,metrics",
    )
