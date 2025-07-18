import pytest
from unittest.mock import patch

# Import LLM service mocks
from tests.mocks.llm_service import (
    mock_llm_service,
    mock_llm_service_with_tool_calls,
    mock_llm_service_sequential,
)

# Import prometheus metrics mocks
from tests.mocks.prometheus_metrics import (
    mock_prometheus_metrics,
    mock_get_tracing_span,
    mock_agent_calls,
)

# Import ReAct agent mocks
from tests.mocks.react_agent import (
    mock_agent,
    mock_trace_manager,
    mock_tool_description,
    agent_input,
    react_agent,
    react_agent_with_tool_calls,
    react_agent_sequential,
)
from tests.mocks.source_chunks import (
    mock_source_chunk_basic,
    mock_source_chunk_empty_content,
    mock_source_chunk_many_metadata,
    mock_source_chunk_no_metadata,
    mock_source_chunk_no_url,
    mock_source_chunk_special_characters,
    mock_source_chunk_with_page_number,
)
from tests.mocks.db_service import postgres_service, sample_table_definition
from tests.mocks.utils import timestamp_with_random_suffix
from tests.mocks.ada_backend_db import ada_backend_mock_session, test_db, ada_backend_seed_session


@pytest.fixture(autouse=True)
def disable_observability_in_tests():
    """Disable observability stack for all tests to avoid external dependencies."""
    with patch("settings.settings.ENABLE_OBSERVABILITY_STACK", False):
        yield
