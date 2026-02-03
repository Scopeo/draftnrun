import json
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import cast

from openinference.semconv.trace import SpanAttributes
from opentelemetry.sdk.trace import BoundedAttributes, Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace.status import StatusCode
from sqlalchemy import create_engine, func, select, update
from sqlalchemy.orm import sessionmaker

from ada_backend.database.models import Usage
from ada_backend.database.setup_db import get_db_url
from ada_backend.database.trace_models import Span, SpanMessage
from engine.trace.nested_utils import split_nested_keys

LOGGER = logging.getLogger(__name__)


def get_session_trace():
    """Get a database session for traces using the ada_backend database."""
    db_url = get_db_url()
    engine = create_engine(db_url, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


@contextmanager
def trace_session():
    """Context manager for trace DB session with automatic cleanup."""
    session = get_session_trace()
    try:
        yield session
    finally:
        session.close()


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


def parse_str_or_dict(input_str: str | list) -> str | dict | list:
    if isinstance(input_str, list):
        return input_str
    try:
        result = json.loads(input_str)
        if isinstance(result, dict) or isinstance(result, list):
            return result
        else:
            return input_str  # It's valid JSON, but not a dict
    except json.JSONDecodeError:
        # Not a JSON string, return as-is
        return input_str


def extract_messages_from_attributes(attributes: dict) -> tuple[list[dict], list[dict], dict]:
    try:
        input = []
        output = []
        if "llm" in attributes:
            if "input_messages" in attributes["llm"]:
                input_messages = attributes["llm"].pop("input_messages")
                input = parse_str_or_dict(input_messages)
                input = input if isinstance(input, list) else [input]
            if "output_messages" in attributes["llm"]:
                output_messages = attributes["llm"].pop("output_messages")
                output = parse_str_or_dict(output_messages)
                output = output if isinstance(output, list) else [output]

        if "input" in attributes:
            input_attributes = attributes.pop("input")
            if input is None or len(input) == 0:
                input = parse_str_or_dict(input_attributes.get("value", []))
                input = input if isinstance(input, list) else [input]
        if "output" in attributes:
            output_attributes = attributes.pop("output")
            if output is None or len(output) == 0:
                output = parse_str_or_dict(output_attributes.get("value", []))
                output = output if isinstance(output, list) else [output]
        return input, output, attributes
    except Exception as e:
        LOGGER.error(f"Error processing span attributes {attributes}: {e}")
        return [], [], attributes


class SQLSpanExporter(SpanExporter):
    def __init__(self):
        self.session = get_session_trace()

    def _extract_credits_from_attributes(self, attributes: dict) -> float:
        credits_dict = attributes.get("credits", {})

        credits_input = credits_dict.get("input_token", 0) or 0
        credits_output = credits_dict.get("output_token", 0) or 0
        credits_per_call = credits_dict.get("per_call", 0) or 0

        total_credits = credits_input + credits_output + credits_per_call
        return total_credits

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        LOGGER.info(f"Exporting {len(spans)} spans to SQL database")
        for span in spans:
            cumulative_error_count = int(span.status.status_code is StatusCode.ERROR)
            cumulative_llm_token_count_prompt = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, 0))
            cumulative_llm_token_count_completion = int(
                span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, 0)
            )

            json_span = json.loads(span.to_json())

            if accumulation := (
                self.session.execute(
                    select(
                        func.sum(Span.cumulative_error_count),
                        func.sum(Span.cumulative_llm_token_count_prompt),
                        func.sum(Span.cumulative_llm_token_count_completion),
                    ).where(Span.parent_id == json_span["context"]["span_id"])
                )
            ).first():
                cumulative_error_count += cast(int, accumulation[0] or 0)
                cumulative_llm_token_count_prompt += cast(int, accumulation[1] or 0)
                cumulative_llm_token_count_completion += cast(int, accumulation[2] or 0)

            formatted_attributes = (
                split_nested_keys(json_span["attributes"]) if isinstance(json_span["attributes"], dict) else {}
            )

            environment = formatted_attributes.pop("environment", None)
            call_type = formatted_attributes.pop("call_type", None)
            project_id = formatted_attributes.pop("project_id", None)
            graph_runner_id = formatted_attributes.pop("graph_runner_id", None)
            tag_name = formatted_attributes.pop("tag_name", None)
            component_instance_id = formatted_attributes.pop("component_instance_id", None)
            model_id = formatted_attributes.pop("model_id", None)
            input, output, formatted_attributes = extract_messages_from_attributes(formatted_attributes)

            openinference_span_kind = json_span["attributes"].get(SpanAttributes.OPENINFERENCE_SPAN_KIND, "UNKNOWN")
            span_row = Span(
                span_id=json_span["context"]["span_id"],
                trace_rowid=json_span["context"]["trace_id"],
                parent_id=json_span["parent_id"],
                span_kind=openinference_span_kind,
                name=span.name,
                start_time=datetime.fromtimestamp(span.start_time / 1e9, tz=timezone.utc),
                end_time=datetime.fromtimestamp(span.end_time / 1e9, tz=timezone.utc),
                attributes=formatted_attributes,
                events=json.dumps([event_to_dict(event) for event in span.events]),
                status_code=span.status.status_code,
                status_message=span.status.description or "",
                cumulative_error_count=cumulative_error_count,
                cumulative_llm_token_count_prompt=cumulative_llm_token_count_prompt,
                cumulative_llm_token_count_completion=cumulative_llm_token_count_completion,
                llm_token_count_prompt=span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT),
                llm_token_count_completion=span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION),
                environment=environment,
                call_type=call_type,
                project_id=project_id,
                graph_runner_id=graph_runner_id,
                tag_name=tag_name,
                component_instance_id=component_instance_id,
                model_id=model_id,
            )
            ancestors = select(Span.id, Span.parent_id).where(Span.span_id == span_row.parent_id).cte(recursive=True)
            child = ancestors.alias()
            ancestors = ancestors.union_all(
                select(Span.id, Span.parent_id).join(child, Span.span_id == child.c.parent_id)
            )
            self.session.execute(
                update(Span)
                .where(Span.id.in_(select(ancestors.c.id)))
                .values(
                    cumulative_error_count=Span.cumulative_error_count + cumulative_error_count,
                    cumulative_llm_token_count_prompt=Span.cumulative_llm_token_count_prompt
                    + cumulative_llm_token_count_prompt,
                    cumulative_llm_token_count_completion=Span.cumulative_llm_token_count_completion
                    + cumulative_llm_token_count_completion,
                )
            )
            self.session.add(span_row)

            if project_id and formatted_attributes:
                total_span_credits = self._extract_credits_from_attributes(formatted_attributes)

                if total_span_credits > 0:
                    current_date = datetime.now(tz=timezone.utc)
                    year = current_date.year
                    month = current_date.month

                    usage_record = self.session.execute(
                        select(Usage).where(Usage.project_id == project_id, Usage.year == year, Usage.month == month)
                    ).scalar_one_or_none()

                    if usage_record:
                        usage_record.credits_used += total_span_credits
                    else:
                        new_usage = Usage(
                            project_id=project_id,
                            year=year,
                            month=month,
                            credits_used=total_span_credits,
                        )
                        self.session.add(new_usage)

            self.session.add(
                SpanMessage(
                    span_id=span_row.span_id,
                    input_content=json.dumps(input) if input is not None else None,
                    output_content=json.dumps(output) if output is not None else None,
                )
            )
        self.session.commit()
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.session.close()
