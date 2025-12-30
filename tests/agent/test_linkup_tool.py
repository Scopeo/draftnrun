import os
import asyncio
import pytest
from unittest.mock import MagicMock

from engine.agent.tools.linkup_tool import (
    LinkupDepth,
    LinkupSearchTool,
    LINKUP_TOOL_DESCRIPTION,
    LinkupSearchToolInputs,
    LinkupSearchToolOutputs,
)
from engine.agent.types import ComponentAttributes, SourceChunk
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def linkup_api_key():
    """Get Linkup API key in environment or skip test if not available."""
    api_key = os.getenv("LINKUP_API_KEY")
    if not api_key:
        pytest.skip("LINKUP_API_KEY environment variable not set")
    return api_key


@pytest.fixture
def linkup_tool(mock_trace_manager, linkup_api_key):
    """Create a Linkup search tool instance."""
    tool = LinkupSearchTool(
        trace_manager=mock_trace_manager,
        component_attributes=ComponentAttributes(component_instance_name="test_linkup_tool"),
        linkup_api_key=linkup_api_key,
    )
    return tool


def test_tool_initialization(linkup_tool):
    """Test that the tool initializes correctly."""
    assert linkup_tool.component_attributes.component_instance_name == "test_linkup_tool"
    assert linkup_tool.tool_description == LINKUP_TOOL_DESCRIPTION
    assert linkup_tool.tool_description.name == "Linkup_Web_Search_Tool"


def test_query_with_params(linkup_tool, linkup_api_key):
    """Test executing simple query that returns a response in the right format."""
    query = "Who is the person who won the most Roland Garros titles ?"

    inputs = LinkupSearchToolInputs(
        query=query,
        depth=LinkupDepth.STANDARD,
        include_domains=["wikipedia.org"],
        from_date="2012-10-10",
        to_date="2014-10-10",
    )

    result = asyncio.run(linkup_tool._run_without_io_trace(inputs=inputs, ctx={}))

    assert isinstance(result, LinkupSearchToolOutputs)

    output = result.output
    sources = result.sources

    assert len(output) > 5
    assert isinstance(sources[0], SourceChunk)
    assert "Wikipedia" in sources[0].name
