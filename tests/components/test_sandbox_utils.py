from unittest.mock import AsyncMock, Mock, patch

import pytest

from engine.components.tools.sandbox_utils import get_or_create_sandbox


@pytest.mark.asyncio
@patch("engine.components.tools.sandbox_utils.AsyncSandbox")
@patch("engine.components.tools.sandbox_utils.get_tracing_span")
async def test_get_or_create_sandbox_replaces_shared_sandbox_with_closed_event_loop(
    mock_get_tracing_span, mock_sandbox_class
):
    stale_sandbox = AsyncMock()
    stale_sandbox.is_running.side_effect = RuntimeError("Event loop is closed")
    stale_sandbox.kill.side_effect = RuntimeError("Event loop is closed")
    new_sandbox = AsyncMock()
    params = Mock(shared_sandbox=stale_sandbox)
    mock_get_tracing_span.return_value = params
    mock_sandbox_class.create = AsyncMock(return_value=new_sandbox)

    sandbox, should_cleanup_locally = await get_or_create_sandbox("test_api_key")

    assert sandbox is new_sandbox
    assert should_cleanup_locally is False
    assert params.shared_sandbox is new_sandbox
    stale_sandbox.is_running.assert_awaited_once()
    stale_sandbox.kill.assert_awaited_once()
    mock_sandbox_class.create.assert_awaited_once_with(api_key="test_api_key")
