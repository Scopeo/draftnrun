from collections import OrderedDict
from uuid import UUID
from datetime import datetime, timedelta, timezone
import requests

import numpy as np

from ada_backend.schemas.chart_schema import Chart, ChartData, ChartType, ChartsResponse, Dataset
from ada_backend.services.metrics.utils import query_trace_duration


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


def get_tokens_chart(project_id: UUID, duration_days: int) -> Chart:
    df = query_trace_duration(project_id, duration_days)
    input_data = df[df["llm_token_count_prompt"].notna()]["llm_token_count_prompt"]
    output_data = df[df["llm_token_count_completion"].notna()]["llm_token_count_completion"]
    bins_edges = [200, 500, 1000, 2000, 3000, 5000, 7000, 10000]

    input_token_hist, _ = np.histogram(input_data, bins=bins_edges)
    output_token_hist, _ = np.histogram(output_data, bins=bins_edges)
    bin_centers = [(bins_edges[i] + bins_edges[i + 1]) / 2 for i in range(len(bins_edges) - 1)]

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
        charts=[
            get_prometheus_agent_calls_chart(project_id, duration_days),
            get_tokens_chart(project_id, duration_days),
            Chart(
                id="resource-distribution",
                type=ChartType.DOUGHNUT,
                title="Resource Distribution",
                data=ChartData(
                    labels=["1", "2", "3", "4"],
                    datasets=[
                        Dataset(
                            label="Resource Distribution",
                            data=[45, 25, 20, 10],
                            backgroundColor=["#FF5733", "#4CAF50", "#2196F3", "#FFC107"],
                        )
                    ],
                ),
            ),
        ]
    )
    if len(response.charts) == 0:
        raise ValueError("No charts found for this project")
    return response
