import ast
from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Any, cast
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


def get_session_trace():
    engine = create_engine(models.TRACES_DB_URL, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    return session


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


def convert_to_list(obj: Any) -> list[str] | None:
    if isinstance(obj, list):
        return obj
    if obj is None:
        return None
    if isinstance(obj, str):
        try:
            result = ast.literal_eval(obj)
            if isinstance(result, list):
                return result
        except (ValueError, SyntaxError):
            pass
    return None


class SQLSpanExporter(SpanExporter):
    def __init__(self):
        self.session = get_session_trace()

    def get_org_info_from_ancestors(self, parent_id: str) -> tuple[str, str] | None:
        """Get org_id and org_llm_providers from ancestors of the span."""
        while parent_id:
            row = self.session.execute(
                select(models.Span.attributes, models.Span.parent_id).where(models.Span.span_id == parent_id)
            ).first()
            if not row:
                break
            attributes, parent_id = row
            if attributes:
                try:
                    attrs = json.loads(attributes)
                except Exception:
                    continue
                org_id = attrs.get("organization_id")
                org_llm_providers = convert_to_list(attrs.get("organization_llm_providers"))
                if org_id:
                    return org_id, org_llm_providers
        return None, None

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

        org_token_counts = defaultdict(int)
        for span in spans:
            total_tokens = 0
            json_span = json.loads(span.to_json())
            org_id = span.attributes.get("organization_id")
            org_llm_providers = convert_to_list(span.attributes.get("organization_llm_providers"))

            if not org_id:
                org_id, org_llm_providers = self.get_org_info_from_ancestors(json_span["parent_id"])
            token_prompt = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT, 0) or 0)
            token_completion = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION, 0) or 0)
            total_tokens = token_prompt + token_completion

            provider = span.attributes.get(SpanAttributes.LLM_PROVIDER)

            if total_tokens > 0 and org_id and (provider is None or provider not in org_llm_providers):
                org_token_counts[org_id] += total_tokens

        for org_id, tokens in org_token_counts.items():
            result = self.session.execute(
                select(models.OrganizationUsage).where(models.OrganizationUsage.organization_id == org_id)
            ).first()

            if result:
                self.session.execute(
                    update(models.OrganizationUsage)
                    .where(models.OrganizationUsage.organization_id == org_id)
                    .values(total_tokens=models.OrganizationUsage.total_tokens + tokens)
                )
            else:
                self.session.add(models.OrganizationUsage(organization_id=org_id, total_tokens=tokens))
        self.session.commit()
        return SpanExportResult.SUCCESS

    def shutdown(self):
        self.session.close()
