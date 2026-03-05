import os
from unittest.mock import patch

import pytest
from pytest_alembic.config import Config
from pytest_mock_resources import create_postgres_fixture

os.environ.setdefault("PMR_POSTGRES_IMAGE", "postgres:16")

alembic_engine = create_postgres_fixture()


@pytest.fixture
def alembic_config():
    cfg = Config(config_options={"file": "ada_backend/database/alembic.ini"})
    return cfg


# Import LLM service mocks
from tests.mocks.ada_backend_db import ada_backend_mock_session, ada_backend_seed_session, test_db
from tests.mocks.cipher import mock_cipher
from tests.mocks.db_service import postgres_service, sample_table_definition
from tests.mocks.llm_service import (
    mock_llm_service,
    mock_llm_service_sequential,
    mock_llm_service_with_tool_calls,
)

# Import prometheus metrics mocks
from tests.mocks.prometheus_metrics import (
    mock_agent_calls,
    mock_get_tracing_span,
    mock_prometheus_metrics,
)

# Import ReAct agent mocks
from tests.mocks.react_agent import (
    agent_input,
    mock_agent,
    mock_tool_description,
    mock_trace_manager,
    react_agent,
    react_agent_sequential,
    react_agent_with_tool_calls,
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
from tests.mocks.utils import timestamp_with_random_suffix


@pytest.fixture(autouse=True)
def disable_observability_in_tests():
    """Disable observability stack for all tests to avoid external dependencies."""
    with patch("settings.settings.ENABLE_OBSERVABILITY_STACK", False):
        yield
