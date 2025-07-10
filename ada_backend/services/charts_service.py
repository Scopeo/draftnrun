from collections import OrderedDict
from uuid import UUID
from datetime import datetime, timedelta, timezone
import requests

import numpy as np
import pandas as pd

from ada_backend.schemas.chart_schema import Chart, ChartData, ChartType, ChartsResponse, Dataset
from ada_backend.services.metrics.utils import query_trace_duration


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
    url = "http://localhost:9090/api/v1/query_range"
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


def get_agent_usage_chart(project_id: UUID, duration_days: int) -> Chart:
    current_date = datetime.now(tz=timezone.utc)
    start_date = current_date - timedelta(days=duration_days)
    all_dates_df = pd.DataFrame(
        pd.date_range(start=start_date.date(), end=current_date.date(), freq="D"), columns=["date"]
    )

    df = query_trace_duration(project_id, duration_days)
    df["date"] = pd.to_datetime(df["start_time"]).dt.normalize()
    datasets = []
    df_with_conversation_id = df[
        df["attributes"].apply(
            lambda x: isinstance(x, dict) and "conversation_id" in x and x["conversation_id"] is not None
        )
    ].copy()
    if not df_with_conversation_id.empty:
        df_with_conversation_id["conversation_id"] = df_with_conversation_id["attributes"].apply(
            lambda x: x.get("conversation_id")
        )
        conversation_id_usage = (
            df_with_conversation_id.groupby("date")["conversation_id"]
            .nunique()
            .reset_index(name="unique_conversation_ids")
        )
        conversation_id_usage = pd.merge(all_dates_df, conversation_id_usage, on="date", how="left").fillna(0)
        conversation_id_usage["unique_conversation_ids"] = conversation_id_usage["unique_conversation_ids"].astype(int)
        conversation_id_usage["date"] = conversation_id_usage["date"].dt.date.astype(str)
        conversation_id_usage = conversation_id_usage.sort_values(by="date", ascending=True)
        datasets.append(
            Dataset(
                label="Number of conversations per day", data=conversation_id_usage["unique_conversation_ids"].tolist()
            )
        )

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

    df = df[df["parent_id"].isna()].copy()
    agent_usage = df.groupby("date").size().reset_index(name="count")
    agent_usage = pd.merge(all_dates_df, agent_usage, on="date", how="left").fillna(0)
    agent_usage["count"] = agent_usage["count"].astype(int)
    agent_usage["date"] = pd.to_datetime(agent_usage["date"]).dt.date
    agent_usage = agent_usage.sort_values(by="date", ascending=True)
    agent_usage["date"] = agent_usage["date"].astype(str)

    datasets.append(Dataset(label="Number of calls per day", data=agent_usage["count"].tolist()))

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


def get_latence_chart(project_id: UUID, duration_days: int) -> Chart:
    df = query_trace_duration(project_id, duration_days)
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


def get_tokens_distribution_chart(project_id: UUID, duration_days: int) -> Chart:
    df = query_trace_duration(project_id, duration_days)
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


def get_charts_by_project(project_id: UUID, duration_days: int) -> ChartsResponse:
    print("GET CHARTS BY PROJECT", project_id, duration_days)
    response = ChartsResponse(
        charts=(
            get_agent_usage_chart(project_id, duration_days)
            + [
                get_latence_chart(project_id, duration_days),
                # get_prometheus_agent_calls_chart(project_id, duration_days),
                get_tokens_distribution_chart(project_id, duration_days),
            ]
        )
    )
    if len(response.charts) == 0:
        raise ValueError("No charts found for this project")
    return response
