from collections import defaultdict
import json
from typing import List
from uuid import UUID
import logging

import pandas as pd

from ada_backend.schemas.trace_schema import TraceSpan
from ada_backend.services.metrics.utils import query_trace_duration

LOGGER = logging.getLogger(__name__)


def build_span_trees(df: pd.DataFrame) -> List[TraceSpan]:
    """Convert a Pandas DataFrame containing multiple OpenTelemetry spans into a list of hierarchical JSON trees."""
    traces = defaultdict(dict)  # {trace_id: {span_id: span}}

    for _, row in df.iterrows():
        LOGGER.debug(f"Processing row: {row}")
        trace_id = row["trace_rowid"]
        span_id = row["span_id"]
        parent_id = row["parent_id"]
        span_kind = row["span_kind"]
        input = []
        output = []
        documents = []
        tool_info = {}
        model_name = ""
        try:
            if span_kind == "AGENT" or span_kind == "CHAIN" or span_kind == "TOOL":
                input = [row["attributes"]["input"].get("value", "")]
                if "output" in row["attributes"]:
                    output = [row["attributes"]["output"].get("value", "")]
            elif span_kind == "LLM":
                if "llm" in row["attributes"]:
                    model_name = row["attributes"]["llm"].get("model_name", "")
                    input = row["attributes"]["llm"]["input_messages"]
                    if "output_messages" in row["attributes"]["llm"]:
                        output = row["attributes"]["llm"]["output_messages"]
                    elif "output" in row["attributes"]:
                        if isinstance(row["attributes"]["output"]["value"], str):
                            row["attributes"]["output"]["value"] = json.loads(row["attributes"]["output"]["value"])
                        output = [row["attributes"]["output"]["value"]]
                else:
                    input = [row["attributes"]["input"].get("value", "")]
                    if "output" in row["attributes"]:
                        output = [row["attributes"]["output"].get("value", "")]
            elif span_kind == "RETRIEVER":
                events = json.loads(row["events"])
                if "input" in row["attributes"]:
                    input = [row["attributes"]["input"].get("value", "")]
                if "retrieval" in row["attributes"]:
                    documents = row["attributes"]["retrieval"]["documents"]
                elif len(events) > 0:
                    documents = [{"document": event["attributes"]} for event in events]
            elif span_kind == "EMBEDDING":
                if isinstance(row["attributes"]["input"]["value"], str):
                    row["attributes"]["input"]["value"] = json.loads(row["attributes"]["input"]["value"])
                input = row["attributes"]["input"]["value"]["input"]
                model_name = "embedding:" + row["attributes"]["embedding"]["model_name"]
            elif span_kind == "TOOL":
                input = [row["attributes"]["input"].get("value", "")]
                output = [row["attributes"]["output"].get("value", "")]
                tool_info = row["attributes"]["tool"]
        except Exception as e:
            LOGGER.error(f"Error processing row {row}: {e}")

        traces[trace_id][span_id] = TraceSpan(
            span_id=span_id,
            name=row["name"],
            span_kind=span_kind,
            start_time=row["start_time"],
            end_time=row["end_time"],
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


def get_trace_by_project(project_id: UUID, duration: int) -> List[TraceSpan]:
    df = query_trace_duration(project_id, duration)
    return build_span_trees(df)
