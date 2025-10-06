from collections import defaultdict
import json
from typing import List, Optional
from uuid import UUID
import logging

import pandas as pd
import numpy as np

from ada_backend.schemas.trace_schema import RootTraceSpan, TraceSpan, TokenUsage
from ada_backend.services.metrics.utils import (
    query_root_trace_duration,
    query_trace_by_trace_id,
    query_trace_duration,
    query_trace_messages,
)
from engine.trace import models as db
from engine.trace.sql_exporter import get_session_trace, parse_str_or_dict
from ada_backend.segment_analytics import track_project_observability_loaded, track_span_observability_loaded
from ada_backend.database.models import EnvType, CallType


LOGGER = logging.getLogger(__name__)


TOKEN_LIMIT = 2000000


def get_attributes_with_messages(span_kind: str, row: pd.Series) -> dict:
    input = json.loads(row["input_content"]) if row["input_content"] else []
    output = json.loads(row["output_content"]) if row["output_content"] else []
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
        input, output, documents, tool_info, model_name = get_attributes_with_messages(span_kind, row)

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
            tag_version=row.get("tag_version", None),
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


def build_root_spans(df: pd.DataFrame) -> List[RootTraceSpan]:
    """Builds a list of root spans from the DataFrame."""
    root_spans = []
    for _, row in df.iterrows():
        LOGGER.debug(f"Processing row: {row}")
        span_kind = row["span_kind"]
        input, output, _, _, _ = get_attributes_with_messages(span_kind, row)
        root_spans.append(
            RootTraceSpan(
                trace_id=row["trace_rowid"],
                span_id=row["span_id"],
                name=row["name"],
                span_kind=span_kind,
                start_time=str(row["start_time"]) if row["start_time"] is not None else "",
                end_time=str(row["end_time"]) if row["end_time"] is not None else "",
                input=input,
                output=output,
                status_code=row["status_code"],
                cumulative_llm_token_count_prompt=row["cumulative_llm_token_count_prompt"],
                cumulative_llm_token_count_completion=row["cumulative_llm_token_count_completion"],
                llm_token_count_prompt=row.get("llm_token_count_prompt", None),
                llm_token_count_completion=row.get("llm_token_count_completion", None),
                environment=row.get("environment", None),
                call_type=row.get("call_type", None),
                tag_version=row.get("tag_version", None),
            )
        )

    return root_spans


def get_token_usage(organization_id: UUID) -> TokenUsage:
    session = get_session_trace()
    token_usage = session.query(db.OrganizationUsage).filter_by(organization_id=str(organization_id)).first()
    if not token_usage:
        return TokenUsage(organization_id=str(organization_id), total_tokens=0)
    return TokenUsage(organization_id=token_usage.organization_id, total_tokens=token_usage.total_tokens)


def get_span_trace_service(user_id: UUID, trace_id: UUID) -> TraceSpan:
    df_span = query_trace_by_trace_id(trace_id)
    track_span_observability_loaded(user_id, trace_id)

    span_trees = build_span_trees(df_span)
    if len(span_trees) == 0:
        raise ValueError(f"No spans found for trace_id {trace_id}")

    return span_trees[0]


def get_root_traces_by_project(
    user_id: UUID,
    project_id: UUID,
    duration: int,
    environment: Optional[EnvType] = None,
    call_type: Optional[CallType] = None,
    tag_version: Optional[str] = None,
) -> List[RootTraceSpan]:
    df_span = query_root_trace_duration(project_id, duration)
    track_project_observability_loaded(user_id, project_id)
    LOGGER.info(f"Querying root spans for project {project_id} with duration {duration} days")

    if environment is not None:
        df_span = df_span[df_span["environment"] == environment.value]

    if call_type is not None:
        df_span = df_span[df_span["call_type"] == call_type.value]

    if tag_version is not None:
        df_span = df_span[df_span["tag_version"] == tag_version]

    return build_root_spans(df_span)
