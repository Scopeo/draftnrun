from unittest.mock import patch
from uuid import UUID

import numpy as np
import pandas as pd

from ada_backend.services.charts_service import get_tokens_distribution_chart
from ada_backend.schemas.chart_schema import Chart, ChartType, ChartData, Dataset


@patch("ada_backend.services.charts_service.query_trace_duration")
def test_get_tokens_chart(mock_query_trace_duration):
    input_data = [100, 200, 300]
    output_data = [50, 100, 70]
    mock_df = pd.DataFrame({"llm_token_count_prompt": input_data, "llm_token_count_completion": output_data})
    mock_query_trace_duration.return_value = mock_df

    expected_bins = [200, 500, 1000, 2000, 3000, 5000, 7000, 10000]
    expected_bin_centers = [(expected_bins[i] + expected_bins[i + 1]) / 2 for i in range(len(expected_bins) - 1)]
    expected_input_n = np.histogram(input_data, bins=expected_bins)[0]
    expected_output_n = np.histogram(output_data, bins=expected_bins)[0]

    project_id = UUID("12345678123456781234567812345678")
    duration_days = 7
    chart = get_tokens_distribution_chart(project_id, duration_days)

    assert isinstance(chart, Chart)
    assert chart.id == f"tokens_distribution_{project_id}"
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
