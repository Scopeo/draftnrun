import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import List, Optional
from uuid import UUID

import pandas as pd

from ada_backend.database.models import CallType, EnvType
from ada_backend.mixpanel_analytics import track_monitoring_loaded, track_trace_viewed
from ada_backend.schemas.trace_schema import (
    PaginatedRootTracesResponse,
    Pagination,
    RootTraceSpan,
    TraceSpan,
)
from ada_backend.services.metrics.utils import (
    query_root_trace_duration,
    query_trace_by_trace_id,
)

LOGGER = logging.getLogger(__name__)


def _safe_json_loads(raw: str | None) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        LOGGER.warning("Skipping unparseable span content (len=%d)", len(raw))
        return []


def get_attributes_with_messages(span_kind: str, row: pd.Series, filter_to_last_message: bool = False) -> dict:
    input_data = _safe_json_loads(row["input_content"])
    input = []
    try:
        if filter_to_last_message and input_data and isinstance(input_data[0], dict) and "messages" in input_data[0]:
            messages = input_data[0].get("messages", [])
            user_msgs = [msg for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"]
            if user_msgs:
                input.append({**input_data[0], "messages": [user_msgs[-1]]})
        if not input:
            input = input_data
    except Exception as e:
        LOGGER.error(f"Error extracting last user message: {e}, input_data: {input_data}")
        input = input_data
    output = _safe_json_loads(row["output_content"])
    documents = []
    tool_info = {}
    model_name = ""
    try:
        if "llm" in row["attributes"]:
            model_name = row["attributes"]["llm"].get("model_name", "")
        if span_kind == "RETRIEVER":
            events = json.loads(row["events"])
            if "retrieval" in row["attributes"]:
                documents = row["attributes"]["retrieval"]["documents"]
            elif len(events) > 0:
                documents = [{"document": event["attributes"]} for event in events]
        elif span_kind == "RERANKER":
            events = json.loads(row["events"])
            if "reranker" in row["attributes"]:
                if "input_documents" in row["attributes"]["reranker"]:
                    documents = row["attributes"]["reranker"]["input_documents"]
                elif "output_documents" in row["attributes"]["reranker"]:
                    documents = row["attributes"]["reranker"]["output_documents"]
            elif len(events) > 0:
                documents = [{"document": event["attributes"]} for event in events]
        elif span_kind == "EMBEDDING":
            model_name = "embedding:" + row["attributes"]["embedding"]["model_name"]
        elif span_kind == "TOOL":
            if "tool" in row["attributes"]:
                tool_info = row["attributes"]["tool"]
    except Exception as e:
        LOGGER.error(f"Error processing row {row}: {e}")
    return input, output, documents, tool_info, model_name


# TODO: refacto this function to only handle one trace id
def build_span_trees(df: pd.DataFrame) -> List[TraceSpan]:
    """Convert a Pandas DataFrame containing multiple OpenTelemetry spans into a list of hierarchical JSON trees."""
    traces = defaultdict(dict)  # {trace_id: {span_id: span}}

    for _, row in df.iterrows():
        LOGGER.debug(f"Processing row: {row}")
        trace_id = row["trace_rowid"]
        span_id = row["span_id"]
        parent_id = row["parent_id"]
        span_kind = row["span_kind"]
        input, output, documents, tool_info, model_name = get_attributes_with_messages(
            span_kind, row, filter_to_last_message=False
        )
        attributes = row.get("attributes", {})

        original_retrieval_rank = None
        original_reranker_rank = None
        try:
            if "original_retrieval_rank" in attributes:
                original_retrieval_rank = json.loads(attributes["original_retrieval_rank"])
            if "original_reranker_rank" in attributes:
                original_reranker_rank = json.loads(attributes["original_reranker_rank"])
        except Exception as e:
            LOGGER.error(f"Error parsing original ranks: {e}")

        traces[trace_id][span_id] = TraceSpan(
            span_id=span_id,
            name=row["name"],
            span_kind=span_kind,
            start_time=str(row["start_time"]) if row["start_time"] is not None else "",
            end_time=str(row["end_time"]) if row["end_time"] is not None else "",
            input=input,
            output=output,
            documents=documents,
            model_name=model_name,
            tool_info=tool_info,
            status_code=row["status_code"],
            cumulative_llm_token_count_prompt=row["cumulative_llm_token_count_prompt"],
            cumulative_llm_token_count_completion=row["cumulative_llm_token_count_completion"],
            llm_token_count_prompt=row.get("llm_token_count_prompt", None),
            llm_token_count_completion=row.get("llm_token_count_completion", None),
            children=[],
            environment=row.get("environment", None),
            call_type=row.get("call_type", None),
            graph_runner_id=row.get("graph_runner_id", None),
            tag_name=row.get("tag_name", None),
            conversation_id=attributes.get("conversation_id"),
            trace_id=row.get("trace_rowid"),
            total_credits=row.get("total_credits", None),
            original_retrieval_rank=original_retrieval_rank,
            original_reranker_rank=original_reranker_rank,
        )

    trace_trees = []
    for trace_id, span_dict in traces.items():
        root_spans = []

        for span_id, span in span_dict.items():
            parent_id = df[df["span_id"] == span_id]["parent_id"].values[0]
            if pd.notna(parent_id):
                span_dict[parent_id].children.append(span)
            else:  # Root span
                root_spans.append(span)

        trace_trees.extend(root_spans)

    return trace_trees


def build_root_spans(rows: List[dict]) -> List[RootTraceSpan]:
    """Builds a list of root spans from query result rows.

    Expects input_preview and output_preview as pre-extracted plain text
    columns from the SQL query (truncated at 500 chars).
    """
    return [
        RootTraceSpan(
            trace_id=row["trace_rowid"],
            span_id=row["span_id"],
            name=row["name"],
            span_kind=row["span_kind"],
            start_time=str(row["start_time"]) if row["start_time"] is not None else "",
            end_time=str(row["end_time"]) if row["end_time"] is not None else "",
            input_preview=row.get("input_preview") or "",
            output_preview=row.get("output_preview") or "",
            status_code=row["status_code"],
            environment=row.get("environment"),
            call_type=row.get("call_type"),
            graph_runner_id=row.get("graph_runner_id"),
            tag_name=row.get("tag_name"),
            conversation_id=row.get("conversation_id"),
            total_credits=row.get("total_credits"),
        )
        for row in rows
    ]


def get_span_trace_service(user_id: UUID, trace_id: UUID) -> TraceSpan:
    df_span = query_trace_by_trace_id(trace_id)
    span_trees = build_span_trees(df_span)
    if len(span_trees) == 0:
        raise ValueError(f"No spans found for trace_id {trace_id}")

    track_trace_viewed(user_id, trace_id)
    return span_trees[0]


def get_root_traces_by_project(
    user_id: UUID,
    project_id: UUID,
    duration: Optional[int] = None,
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    page: int = 1,
    page_size: int = 20,
    graph_runner_id: Optional[UUID] = None,
    organization_id: Optional[UUID] = None,
    search: Optional[str] = None,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> PaginatedRootTracesResponse:
    if page_size <= 0:
        page_size = 20
    if page <= 0:
        page = 1

    rows, total_pages = query_root_trace_duration(
        project_id,
        duration_days=duration,
        environment=environment,
        call_type=call_type,
        graph_runner_id=graph_runner_id,
        page=page,
        page_size=page_size,
        search=search,
        start_time=start_time,
        end_time=end_time,
    )
    track_monitoring_loaded(user_id, project_count=1, organization_id=organization_id)
    LOGGER.info("Querying root spans for project %s with duration=%s start_time=%s end_time=%s",
                project_id, duration, start_time, end_time)

    traces = build_root_spans(rows)
    return PaginatedRootTracesResponse(
        pagination=Pagination(page=page, size=page_size, total_pages=total_pages),
        traces=traces,
    )
