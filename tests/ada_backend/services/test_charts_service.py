from unittest.mock import patch
from uuid import UUID

import numpy as np
import pandas as pd

from ada_backend.schemas.chart_schema import Chart, ChartCategory, ChartData, ChartType, Dataset
from ada_backend.services.charts_service import TOKENS_DISTRIBUTION_BINS, get_tokens_distribution_chart
from ada_backend.services.metrics.rank_charts import compute_rank_bins, get_ranks_distribution_charts


@patch("ada_backend.services.charts_service.query_trace_duration")
def test_get_tokens_chart(mock_query_trace_duration):
    input_data = [100, 200, 300]
    output_data = [50, 100, 70]
    mock_df = pd.DataFrame({"llm_token_count_prompt": input_data, "llm_token_count_completion": output_data})
    mock_query_trace_duration.return_value = mock_df

    expected_bins = TOKENS_DISTRIBUTION_BINS
    expected_bin_centers = [(expected_bins[i] + expected_bins[i + 1]) / 2 for i in range(len(expected_bins) - 1)]
    expected_input_n = np.histogram(input_data, bins=expected_bins)[0]
    expected_output_n = np.histogram(output_data, bins=expected_bins)[0]

    project_id = UUID("12345678123456781234567812345678")
    duration_days = 7
    chart = get_tokens_distribution_chart([project_id], duration_days)

    assert isinstance(chart, Chart)
    assert chart.type == ChartType.BAR
    assert chart.title == "Tokens Distribution"
    assert isinstance(chart.data, ChartData)
    assert chart.data.labels == expected_bin_centers
    assert len(chart.data.datasets) == 2
    assert isinstance(chart.data.datasets[0], Dataset)
    assert chart.data.datasets[0].label == "Input Tokens Distribution"
    assert chart.data.datasets[0].data == expected_input_n.tolist()
    assert isinstance(chart.data.datasets[1], Dataset)
    assert chart.data.datasets[1].label == "Output Tokens Distribution"
    assert chart.data.datasets[1].data == expected_output_n.tolist()


def test_compute_rank_bins_small():
    edges, labels = compute_rank_bins(1)
    assert edges == [1, 2]
    assert labels == ["1"]

    edges, labels = compute_rank_bins(5)
    assert edges == [1, 2, 3, 4, 5, 6]
    assert labels == ["1", "2", "3", "4", "5"]

    edges, labels = compute_rank_bins(10)
    assert edges == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    assert labels == ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10"]


def test_compute_rank_bins_large():
    edges, labels = compute_rank_bins(100)
    assert len(labels) == 10
    assert edges[0] == 1
    assert edges[-1] == 101
    assert labels[0] == "1-10"
    assert labels[-1] == "91-100"

    edges, labels = compute_rank_bins(50)
    assert len(labels) == 10
    assert edges[0] == 1
    assert edges[-1] == 51
    assert labels[0] == "1-5"
    assert labels[-1] == "46-50"

    edges, labels = compute_rank_bins(33)
    assert len(labels) == 10
    assert edges[0] == 1
    assert edges[-1] == 34
    assert labels[-1] == "31-33"


@patch("ada_backend.services.metrics.rank_charts.query_trace_duration")
def test_get_ranks_distribution_charts_with_totals(mock_query_trace_duration):
    total_retrieved = 50
    total_reranked = 10
    retrieval_ranks = [1, 2, 3, 1, 5, 7, 10]
    reranker_ranks = [1, 1, 2, 4, 6, 9]

    mock_df = pd.DataFrame({
        "attributes": [
            {
                "original_retrieval_rank": [1, 2, 3],
                "original_reranker_rank": [1, 1, 2],
                "total_retrieved_chunks": total_retrieved,
                "total_reranked_chunks": total_reranked,
            },
            {
                "original_retrieval_rank": [1, 5],
                "original_reranker_rank": [4, 6],
                "total_retrieved_chunks": total_retrieved,
                "total_reranked_chunks": total_reranked,
            },
            {
                "original_retrieval_rank": [7, 10],
                "original_reranker_rank": [9],
                "total_retrieved_chunks": total_retrieved,
                "total_reranked_chunks": total_reranked,
            },
        ]
    })
    mock_query_trace_duration.return_value = mock_df

    num_queries = 3

    retrieval_bins, retrieval_labels = compute_rank_bins(total_retrieved)
    reranker_bins, reranker_labels = compute_rank_bins(total_reranked)

    expected_retrieval_hist = np.histogram(retrieval_ranks, bins=retrieval_bins)[0]
    expected_reranker_hist = np.histogram(reranker_ranks, bins=reranker_bins)[0]

    retrieval_bin_widths = [retrieval_bins[i + 1] - retrieval_bins[i] for i in range(len(retrieval_bins) - 1)]
    reranker_bin_widths = [reranker_bins[i + 1] - reranker_bins[i] for i in range(len(reranker_bins) - 1)]

    expected_retrieval_pct = [
        round(count / (width * num_queries) * 100, 1)
        for count, width in zip(expected_retrieval_hist, retrieval_bin_widths)
    ]
    expected_reranker_pct = [
        round(count / (width * num_queries) * 100, 1)
        for count, width in zip(expected_reranker_hist, reranker_bin_widths)
    ]

    project_id = UUID("12345678123456781234567812345678")
    charts = get_ranks_distribution_charts([project_id], 7)

    assert len(charts) == 2

    avg_retrieval_chunks = round(len(retrieval_ranks) / num_queries, 1)
    avg_reranker_chunks = round(len(reranker_ranks) / num_queries, 1)

    retrieval_chart = charts[0]
    assert isinstance(retrieval_chart, Chart)
    assert retrieval_chart.type == ChartType.BAR
    assert retrieval_chart.title == "Chunk usage by retriever ranking"
    assert (
        retrieval_chart.subtitle
        == f"{num_queries} retrieval queries - {avg_retrieval_chunks} chunks used in average per query"
    )
    assert retrieval_chart.category == ChartCategory.RETRIEVAL
    assert retrieval_chart.y_axis_label == "Chunk usage rate (%)"
    assert retrieval_chart.details is not None
    assert isinstance(retrieval_chart.data, ChartData)
    assert retrieval_chart.data.labels == retrieval_labels
    assert len(retrieval_chart.data.datasets) == 1
    assert retrieval_chart.data.datasets[0].label == "Chunk usage rate"
    assert retrieval_chart.data.datasets[0].data == expected_retrieval_pct

    reranker_chart = charts[1]
    assert isinstance(reranker_chart, Chart)
    assert reranker_chart.type == ChartType.BAR
    assert reranker_chart.title == "Chunk usage by reranker ranking"
    assert (
        reranker_chart.subtitle
        == f"{num_queries} reranker queries - {avg_reranker_chunks} chunks used in average per query"
    )
    assert reranker_chart.category == ChartCategory.RETRIEVAL
    assert reranker_chart.y_axis_label == "Chunk usage rate (%)"
    assert reranker_chart.details is not None
    assert isinstance(reranker_chart.data, ChartData)
    assert reranker_chart.data.labels == reranker_labels
    assert len(reranker_chart.data.datasets) == 1
    assert reranker_chart.data.datasets[0].label == "Chunk usage rate"
    assert reranker_chart.data.datasets[0].data == expected_reranker_pct


@patch("ada_backend.services.metrics.rank_charts.query_trace_duration")
def test_get_ranks_distribution_charts_fallback_to_max_rank(mock_query_trace_duration):
    """When total_*_chunks attributes are missing, fall back to max(ranks)."""
    mock_df = pd.DataFrame({
        "attributes": [
            {"original_retrieval_rank": [1, 3, 7]},
        ]
    })
    mock_query_trace_duration.return_value = mock_df

    project_id = UUID("12345678123456781234567812345678")
    charts = get_ranks_distribution_charts([project_id], 7)

    assert len(charts) == 1
    retrieval_chart = charts[0]
    _, expected_labels = compute_rank_bins(7)
    assert retrieval_chart.data.labels == expected_labels


@patch("ada_backend.services.metrics.rank_charts.query_trace_duration")
def test_get_ranks_distribution_charts_empty(mock_query_trace_duration):
    mock_df = pd.DataFrame({"attributes": [{}]})
    mock_query_trace_duration.return_value = mock_df

    project_id = UUID("12345678123456781234567812345678")
    charts = get_ranks_distribution_charts([project_id], 7)
    assert charts == []
