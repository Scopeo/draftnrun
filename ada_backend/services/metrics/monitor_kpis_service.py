import logging
from datetime import datetime, timedelta
from uuid import UUID

import pandas as pd

from ada_backend.database.models import CallType
from ada_backend.schemas.monitor_schema import KPI, KPISResponse, TraceKPIS
from ada_backend.segment_analytics import track_project_monitoring_loaded
from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)


def get_trace_metrics(project_id: UUID, duration_days: int, call_type: CallType | None = None) -> TraceKPIS:
    """Get trace metrics with comparison between current and previous periods using SQL aggregation."""
    now = datetime.now()
    current_start = now - timedelta(days=duration_days)
    previous_start = now - timedelta(days=2 * duration_days)

    # Build the call_type filter clause
    call_type_filter = ""
    if call_type is not None:
        call_type_filter = "AND call_type = %(call_type)s"

    query = f"""
    SELECT
        CASE
            WHEN start_time >= %(current_start)s THEN 'current'
            ELSE 'previous'
        END as period,
        COUNT(*) as request_count,
        COALESCE(SUM(cumulative_llm_token_count_prompt + cumulative_llm_token_count_completion), 0) as total_tokens,
        AVG(EXTRACT(EPOCH FROM (end_time - start_time))) as avg_latency_seconds
    FROM traces.spans
    WHERE start_time >= %(previous_start)s
    AND parent_id IS NULL
    AND project_id = %(project_id)s
    {call_type_filter}
    GROUP BY period
    """

    session = get_session_trace()
    try:
        params = {
            "current_start": current_start,
            "previous_start": previous_start,
            "project_id": str(project_id),
        }
        if call_type is not None:
            params["call_type"] = call_type.value

        df = pd.read_sql_query(
            query,
            session.bind,
            params=params,
        )
    finally:
        session.close()

    # Initialize default values
    current_metrics = {"request_count": 0, "total_tokens": 0, "avg_latency_seconds": None}
    previous_metrics = {"request_count": 0, "total_tokens": 0, "avg_latency_seconds": None}

    # Extract metrics for each period
    for _, row in df.iterrows():
        metrics = {
            "request_count": int(row["request_count"]),
            "total_tokens": int(row["total_tokens"] or 0),
            "avg_latency_seconds": float(row["avg_latency_seconds"]) if row["avg_latency_seconds"] else None,
        }

        if row["period"] == "current":
            current_metrics = metrics
        else:
            previous_metrics = metrics

    # Helper function to calculate percentage changes
    def calculate_percentage_change(current: float, previous: float) -> float | None:
        if previous == 0:
            return None
        return round((current - previous) / previous * 100, 1)

    # Calculate comparisons
    token_comparison = calculate_percentage_change(current_metrics["total_tokens"], previous_metrics["total_tokens"])

    latency_comparison = None
    if current_metrics["avg_latency_seconds"] and previous_metrics["avg_latency_seconds"]:
        latency_comparison = calculate_percentage_change(
            current_metrics["avg_latency_seconds"], previous_metrics["avg_latency_seconds"]
        )

    request_comparison = calculate_percentage_change(
        current_metrics["request_count"], previous_metrics["request_count"]
    )

    return TraceKPIS(
        tokens_count=current_metrics["total_tokens"],
        token_comparison_percentage=token_comparison,
        average_latency=(
            round(current_metrics["avg_latency_seconds"], 2) if current_metrics["avg_latency_seconds"] else None
        ),
        latency_comparison_percentage=latency_comparison,
        nb_request=current_metrics["request_count"],
        nb_request_comparison_percentage=request_comparison,
    )


def get_monitoring_kpis_by_project(
    user_id: UUID,
    project_id: UUID,
    duration_days: int,
    call_type: CallType | None = None,
) -> KPISResponse:
    trace_kpis = get_trace_metrics(project_id, duration_days, call_type)
    LOGGER.info(f"Trace metrics for project {project_id} and duration {duration_days} days retrieved successfully.")
    track_project_monitoring_loaded(user_id, project_id)
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
