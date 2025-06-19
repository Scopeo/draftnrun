from datetime import datetime, timedelta
import sqlite3
import logging
from uuid import UUID
import json

import pandas as pd

from ada_backend.schemas.monitor_schema import KPI, KPISResponse, TraceKPIS
from ada_backend.services.metrics.utils import get_trace_db_path


LOGGER = logging.getLogger(__name__)


def get_trace_metrics(project_id: UUID, duration_days: int) -> TraceKPIS:
    start_time_offset_days = (datetime.now() - timedelta(days=2 * duration_days)).isoformat()
    query = (
        "SELECT trace_rowid, start_time, end_time, attributes, cumulative_llm_token_count_completion, "
        "cumulative_llm_token_count_prompt FROM spans "
        f"WHERE start_time >= '{start_time_offset_days}' AND parent_id IS NULL"
    )
    db_path = get_trace_db_path()
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(query, conn)
    conn.close()
    df["attributes"] = df["attributes"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df_expanded = df.join(pd.json_normalize(df["attributes"]))
    df = df_expanded[df_expanded["project_id"] == str(project_id)].copy()
    df["end_time"] = pd.to_datetime(df["end_time"])
    df["start_time"] = pd.to_datetime(df["start_time"])

    df_previous = df[df["start_time"] < (datetime.now() - timedelta(days=duration_days)).isoformat()].copy()
    df_current = df[df["start_time"] >= (datetime.now() - timedelta(days=duration_days)).isoformat()].copy()

    tokens_previous_sum = (
        df_previous["cumulative_llm_token_count_prompt"].sum()
        + df_previous["cumulative_llm_token_count_completion"].sum()
    )
    tokens_current_sum = (
        df_current["cumulative_llm_token_count_prompt"].sum()
        + df_current["cumulative_llm_token_count_completion"].sum()
    )
    comparison_percentage = (
        round((tokens_current_sum - tokens_previous_sum) / tokens_previous_sum * 100, 1)
        if tokens_previous_sum != 0
        else None
    )

    df_previous["latency"] = df_previous["end_time"] - df_previous["start_time"]
    average_latency_previous = df_previous["latency"].mean().total_seconds() if not df_previous.empty else None
    df_current["latency"] = df_current["end_time"] - df_current["start_time"]
    average_latency_current = df_current["latency"].mean().total_seconds() if not df_current.empty else None
    latency_comparison_percentage = (
        round((average_latency_current - average_latency_previous) / average_latency_previous * 100, 1)
        if all(v is not None for v in [average_latency_current, average_latency_previous])
        and average_latency_previous != 0
        else None
    )

    nb_request_previous = len(df_previous)
    nb_request_previous = len(df_current)
    nb_request_comparison_percentage = (
        round((nb_request_previous - nb_request_previous) / nb_request_previous * 100, 1)
        if nb_request_previous != 0
        else None
    )

    return TraceKPIS(
        tokens_count=tokens_current_sum,
        token_comparison_percentage=comparison_percentage,
        average_latency=round(average_latency_current, 2) if average_latency_current is not None else None,
        latency_comparison_percentage=latency_comparison_percentage,
        nb_request=nb_request_previous,
        nb_request_comparison_percentage=nb_request_comparison_percentage,
    )


def get_monitoring_kpis_by_project(project_id: UUID, duration_days: int) -> KPISResponse:
    trace_kpis = get_trace_metrics(project_id, duration_days)
    LOGGER.info(f"Trace metrics for project {project_id} and duration {duration_days} days retrieved successfully.")
    return KPISResponse(
        kpis=[
            KPI(
                title="Total Tokens Usage",
                color="primary",
                icon="tabler-coin",
                stats=str(trace_kpis.tokens_count) if trace_kpis.tokens_count is not None else "N/A",
                change=(
                    str(trace_kpis.token_comparison_percentage) + "%"
                    if trace_kpis.token_comparison_percentage is not None
                    else "N/A"
                ),
            ),
            KPI(
                title="Total API Requests",
                color="success",
                icon="tabler-api",
                stats=str(trace_kpis.nb_request),
                change=(
                    str(trace_kpis.nb_request_comparison_percentage) + "%"
                    if trace_kpis.nb_request_comparison_percentage is not None
                    else "N/A"
                ),
            ),
            KPI(
                title="Average Latency",
                color="warning",
                icon="tabler-clock",
                stats=str(trace_kpis.average_latency) + "s" if trace_kpis.average_latency is not None else "N/A",
                change=(
                    str(trace_kpis.latency_comparison_percentage) + "%"
                    if trace_kpis.latency_comparison_percentage is not None
                    else "N/A"
                ),
            ),
        ]
    )
