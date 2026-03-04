from unittest.mock import patch
from uuid import UUID

import numpy as np
import pandas as pd

from ada_backend.schemas.chart_schema import Chart, ChartData, ChartType, Dataset
from ada_backend.services.charts_service import (
    RANKS_DISTRIBUTION_BINS,
    TOKENS_DISTRIBUTION_BINS,
    get_ranks_distribution_chart,
    get_tokens_distribution_chart,
)


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


@patch("ada_backend.services.charts_service.query_trace_duration")
def test_get_ranks_distribution_chart(mock_query_trace_duration):
    retrieval_ranks = [1, 2, 3, 1, 5, 7, 10]
    reranker_ranks = [1, 1, 2, 4, 6, 9]

    mock_df = pd.DataFrame({
        "attributes": [
            {"original_retrieval_rank": [1, 2, 3], "original_reranker_rank": [1, 1, 2]},
            {"original_retrieval_rank": [1, 5], "original_reranker_rank": [4, 6]},
            {"original_retrieval_rank": [7, 10], "original_reranker_rank": [9]},
        ]
    })
    mock_query_trace_duration.return_value = mock_df

    expected_bins = RANKS_DISTRIBUTION_BINS
    expected_labels = ["1", "2-5", "6-10"]
    expected_retrieval_hist = np.histogram(retrieval_ranks, bins=expected_bins)[0]
    expected_reranker_hist = np.histogram(reranker_ranks, bins=expected_bins)[0]

    retrieval_total = expected_retrieval_hist.sum()
    reranker_total = expected_reranker_hist.sum()

    expected_retrieval_percentages = [round(x, 1) for x in (expected_retrieval_hist / retrieval_total * 100).tolist()]
    expected_reranker_percentages = [round(x, 1) for x in (expected_reranker_hist / reranker_total * 100).tolist()]

    project_id = UUID("12345678123456781234567812345678")
    duration_days = 7
    chart = get_ranks_distribution_chart([project_id], duration_days)

    assert isinstance(chart, Chart)
    assert chart.type == ChartType.HISTOGRAM
    assert chart.title == "Ranks Distribution"
    assert isinstance(chart.data, ChartData)
    assert chart.data.labels == expected_labels
    assert len(chart.data.datasets) == 2
    assert isinstance(chart.data.datasets[0], Dataset)
    assert chart.data.datasets[0].label == "Retrieval Rank Distribution"
    assert chart.data.datasets[0].data == expected_retrieval_percentages
    assert chart.data.datasets[0].backgroundColor == "rgba(54, 162, 235, 0.6)"
    assert isinstance(chart.data.datasets[1], Dataset)
    assert chart.data.datasets[1].label == "Reranker Rank Distribution"
    assert chart.data.datasets[1].data == expected_reranker_percentages
    assert chart.data.datasets[1].backgroundColor == "rgba(255, 99, 132, 0.6)"
