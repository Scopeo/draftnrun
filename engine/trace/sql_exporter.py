import ast
from collections import defaultdict
from datetime import datetime, timezone
import logging
from typing import Any, cast
import json
import traceback

from opentelemetry.sdk.trace import ReadableSpan, Event, BoundedAttributes
from openinference.semconv.trace import SpanAttributes
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace.status import StatusCode
from sqlalchemy import func, select, create_engine, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError

from engine.trace.nested_utils import split_nested_keys
from engine.trace import models
from settings import settings

LOGGER = logging.getLogger(__name__)


def get_session_trace():
    if not settings.TRACES_DB_URL:
        raise ValueError("TRACES_DB_URL is not set")
    engine = create_engine(settings.TRACES_DB_URL, echo=False)
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

    def _log_span_details(self, span: ReadableSpan, operation: str):
        """Log detailed information about a span for debugging."""
        try:
            span_id = span.context.span_id
            trace_id = span.context.trace_id
            name = span.name
            status = span.status.status_code
            LOGGER.debug(f"Span {operation}: id={span_id}, trace={trace_id}, name='{name}', status={status}")
        except Exception as e:
            LOGGER.debug(f"Could not log span details: {e}")

    def _handle_span_processing_error(self, span: ReadableSpan, error: Exception, operation: str):
        """Handle and log errors during span processing."""
        try:
            span_id = span.context.span_id if hasattr(span, "context") else "unknown"
            trace_id = span.context.trace_id if hasattr(span, "context") else "unknown"
        except (AttributeError, TypeError):
            span_id = "unknown"
            trace_id = "unknown"

        error_msg = f"Error processing span {span_id} (trace: {trace_id}) during {operation}: {str(error)}"
        LOGGER.error(error_msg)

        if isinstance(error, IntegrityError):
            LOGGER.error(f"Integrity error details: {error.orig}")
        elif isinstance(error, OperationalError):
            LOGGER.error(f"Operational error details: {error.orig}")

    def export(self, spans: list[ReadableSpan]) -> SpanExportResult:
        if not spans:
            LOGGER.debug("No spans to export")
            return SpanExportResult.SUCCESS

        LOGGER.info(f"Exporting {len(spans)} spans to SQL database")

        try:
            # Process spans
            for i, span in enumerate(spans):
                try:
                    self._log_span_details(span, f"processing ({i+1}/{len(spans)})")

                    cumulative_error_count = int(span.status.status_code is StatusCode.ERROR)
                    try:
                        cumulative_llm_token_count_prompt = int(
                            span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT)
                        )
                    except (ValueError, TypeError):
                        cumulative_llm_token_count_prompt = 0
                    try:
                        cumulative_llm_token_count_completion = int(
                            span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION)
                        )
                    except (ValueError, TypeError):
                        cumulative_llm_token_count_completion = 0

                    json_span = json.loads(span.to_json())

                    # Get cumulative counts from children
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

                    openinference_span_kind = json_span["attributes"].get(
                        SpanAttributes.OPENINFERENCE_SPAN_KIND, "UNKNOWN"
                    )

                    # Handle None timestamps with defaults
                    start_time_ns = span.start_time if span.start_time is not None else 0
                    end_time_ns = span.end_time if span.end_time is not None else 0
                    used_fallback_start = False
                    used_fallback_end = False
                    # Convert nanoseconds to datetime, with fallback for zero values
                    if start_time_ns > 0:
                        start_time = datetime.fromtimestamp(start_time_ns / 1e9, tz=timezone.utc)
                    else:
                        start_time = datetime.now(timezone.utc)
                        used_fallback_start = True
                    if end_time_ns > 0:
                        end_time = datetime.fromtimestamp(end_time_ns / 1e9, tz=timezone.utc)
                    else:
                        end_time = datetime.now(timezone.utc)
                        used_fallback_end = True
                    if used_fallback_start or used_fallback_end:
                        LOGGER.warning(
                            f"Span {json_span['context'].get('span_id', 'unknown')} is missing "
                            f"{'start_time' if used_fallback_start else ''}"
                            f"{' and ' if used_fallback_start and used_fallback_end else ''}"
                            f"{'end_time' if used_fallback_end else ''}; "
                            f"using fallback timestamp(s)."
                        )

                    span_row = models.Span(
                        span_id=json_span["context"]["span_id"],
                        trace_rowid=json_span["context"]["trace_id"],
                        parent_id=json_span["parent_id"],
                        span_kind=openinference_span_kind,
                        name=span.name,
                        start_time=start_time,
                        end_time=end_time,
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

                    # Update ancestors
                    if span_row.parent_id:
                        try:
                            ancestors = (
                                select(models.Span.id, models.Span.parent_id)
                                .where(models.Span.span_id == span_row.parent_id)
                                .cte(recursive=True)
                            )
                            child = ancestors.alias()
                            ancestors = ancestors.union_all(
                                select(models.Span.id, models.Span.parent_id).join(
                                    child, models.Span.span_id == child.c.parent_id
                                )
                            )
                            self.session.execute(
                                update(models.Span)
                                .where(models.Span.id.in_(select(ancestors.c.id)))
                                .values(
                                    cumulative_error_count=models.Span.cumulative_error_count + cumulative_error_count,
                                    cumulative_llm_token_count_prompt=models.Span.cumulative_llm_token_count_prompt
                                    + cumulative_llm_token_count_prompt,
                                    cumulative_llm_token_count_completion=(
                                        models.Span.cumulative_llm_token_count_completion
                                        + cumulative_llm_token_count_completion
                                    ),
                                )
                            )
                        except SQLAlchemyError as e:
                            LOGGER.warning(f"Failed to update ancestors for span {span_row.span_id}: {e}")

                    self.session.add(span_row)

                except Exception as e:
                    self._handle_span_processing_error(span, e, "span creation")
                    # Continue with next span instead of failing entire batch
                    continue

            # Commit all span operations
            LOGGER.debug("Committing span operations to database")
            self.session.commit()
            LOGGER.info(f"Successfully committed {len(spans)} spans to database")

            # Process organization usage
            org_token_counts = defaultdict(int)
            for span in spans:
                try:
                    total_tokens = 0
                    json_span = json.loads(span.to_json())
                    org_id = span.attributes.get("organization_id")
                    org_llm_providers = convert_to_list(span.attributes.get("organization_llm_providers"))

                    if not org_id:
                        org_id, org_llm_providers = self.get_org_info_from_ancestors(json_span["parent_id"])
                    token_prompt = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_PROMPT) or 0)
                    token_completion = int(span.attributes.get(SpanAttributes.LLM_TOKEN_COUNT_COMPLETION) or 0)
                    total_tokens = token_prompt + token_completion

                    provider = span.attributes.get(SpanAttributes.LLM_PROVIDER)

                    if total_tokens > 0 and org_id and (provider is None or provider not in org_llm_providers):
                        org_token_counts[org_id] += total_tokens

                except Exception as e:
                    self._handle_span_processing_error(span, e, "organization usage calculation")
                    continue

            # Update organization usage
            if org_token_counts:
                LOGGER.debug(f"Updating organization usage for {len(org_token_counts)} organizations")
                for org_id, tokens in org_token_counts.items():
                    try:
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
                    except SQLAlchemyError as e:
                        LOGGER.error(f"Failed to update organization usage for org {org_id}: {e}")
                        continue

                # Commit organization usage updates
                self.session.commit()
                LOGGER.info(f"Successfully updated organization usage for {len(org_token_counts)} organizations")

            return SpanExportResult.SUCCESS

        except SQLAlchemyError as e:
            LOGGER.error(f"Database error during span export: {e}")
            LOGGER.error(f"Error type: {type(e).__name__}")
            LOGGER.error(f"Error details: {str(e)}")
            if hasattr(e, "orig"):
                LOGGER.error(f"Original error: {e.orig}")
            LOGGER.error(f"Traceback: {traceback.format_exc()}")

            try:
                self.session.rollback()
                LOGGER.info("Successfully rolled back database transaction")
            except Exception as rollback_error:
                LOGGER.error(f"Failed to rollback transaction: {rollback_error}")

            return SpanExportResult.FAILURE

        except Exception as e:
            LOGGER.error(f"Unexpected error during span export: {e}")
            LOGGER.error(f"Error type: {type(e).__name__}")
            LOGGER.error(f"Traceback: {traceback.format_exc()}")

            try:
                self.session.rollback()
                LOGGER.info("Successfully rolled back database transaction")
            except Exception as rollback_error:
                LOGGER.error(f"Failed to rollback transaction: {rollback_error}")

            return SpanExportResult.FAILURE

    def shutdown(self):
        """Clean up resources."""
        try:
            self.session.close()
            LOGGER.info("SQLSpanExporter session closed")
        except Exception as e:
            LOGGER.error(f"Error during shutdown: {e}")
