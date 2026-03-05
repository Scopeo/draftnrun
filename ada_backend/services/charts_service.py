import math
from calendar import monthrange
from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import List
from uuid import UUID, uuid4

import numpy as np
import pandas as pd
import requests
from sqlalchemy.orm import Session

from ada_backend.database.models import CallType
from ada_backend.repositories.credits_repository import get_organization_limit, get_organization_total_credits
from ada_backend.schemas.chart_schema import Chart, ChartCategory, ChartData, ChartsResponse, ChartType, Dataset
from ada_backend.services.metrics.utils import (
    calculate_calls_per_day,
    count_conversations_per_day,
    query_trace_duration,
)
from settings import settings

TOKENS_DISTRIBUTION_BINS = [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]


def compute_rank_bins(total: int) -> tuple[list[int], list[str]]:
    if total <= 10:
        edges = list(range(1, total + 2))
        labels = [str(i) for i in range(1, total + 1)]
        return edges, labels

    raw_width = total / 10
    edges = [math.ceil(1 + i * raw_width) for i in range(10)] + [total + 1]
    labels = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1] - 1
        labels.append(str(lo) if lo == hi else f"{lo}-{hi}")
    return edges, labels


def calculate_prometheus_step(duration_days: int, target_points: int = 200) -> str:
    duration_seconds = duration_days * 24 * 60 * 60
    raw_step = duration_seconds / target_points
    step_mapping = OrderedDict([
        (15, "15s"),
        (30, "30s"),
        (60, "1m"),
        (300, "5m"),
        (900, "15m"),
        (3600, "1h"),
        (21600, "6h"),
        (86400, "1d"),
    ])
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


def get_agent_usage_chart(
    project_ids: List[UUID], duration_days: int, call_type: CallType | None = None
) -> list[Chart]:
    current_date = datetime.now(tz=timezone.utc)
    start_date = current_date - timedelta(days=duration_days)
    all_dates_df = pd.DataFrame(
        pd.date_range(start=start_date.date(), end=current_date.date(), freq="D", tz=timezone.utc), columns=["date"]
    )

    df = query_trace_duration(project_ids, duration_days, call_type)
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
        df
        .groupby("date")[["llm_token_count_prompt", "llm_token_count_completion"]]
        .sum()
        .reset_index()
        .rename(columns={"llm_token_count_prompt": "input_tokens", "llm_token_count_completion": "output_tokens"})
    )
    token_usage = pd.merge(all_dates_df, token_usage, on="date", how="left").fillna(0)
    token_usage[["input_tokens", "output_tokens"]] = token_usage[["input_tokens", "output_tokens"]].astype(int)
    token_usage["date"] = pd.to_datetime(token_usage["date"]).dt.date
    token_usage = token_usage.sort_values(by="date", ascending=True)
    token_usage["date"] = token_usage["date"].astype(str)

    chart_id = str(uuid4())

    return [
        Chart(
            id=f"agent_usage_{chart_id}",
            type=ChartType.LINE,
            title="Agent Usage",
            data=ChartData(
                labels=agent_usage["date"].tolist(),
                datasets=datasets,
            ),
            x_axis_type="datetime",
            category=ChartCategory.GENERAL,
        ),
        Chart(
            id=f"token_usage_{chart_id}",
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
            category=ChartCategory.GENERAL,
        ),
    ]


def get_latence_chart(project_ids: List[UUID], duration_days: int, call_type: CallType | None = None) -> Chart:
    df = query_trace_duration(project_ids, duration_days, call_type)
    df = df[df["parent_id"].isna()]
    df["start_time"] = pd.to_datetime(df["start_time"])
    df["end_time"] = pd.to_datetime(df["end_time"])
    df["duration"] = (df["end_time"] - df["start_time"]).dt.total_seconds()

    latency_hist, bins_edges = np.histogram(df["duration"], bins="fd")
    bin_centers = [np.round((bins_edges[i] + bins_edges[i + 1]) / 2, 1) for i in range(len(bins_edges) - 1)]

    chart_id_suffix = str(uuid4())

    return Chart(
        id=f"latency_distribution_{chart_id_suffix}",
        type=ChartType.BAR,
        title="Latency Distribution (seconds)",
        data=ChartData(
            labels=bin_centers,
            datasets=[
                Dataset(label="Latency Distribution", data=latency_hist.tolist()),
            ],
        ),
        category=ChartCategory.GENERAL,
    )


def get_tokens_distribution_chart(
    project_ids: List[UUID], duration_days: int, call_type: CallType | None = None
) -> Chart:
    df = query_trace_duration(project_ids, duration_days, call_type)
    input_data = df[df["llm_token_count_prompt"].notna()]["llm_token_count_prompt"]
    output_data = df[df["llm_token_count_completion"].notna()]["llm_token_count_completion"]

    input_token_hist, _ = np.histogram(input_data, bins=TOKENS_DISTRIBUTION_BINS)
    output_token_hist, _ = np.histogram(output_data, bins=TOKENS_DISTRIBUTION_BINS)
    bin_centers = [
        (TOKENS_DISTRIBUTION_BINS[i] + TOKENS_DISTRIBUTION_BINS[i + 1]) / 2
        for i in range(len(TOKENS_DISTRIBUTION_BINS) - 1)
    ]

    chart_id = str(uuid4())

    return Chart(
        id=f"tokens_distribution_{chart_id}",
        type=ChartType.BAR,
        title="Tokens Distribution",
        data=ChartData(
            labels=bin_centers,
            datasets=[
                Dataset(label="Input Tokens Distribution", data=input_token_hist.tolist()),
                Dataset(label="Output Tokens Distribution", data=output_token_hist.tolist()),
            ],
        ),
        category=ChartCategory.GENERAL,
    )


def _build_rank_chart(
    ranks: list,
    total_chunks: int,
    num_queries: int,
    title: str,
    subtitle: str,
    details: str,
) -> Chart | None:
    if not ranks:
        return None
    ranks_array = np.array(ranks)
    bins, labels = compute_rank_bins(total_chunks)
    hist, _ = np.histogram(ranks_array, bins=bins)
    bin_widths = [bins[i + 1] - bins[i] for i in range(len(bins) - 1)]
    percentages = (
        [round(count / (width * num_queries) * 100, 1) for count, width in zip(hist, bin_widths)]
        if num_queries > 0
        else [0] * len(hist)
    )
    chart_id = str(uuid4())
    return Chart(
        id=f"ranks_distribution_{chart_id}",
        type=ChartType.BAR,
        title=title,
        subtitle=subtitle,
        data=ChartData(
            labels=labels,
            datasets=[Dataset(label="Chunk usage rate", data=percentages)],
        ),
        x_axis_label="Rank",
        y_axis_label="Chunk usage rate (%)",
        category=ChartCategory.RETRIEVAL,
        details=details,
    )


def _parse_ranks_attribute(attributes: dict, key: str) -> list:
    try:
        ranks = attributes[key]
        if isinstance(ranks, str):
            ranks = eval(ranks)
        if isinstance(ranks, list) and ranks:
            return [r for r in ranks if r is not None]
    except Exception:
        pass
    return []


def get_ranks_distribution_charts(
    project_ids: List[UUID], duration_days: int, call_type: CallType | None = None
) -> list[Chart]:
    df = query_trace_duration(project_ids, duration_days, call_type)

    retrieval_ranks = []
    reranker_ranks = []
    max_total_retrieved = 0
    max_total_reranked = 0
    num_retrieval_queries = 0
    num_reranker_queries = 0

    for _, row in df.iterrows():
        attributes = row.get("attributes", {})
        if not attributes:
            continue

        if "original_retrieval_rank" in attributes:
            parsed = _parse_ranks_attribute(attributes, "original_retrieval_rank")
            if parsed:
                retrieval_ranks.extend(parsed)
                num_retrieval_queries += 1
        if "original_reranker_rank" in attributes:
            parsed = _parse_ranks_attribute(attributes, "original_reranker_rank")
            if parsed:
                reranker_ranks.extend(parsed)
                num_reranker_queries += 1

        total_retrieved = attributes.get("total_retrieved_chunks")
        if total_retrieved is not None:
            max_total_retrieved = max(max_total_retrieved, int(total_retrieved))
        total_reranked = attributes.get("total_reranked_chunks")
        if total_reranked is not None:
            max_total_reranked = max(max_total_reranked, int(total_reranked))

    if not max_total_retrieved and retrieval_ranks:
        max_total_retrieved = int(np.array(retrieval_ranks).max())
    if not max_total_reranked and reranker_ranks:
        max_total_reranked = int(np.array(reranker_ranks).max())

    charts = []

    if retrieval_ranks and num_retrieval_queries > 0:
        avg_chunks_per_query = round(len(retrieval_ranks) / num_retrieval_queries, 1)
        retrieval_chart = _build_rank_chart(
            retrieval_ranks,
            max_total_retrieved,
            num_retrieval_queries,
            title="Chunk usage by retriever ranking",
            subtitle=(
                f"{num_retrieval_queries} retrieval queries"
                f" - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "When someone asks a question, the retriever searches through your knowledge base "
                "and returns a list of chunks, ordered from what it thinks is most relevant (#1) "
                "to least relevant. This chart shows which positions in that list actually ended up "
                "being useful. If most of the useful chunks come from the top of the list, "
                "your retriever is doing a great job. If useful chunks are often found further down, "
                "it means the retriever is not putting the best answers first."
            ),
        )
        if retrieval_chart:
            charts.append(retrieval_chart)

    if reranker_ranks and num_reranker_queries > 0:
        avg_chunks_per_query = round(len(reranker_ranks) / num_reranker_queries, 1)
        reranker_chart = _build_rank_chart(
            reranker_ranks,
            max_total_reranked,
            num_reranker_queries,
            title="Chunk usage by reranker ranking",
            subtitle=(
                f"{num_reranker_queries} reranker queries"
                f" - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "After the retriever finds chunks, the reranker takes a second look and reorders them "
                "to try to put the best answers at the top. This chart shows which positions in the "
                "reranked list actually ended up being useful. If most useful chunks are near the top, "
                "the reranker is helping. If they are spread out or stuck at the bottom, "
                "the reranker is not improving the order much."
            ),
        )
        if reranker_chart:
            charts.append(reranker_chart)

    return charts


async def get_credit_usage_table_chart(session: Session, organization_id: UUID) -> Chart:
    """Get organization credit usage as a table chart."""
    today = datetime.now()

    credits_used = get_organization_total_credits(session, organization_id, today.year, today.month)
    org_limit = get_organization_limit(session, organization_id)
    credits_limit = org_limit.limit if org_limit else None
    percentage_used = round((credits_used / credits_limit) * 100, 1) if credits_limit and credits_limit > 0 else None

    last_day = monthrange(today.year, today.month)[1]
    reset_datetime = datetime(today.year, today.month, last_day, 23, 59, 59)

    credits_used_formatted = f"{credits_used:,.0f}".replace(",", " ")
    credits_limit_formatted = f"{credits_limit:,.0f}".replace(",", " ") if credits_limit is not None else "N/A"

    labels = ["Organization Credit Usage", "Reset Date"]

    credits_display = (
        f"{credits_used_formatted} / {credits_limit_formatted} credits"
        if credits_limit is not None
        else f"{credits_used_formatted} credits"
    )

    reset_display = reset_datetime.strftime("%d/%m/%Y")

    data_values = [
        credits_display,
        reset_display,
    ]

    chart = Chart(
        id=f"credit_usage_{organization_id}",
        type=ChartType.TABLE,
        title="Organization Credit Usage",
        data=ChartData(
            labels=labels,
            datasets=[Dataset(label="Value", data=data_values)],
        ),
        progress_percentage=percentage_used if percentage_used is not None else None,
    )

    return ChartsResponse(charts=[chart])


async def get_charts_by_projects(
    project_ids: List[UUID],
    duration_days: int,
    call_type: CallType | None = None,
) -> ChartsResponse:
    charts = get_agent_usage_chart(project_ids, duration_days, call_type) + [
        get_latence_chart(project_ids, duration_days, call_type),
        # get_prometheus_agent_calls_chart(project_id, duration_days),
        get_tokens_distribution_chart(project_ids, duration_days, call_type),
    ]

    charts.extend(get_ranks_distribution_charts(project_ids, duration_days, call_type))

    response = ChartsResponse(charts=charts)
    if len(response.charts) == 0:
        raise ValueError("No charts found for this project")
    return response
