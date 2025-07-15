from unittest.mock import MagicMock

import pytest


def setup_prometheus_mocks(get_span_mock, agent_calls_mock):
    """Helper function to setup prometheus mocks consistently across tests."""
    get_span_mock.return_value.project_id = "1234"
    counter_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    return counter_mock


@pytest.fixture
def mock_prometheus_metrics():
    """Mock prometheus metrics for consistent patching across tests."""
    get_span_mock = MagicMock()
    get_span_mock.return_value.project_id = "1234"

    counter_mock = MagicMock()
    agent_calls_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock

    return {"get_span": get_span_mock, "agent_calls": agent_calls_mock, "counter": counter_mock}


@pytest.fixture
def mock_get_tracing_span():
    """Mock get_tracing_span function."""
    mock_span = MagicMock()
    mock_span.project_id = "1234"
    return mock_span


@pytest.fixture
def mock_agent_calls():
    """Mock agent_calls metric."""
    counter_mock = MagicMock()
    agent_calls_mock = MagicMock()
    agent_calls_mock.labels.return_value = counter_mock
    return agent_calls_mock, counter_mock
