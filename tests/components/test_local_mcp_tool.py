from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from engine.components.tools.mcp.local_mcp_tool import LocalMCPTool
from engine.components.types import ComponentAttributes, ToolDescription
from engine.trace.trace_manager import TraceManager


@pytest.fixture
def mock_trace_manager():
    return MagicMock(spec=TraceManager)


@pytest.fixture
def component_attributes():
    return ComponentAttributes(component_instance_name="local-mcp-test")


@pytest.fixture
def tool_description():
    return ToolDescription(
        name="test_tool",
        description="Test tool",
        tool_properties={},
        required_tool_properties=[],
    )


@pytest.fixture
def local_mcp_tool(mock_trace_manager, component_attributes, tool_description):
    return LocalMCPTool(
        trace_manager=mock_trace_manager,
        component_attributes=component_attributes,
        command="echo",
        tool_descriptions=[tool_description],
    )


@pytest.mark.asyncio
async def test_close_cleans_up_resources(local_mcp_tool):
    """Test that close() properly exits both session and stdio context managers."""
    # Mock the internal session and context
    mock_session = AsyncMock()
    mock_stdio_context = AsyncMock()

    local_mcp_tool._session = mock_session
    local_mcp_tool._stdio_context = mock_stdio_context

    await local_mcp_tool.close()

    # Verify both context managers were exited
    mock_session.__aexit__.assert_called_once_with(None, None, None)
    mock_stdio_context.__aexit__.assert_called_once_with(None, None, None)

    # Verify references were cleared
    assert local_mcp_tool._session is None
    assert local_mcp_tool._stdio_context is None


@pytest.mark.asyncio
async def test_close_is_idempotent(local_mcp_tool):
    """Test that calling close() multiple times is safe."""
    mock_session = AsyncMock()
    mock_stdio_context = AsyncMock()

    local_mcp_tool._session = mock_session
    local_mcp_tool._stdio_context = mock_stdio_context

    # First close
    await local_mcp_tool.close()

    # Second close
    await local_mcp_tool.close()

    # Context managers should still only be called once
    mock_session.__aexit__.assert_called_once()
    mock_stdio_context.__aexit__.assert_called_once()


@pytest.mark.asyncio
async def test_close_handles_session_error(local_mcp_tool):
    """Test that close() handles errors during session exit and still cleans up stdio."""
    mock_session = AsyncMock()
    mock_session.__aexit__.side_effect = RuntimeError("Session error")

    mock_stdio_context = AsyncMock()

    local_mcp_tool._session = mock_session
    local_mcp_tool._stdio_context = mock_stdio_context

    # Should not raise exception (caught and logged)
    await local_mcp_tool.close()

    # Stdio context should still be closed even if session failed
    mock_stdio_context.__aexit__.assert_called_once()

    # References should still be cleared
    assert local_mcp_tool._session is None
    assert local_mcp_tool._stdio_context is None


@pytest.mark.asyncio
async def test_close_handles_stdio_error(local_mcp_tool):
    """Test that close() handles errors during stdio exit."""
    mock_session = AsyncMock()

    mock_stdio_context = AsyncMock()
    mock_stdio_context.__aexit__.side_effect = RuntimeError("Stdio error")

    local_mcp_tool._session = mock_session
    local_mcp_tool._stdio_context = mock_stdio_context

    # Should not raise exception
    await local_mcp_tool.close()

    mock_session.__aexit__.assert_called_once()
    mock_stdio_context.__aexit__.assert_called_once()

    assert local_mcp_tool._session is None
    assert local_mcp_tool._stdio_context is None


@pytest.mark.asyncio
async def test_context_manager_calls_close(local_mcp_tool):
    """Test that using the component as a context manager calls close()."""
    # Mock _ensure_session to avoid actual subprocess creation
    with patch.object(LocalMCPTool, "_ensure_session", new_callable=AsyncMock) as mock_ensure:
        # Mock close to verify it's called
        with patch.object(LocalMCPTool, "close", new_callable=AsyncMock) as mock_close:
            async with local_mcp_tool:
                pass

            mock_ensure.assert_called_once()
            mock_close.assert_called_once()
