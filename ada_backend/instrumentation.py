from fastapi import FastAPI
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_performance_instrumentation(app: FastAPI):
    """
    Sets up OpenTelemetry for performance monitoring, including metrics and traces.
    This is kept separate from the feature-level tracing.
    """
    resource = Resource(attributes={"service.name": "ada-backend"})

    # The PrometheusExporter makes a /metrics endpoint available on the FastAPI app.
    prometheus_exporter = PrometheusExporter()
    metric_reader = PeriodicExportingMetricReader(exporter=prometheus_exporter)
    perf_meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])

    perf_trace_provider = TracerProvider(resource=resource)
    otlp_exporter = OTLPSpanExporter(endpoint="http://localhost:4318/v1/traces")
    perf_trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=perf_trace_provider,
        meter_provider=perf_meter_provider,
    )
