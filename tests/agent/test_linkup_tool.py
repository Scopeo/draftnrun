import pytest
import os
from unittest.mock import MagicMock
import pytest_asyncio
from engine.agent.tools.linkup_tool import (
    LinkupSearchTool,
    LINKUP_TOOL_DESCRIPTION,
)
from engine.agent.types import ComponentAttributes, SourceChunk
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest_asyncio.fixture
async def linkup_tool(mock_trace_manager):
    """Create a Linkup search tool instance."""
    tool = LinkupSearchTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(
            component_instance_name="test_linkup_tool"
        ),
    )
    return tool


@pytest.fixture
def linkup_api_key():
    """Get Linkup API key from environment or skip test if not available."""
    api_key = os.getenv("LINKUP_API_KEY")
    if not api_key:
        pytest.skip("LINKUP_API_KEY environment variable not set")
    return api_key


def test_tool_initialization(linkup_tool):
    """Test that the tool initializes correctly."""
    assert linkup_tool.component_attributes.component_instance_name == "test_linkup_tool"
    assert linkup_tool.tool_description == LINKUP_TOOL_DESCRIPTION
    assert linkup_tool.tool_description.name == "Linkup_Web_Search_Tool"


def test_query_with_params(linkup_tool):
    """Test executing simple query with parameters that returns a response in the right format."""
    query = "Who is the person who won the most Roland Garros titles ?"

    result = linkup_tool.search_results(query=query,
                                        depth="standard",
                                        output_type="sourcedAnswer",
                                        exclude_domains=None,
                                        include_domains=["wikipedia.org"],
                                        from_date='2012-10-10',
                                        to_date='2014-10-10'
                                        )

    assert len(result.response) > 5
    assert isinstance(result.sources[0], SourceChunk)
    assert "Wikipedia" in result.sources[0].name
    assert result.is_successful
