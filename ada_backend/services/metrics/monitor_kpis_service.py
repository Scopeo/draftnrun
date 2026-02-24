import logging
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import UUID

import pandas as pd

from ada_backend.database.models import CallType
from ada_backend.schemas.monitor_schema import KPI, CostKPI, KPISResponse, TraceKPIS
from ada_backend.segment_analytics import track_projects_monitoring_loaded
from ada_backend.services.metrics.utils import QUERY_COSTS_BASIS, SQL_COST_KPIS_ROUNDED_TAIL
from engine.trace.sql_exporter import get_session_trace

LOGGER = logging.getLogger(__name__)

SIGNIFICANT_FIGURES_CREDIT_FORMAT = 2


def _run_trace_kpis_query(
    query: str,
    project_ids: List[UUID],
    call_type: CallType | None,
    **params: object,
) -> pd.DataFrame:
    call_type_filter = "AND call_type = %(call_type)s" if call_type is not None else ""
    project_id_placeholders = ", ".join([f"%(project_id_{i})s" for i in range(len(project_ids))])
    query = query.format(call_type_filter=call_type_filter, project_id_placeholders=project_id_placeholders)
    full_params = {f"project_id_{i}": str(project_id) for i, project_id in enumerate(project_ids)}
    if call_type is not None:
        full_params["call_type"] = call_type.value
    full_params.update(params)
    session = get_session_trace()
    try:
        return pd.read_sql_query(query, session.bind, params=full_params)
    finally:
        session.close()


def get_trace_metrics(project_ids: List[UUID], duration_days: int, call_type: CallType | None = None) -> TraceKPIS:
    """Get trace metrics with comparison between current and previous periods using SQL aggregation."""
    now = datetime.now()
    current_start = now - timedelta(days=duration_days)
    previous_start = now - timedelta(days=2 * duration_days)

    query = """
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
    AND project_id IN ({project_id_placeholders})
    {call_type_filter}
    GROUP BY period
    """
    df = _run_trace_kpis_query(
        query, project_ids, call_type, current_start=current_start, previous_start=previous_start
    )

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


def get_trace_cost_kpis(project_ids: List[UUID], duration_days: int, call_type: CallType | None = None) -> CostKPI:
    """Get mean cost per run and per conversation over a given period."""
    now = datetime.now()
    start_time = now - timedelta(days=duration_days)
    end_time = now

    query = (
        QUERY_COSTS_BASIS
        + """
         WHERE project_id IN ({project_id_placeholders})
                AND s.start_time >= %(start_time)s
                AND s.start_time < %(end_time)s
                {call_type_filter}
            GROUP BY
                s.trace_rowid,
                s.attributes->>'conversation_id'
        ),
        conversation_totals AS (
            SELECT
                conversation_id,
                SUM(cost_per_run) as total_cost_per_conversation
            FROM trace_costs
            WHERE conversation_id IS NOT NULL
            GROUP BY conversation_id
        ),
        run_totals AS (
            SELECT SUM(cost_per_run) as total_cost_per_run
            FROM trace_costs
            GROUP BY trace_rowid
        """
        + SQL_COST_KPIS_ROUNDED_TAIL
    )
    df = _run_trace_kpis_query(
        query,
        project_ids,
        call_type,
        start_time=start_time,
        end_time=end_time,
        significant_figures=SIGNIFICANT_FIGURES_CREDIT_FORMAT,
    )
    mean_cost_per_run = 0
    mean_cost_per_conversation = 0
    if not df.empty:
        mean_cost_per_run = df["mean_cost_per_run"].iloc[0]
        mean_cost_per_conversation = df["mean_cost_per_conversation"].iloc[0]
        if pd.isna(mean_cost_per_run):
            LOGGER.warning(
                f"Mean cost per run is NaN for projects requests {project_ids} "
                f"and duration {duration_days} days with call type {call_type}"
            )
            mean_cost_per_run = 0
        if pd.isna(mean_cost_per_conversation):
            LOGGER.warning(
                f"Mean cost per conversation is NaN for projects requests {project_ids} "
                f"and duration {duration_days} days with call type {call_type}"
            )
            mean_cost_per_conversation = 0
    return CostKPI(cost_per_call=mean_cost_per_run, cost_per_conversation=mean_cost_per_conversation)


def get_monitoring_kpis_by_projects(
    user_id: UUID,
    project_ids: List[UUID],
    organization_id: Optional[UUID],
    duration_days: int,
    call_type: CallType | None = None,
) -> KPISResponse:
    trace_kpis = get_trace_metrics(project_ids, duration_days, call_type)
    cost_kpis = get_trace_cost_kpis(project_ids, duration_days, call_type)
    project_ids_for_tracking = ", ".join([str(project_id) for project_id in project_ids])
    track_projects_monitoring_loaded(user_id, project_ids_for_tracking, organization_id)
    project_ids_for_log = project_ids_for_tracking
    if len(project_ids) > 2:
        project_ids_for_log = f"{project_ids[0]}, {project_ids[1]} and {len(project_ids) - 2} projects"
    LOGGER.info(
        f"Trace metrics for projects {project_ids_for_log} and duration {duration_days} days retrieved successfully."
    )
    return KPISResponse(
        kpis=[
            KPI(
                title="Mean cost per call (credits)",
                color="primary",
                icon="tabler-coins",
                stats=str(cost_kpis.cost_per_call) if cost_kpis.cost_per_call is not None else "",
                change="",
            ),
            KPI(
                title="Mean cost per conversation (credits)",
                color="primary",
                icon="tabler-messages",
                stats=str(cost_kpis.cost_per_conversation) if cost_kpis.cost_per_conversation is not None else "",
                change="",
            ),
            KPI(
                title="Total requests",
                color="success",
                icon="tabler-api",
                stats=str(trace_kpis.nb_request),
                change=(
                    str(trace_kpis.nb_request_comparison_percentage) + "%"
                    if trace_kpis.nb_request_comparison_percentage is not None
                    else ""
                ),
            ),
            KPI(
                title="Average Response time",
                color="warning",
                icon="tabler-clock",
                stats=str(trace_kpis.average_latency) + "s" if trace_kpis.average_latency is not None else "",
                change=(
                    str(trace_kpis.latency_comparison_percentage) + "%"
                    if trace_kpis.latency_comparison_percentage is not None
                    else ""
                ),
            ),
        ]
    )
