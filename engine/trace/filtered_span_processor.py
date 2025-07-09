"""Filtered Span Processor for selective span export based on span attributes."""

from typing import Callable, Optional
from opentelemetry.sdk.trace import ReadableSpan, Span, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, BatchSpanProcessor
from opentelemetry.context import Context


class FilteredSpanProcessor(SpanProcessor):
    """SpanProcessor that filters spans before passing them to an exporter."""

    def __init__(self, exporter: SpanExporter, filter_func: Callable[[ReadableSpan], bool]):
        self.exporter = exporter
        self.filter_func = filter_func
        self.processor = BatchSpanProcessor(exporter)

    def on_start(self, span: Span, parent_context: Optional[Context] = None) -> None:
        # Always start spans, filter on end when we have complete data
        self.processor.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        # Only process spans that pass the filter
        if self.filter_func(span):
            self.processor.on_end(span)

    def shutdown(self) -> None:
        self.processor.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.processor.force_flush(timeout_millis)
