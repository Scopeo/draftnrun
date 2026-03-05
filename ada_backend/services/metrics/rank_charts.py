import math
from typing import List
from uuid import UUID, uuid4

import numpy as np

from ada_backend.database.models import CallType
from ada_backend.schemas.chart_schema import Chart, ChartCategory, ChartData, ChartType, Dataset
from ada_backend.services.metrics.utils import query_trace_duration


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
                f"{num_retrieval_queries} retrieval queries - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "When someone asks a question, the retriever searches through your knowledge base "
                "and returns a list of chunks, ordered from what it thinks is most relevant (#1) "
                "to least relevant.\n\n"
                "This chart shows which positions in that list actually ended up being useful.\n\n"
                "If most useful chunks are at the top, you might try retrieving fewer chunks. "
                "If they're spread out, you likely need all of them."
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
                f"{num_reranker_queries} reranker queries - {avg_chunks_per_query} chunks used in average per query"
            ),
            details=(
                "After the retriever finds chunks, the reranker takes a second look and reorders them "
                "to try to put the best answers at the top.\n\n"
                "This chart shows which positions in the reranked list actually ended up being useful.\n\n"
                "If most useful chunks are at the top, you might try reranking fewer chunks. "
                "If they're spread out, you likely need all of them."
            ),
        )
        if reranker_chart:
            charts.append(reranker_chart)

    return charts
