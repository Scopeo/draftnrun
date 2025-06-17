from datetime import datetime, timezone
import logging
from typing import cast
import json

from opentelemetry.sdk.trace import ReadableSpan, Event, BoundedAttributes
from openinference.semconv.trace import SpanAttributes
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace.status import StatusCode
from sqlalchemy import func, select, create_engine, update
from sqlalchemy.orm import sessionmaker

from engine.trace.nested_utils import split_nested_keys
from engine.trace import models


LOGGER = logging.getLogger(__name__)


def event_to_dict(event: Event) -> dict:
    event_dict = {
        "name": event.name,
        "timestamp": event.timestamp,
        "attributes": event.attributes,
    }
    if isinstance(event.attributes, BoundedAttributes):
        # Convert the internal _dict of BoundedAttributes to a regular dictionary
        event_dict["attributes"] = {key: value for key, value in event.attributes._dict.items()}
    return event_dict


class SQLSpanExporter(SpanExporter):
    def __init__(self, db_engine: str = models.TRACES_DB_URL):
        self.engine = create_engine(db_engine, echo=False)
        Session = sessionmaker(bind=self.engine)
        self.session = Session()

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        LOGGER.info(f"Exporting {len(spans)} spans to SQL database")
        for span in spans:
            cumulative_error_count = int(span.status.status_code is StatusCode.ERROR)
            try:
                cumulative_llm_token_count_prompt = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT), 0)
            except BaseException:
                cumulative_llm_token_count_prompt = 0
            try:
                cumulative_llm_token_count_completion = int(
                    span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, 0)
                )
            except BaseException:
                cumulative_llm_token_count_completion = 0

            json_span = json.loads(span.to_json())

            if accumulation := (
                self.session.execute(
                    select(
                        func.sum(models.Span.cumulative_error_count),
                        func.sum(models.Span.cumulative_llm_token_count_prompt),
                        func.sum(models.Span.cumulative_llm_token_count_completion),
                    ).where(models.Span.parent_id == json_span["context"]["span_id"])
                )
            ).first():
                cumulative_error_count += cast(int, accumulation[0] or 0)
                cumulative_llm_token_count_prompt += cast(int, accumulation[1] or 0)
                cumulative_llm_token_count_completion += cast(int, accumulation[2] or 0)

            formatted_attributes = (
                split_nested_keys(json_span["attributes"]) if isinstance(json_span["attributes"], dict) else {}
            )

            openinference_span_kind = json_span["attributes"].get(SpanAttributes.OPENINFERENCE_SPAN_KIND, "UNKNOWN")

            span_row = models.Span(
                span_id=json_span["context"]["span_id"],
                trace_rowid=json_span["context"]["trace_id"],
                parent_id=json_span["parent_id"],
                span_kind=openinference_span_kind,
                name=span.name,
                start_time=datetime.fromtimestamp(span.start_time / 1e9, tz=timezone.utc),
                end_time=datetime.fromtimestamp(span.end_time / 1e9, tz=timezone.utc),
                attributes=json.dumps(formatted_attributes),
                events=json.dumps([event_to_dict(event) for event in span.events]),
                status_code=span.status.status_code,
                status_message=span.status.description or "",
                cumulative_error_count=cumulative_error_count,
                cumulative_llm_token_count_prompt=cumulative_llm_token_count_prompt,
                cumulative_llm_token_count_completion=cumulative_llm_token_count_completion,
                llm_token_count_prompt=span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT),
                llm_token_count_completion=span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION),
            )
            ancestors = (
                select(models.Span.id, models.Span.parent_id)
                .where(models.Span.span_id == span_row.parent_id)
                .cte(recursive=True)
            )
            child = ancestors.alias()
            ancestors = ancestors.union_all(
                select(models.Span.id, models.Span.parent_id).join(child, models.Span.span_id == child.c.parent_id)
            )
            self.session.execute(
                update(models.Span)
                .where(models.Span.id.in_(select(ancestors.c.id)))
                .values(
                    cumulative_error_count=models.Span.cumulative_error_count + cumulative_error_count,
                    cumulative_llm_token_count_prompt=models.Span.cumulative_llm_token_count_prompt
                    + cumulative_llm_token_count_prompt,
                    cumulative_llm_token_count_completion=models.Span.cumulative_llm_token_count_completion
                    + cumulative_llm_token_count_completion,
                )
            )

            self.session.add(span_row)
            self.session.commit()
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.session.close()
