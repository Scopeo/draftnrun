from collections import OrderedDict
from uuid import UUID
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from typing import Optional
import requests

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType
from ada_backend.schemas.chart_schema import Chart, ChartData, ChartType, ChartsResponse, Dataset, CreditUsage
from ada_backend.services.metrics.utils import (
    query_trace_duration,
    calculate_calls_per_day,
    count_conversations_per_day,
)
from ada_backend.repositories.credits_repository import get_organization_total_credits, get_organization_limit
from ada_backend.repositories.project_repository import get_project
from settings import settings


TOKENS_DISTRIBUTION_BINS = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]


def calculate_prometheus_step(duration_days: int, target_points: int = 200) -> str:
    duration_seconds = duration_days * 24 * 60 * 60
    raw_step = duration_seconds / target_points
    step_mapping = OrderedDict(
        [
            (15, "15s"),
            (30, "30s"),
            (60, "1m"),
            (300, "5m"),
            (900, "15m"),
            (3600, "1h"),
            (21600, "6h"),
            (86400, "1d"),
        ]
    )
    for threshold, step in step_mapping.items():
        if raw_step <= threshold:
            return step
    return "7d"


def query_prometheus_agent_calls(project_id: UUID, start_time: str, end_time: str, step: str) -> dict:
    url = f"{settings.PROMETHEUS_URL}/api/v1/query_range"
    params = {
        "query": f'agent_calls_total{{project_id="{project_id}"}}',
        "start": start_time,
        "end": end_time,
        "step": step,
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    return response.json()


def convert_prometheus_response_to_chart_data(response: dict) -> ChartData:
    prometheus_data = response["data"]["result"]
    timestamps = sorted(set(ts for series in prometheus_data for ts, _ in series["values"]))
    color_palette_count = len(prometheus_data)
    aligned_series = []
    for i, series in enumerate(prometheus_data):
        class_name = series["metric"]["class_name"]
        series_dict = dict(series["values"])
        aligned_data = [
            None if np.isnan(float(series_dict.get(ts, np.nan))) else float(series_dict.get(ts, np.nan))
            for ts in timestamps
        ]
        aligned_series.append(
            Dataset(
                label=class_name,
                data=aligned_data,
                borderColor=(
                    f"hsl({360 * i / color_palette_count}, 100%, 50%)" if color_palette_count > 1 else "#FF5733"
                ),
                fill=False,
            )
        )
    return ChartData(labels=timestamps, datasets=aligned_series)


def get_prometheus_agent_calls_chart(project_id: UUID, duration_days: int) -> Chart:
    end_time = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    start_time = (datetime.now(tz=timezone.utc) - timedelta(days=duration_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    step = calculate_prometheus_step(duration_days)
    reponse_json = query_prometheus_agent_calls(project_id, start_time, end_time, step)
    return Chart(
        id=f"agent-metrics_{project_id}",
        type=ChartType.LINE,
        title="Agent Performance Metrics",
        data=convert_prometheus_response_to_chart_data(reponse_json),
        x_axis_type="datetime",
    )


def get_agent_usage_chart(project_id: UUID, duration_days: int, call_type: CallType | None = None) -> list[Chart]:
    current_date = datetime.now(tz=timezone.utc)
    start_date = current_date - timedelta(days=duration_days)
    all_dates_df = pd.DataFrame(
        pd.date_range(start=start_date.date(), end=current_date.date(), freq="D", tz=timezone.utc), columns=["date"]
    )

    df = query_trace_duration(project_id, duration_days, call_type)
    df["date"] = pd.to_datetime(df["start_time"]).dt.normalize()
    datasets = []

    agent_usage = calculate_calls_per_day(df, all_dates_df)
    datasets.append(Dataset(label="Number of calls per day", data=agent_usage["count"].tolist()))

    conversation_id_usage = count_conversations_per_day(df, all_dates_df)
    datasets.append(
        Dataset(
            label="Number of conversations per day", data=conversation_id_usage["unique_conversation_ids"].tolist()
        )
    )

    # Calculate token usage
    df[["llm_token_count_prompt", "llm_token_count_completion"]] = df[
        ["llm_token_count_prompt", "llm_token_count_completion"]
    ].fillna(0)
    token_usage = (
        df.groupby("date")[["llm_token_count_prompt", "llm_token_count_completion"]]
        .sum()
        .reset_index()
        .rename(columns={"llm_token_count_prompt": "input_tokens", "llm_token_count_completion": "output_tokens"})
    )
    token_usage = pd.merge(all_dates_df, token_usage, on="date", how="left").fillna(0)
    token_usage[["input_tokens", "output_tokens"]] = token_usage[["input_tokens", "output_tokens"]].astype(int)
    token_usage["date"] = pd.to_datetime(token_usage["date"]).dt.date
    token_usage = token_usage.sort_values(by="date", ascending=True)
    token_usage["date"] = token_usage["date"].astype(str)

    return [
        Chart(
            id=f"agent_usage_{project_id}",
            type=ChartType.LINE,
            title="Agent Usage",
            data=ChartData(
                labels=agent_usage["date"].tolist(),
                datasets=datasets,
            ),
            x_axis_type="datetime",
        ),
        Chart(
            id=f"token_usage_{project_id}",
            type=ChartType.LINE,
            title="Token Usage",
            data=ChartData(
                labels=agent_usage["date"].tolist(),
                datasets=[
                    Dataset(
                        label="Input tokens per day",
                        data=token_usage["input_tokens"].tolist(),
                        borderColor="#FF5733",
                    ),
                    Dataset(
                        label="Output tokens per day",
                        data=token_usage["output_tokens"].tolist(),
                        borderColor="#33FF57",
                    ),
                ],
            ),
            x_axis_type="datetime",
        ),
    ]


def get_latence_chart(project_id: UUID, duration_days: int, call_type: CallType | None = None) -> Chart:
    df = query_trace_duration(project_id, duration_days, call_type)
    df = df[df["parent_id"].isna()]
    df["start_time"] = pd.to_datetime(df["start_time"])
    df["end_time"] = pd.to_datetime(df["end_time"])
    df["duration"] = (df["end_time"] - df["start_time"]).dt.total_seconds()

    latency_hist, bins_edges = np.histogram(df["duration"], bins="fd")
    bin_centers = [np.round((bins_edges[i] + bins_edges[i + 1]) / 2, 1) for i in range(len(bins_edges) - 1)]
    return Chart(
        id=f"latency_distribution_{project_id}",
        type=ChartType.BAR,
        title="Latency Distribution (seconds)",
        data=ChartData(
            labels=bin_centers,
            datasets=[
                Dataset(label="Latency Distribution", data=latency_hist.tolist()),
            ],
        ),
    )


def get_tokens_distribution_chart(project_id: UUID, duration_days: int, call_type: CallType | None = None) -> Chart:
    df = query_trace_duration(project_id, duration_days, call_type)
    input_data = df[df["llm_token_count_prompt"].notna()]["llm_token_count_prompt"]
    output_data = df[df["llm_token_count_completion"].notna()]["llm_token_count_completion"]

    input_token_hist, _ = np.histogram(input_data, bins=TOKENS_DISTRIBUTION_BINS)
    output_token_hist, _ = np.histogram(output_data, bins=TOKENS_DISTRIBUTION_BINS)
    bin_centers = [
        (TOKENS_DISTRIBUTION_BINS[i] + TOKENS_DISTRIBUTION_BINS[i + 1]) / 2
        for i in range(len(TOKENS_DISTRIBUTION_BINS) - 1)
    ]

    return Chart(
        id=f"tokens_distribution_{project_id}",
        type=ChartType.BAR,
        title="Tokens Distribution",
        data=ChartData(
            labels=bin_centers,
            datasets=[
                Dataset(label="Input Tokens Distribution", data=input_token_hist.tolist()),
                Dataset(label="Output Tokens Distribution", data=output_token_hist.tolist()),
            ],
        ),
    )


def get_organization_credit_usage_data(session: Session, project_id: UUID) -> Optional[CreditUsage]:
    """Get organization credit usage data for table display."""
    project = get_project(session, project_id=project_id)
    if not project:
        return None

    today = datetime.now()
    organization_id = project.organization_id

    credits_used = get_organization_total_credits(session, organization_id, today.year, today.month)
    org_limit = get_organization_limit(session, organization_id, today.year, today.month)
    credits_limit = org_limit.limit if org_limit else None
    percentage_used = round((credits_used / credits_limit) * 100, 1) if credits_limit and credits_limit > 0 else None

    last_day = monthrange(today.year, today.month)[1]
    reset_datetime = datetime(today.year, today.month, last_day, 23, 59, 59)
    days_left = (reset_datetime - today).days
    reset_date = f"{days_left} days left" if days_left >= 0 else "0 days left"

    return CreditUsage(
        credits_used=credits_used,
        credits_limit=credits_limit,
        percentage_used=percentage_used,
        reset_date=reset_date,
    )


async def get_charts_by_project(
    session: Session,
    project_id: UUID,
    duration_days: int,
    call_type: CallType | None = None,
) -> ChartsResponse:
    charts = get_agent_usage_chart(project_id, duration_days, call_type) + [
        get_latence_chart(project_id, duration_days, call_type),
        get_tokens_distribution_chart(project_id, duration_days, call_type),
    ]

    credit_usage = get_organization_credit_usage_data(session=session, project_id=project_id)

    response = ChartsResponse(charts=charts, credit_usage=credit_usage)
    if len(response.charts) == 0:
        raise ValueError("No charts found for this project")
    return response
