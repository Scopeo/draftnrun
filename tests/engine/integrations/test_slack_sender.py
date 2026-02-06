import uuid
from unittest.mock import patch

import pytest

from engine.components.types import ComponentAttributes
from engine.integrations.slack.slack_sender import SlackSender, SlackSenderInputs
from engine.trace.trace_manager import TraceManager


@pytest.mark.asyncio
async def test_slack_sender_success():
    """Test SlackSender sends message successfully."""

    mock_response = {
        "ok": True,
        "channel": "C01234567",
        "ts": "1234567890.123456",
    }

    with patch("engine.integrations.slack.slack_sender.send_slack_message", return_value=mock_response):
        sender = SlackSender(
            trace_manager=TraceManager(project_name="test"),
            component_attributes=ComponentAttributes(
                component_instance_name="test_slack_sender",
                component_instance_id=uuid.uuid4(),
            ),
            access_token="xoxb-test-token",
        )

        inputs = SlackSenderInputs(
            channel="#general",
            message="Test message",
        )

        result = await sender._run_without_io_trace(inputs, ctx={})

        assert result.status == "Message sent successfully to #general. Timestamp: 1234567890.123456"
        assert result.channel == "C01234567"
        assert result.ts == "1234567890.123456"
        assert result.message == "Test message"


@pytest.mark.asyncio
async def test_slack_sender_with_thread():
    """Test SlackSender sends message to thread successfully."""

    mock_response = {
        "ok": True,
        "channel": "C01234567",
        "ts": "1234567890.999999",
    }

    with patch("engine.integrations.slack.slack_sender.send_slack_message", return_value=mock_response):
        sender = SlackSender(
            trace_manager=TraceManager(project_name="test"),
            component_attributes=ComponentAttributes(
                component_instance_name="test_slack_sender",
                component_instance_id=uuid.uuid4(),
            ),
            access_token="xoxb-test-token",
        )

        inputs = SlackSenderInputs(
            channel="#general",
            message="Thread reply",
            thread_ts="1234567890.123456",
        )

        result = await sender._run_without_io_trace(inputs, ctx={})

        assert "in thread 1234567890.123456" in result.status
        assert result.channel == "C01234567"
        assert result.ts == "1234567890.999999"


@pytest.mark.asyncio
async def test_slack_sender_api_error():
    """Test SlackSender handles Slack API errors."""

    from slack_sdk.errors import SlackApiError

    mock_error = SlackApiError(
        message="channel_not_found",
        response={"error": "channel_not_found"},
    )

    with patch("engine.integrations.slack.slack_sender.send_slack_message", side_effect=mock_error):
        sender = SlackSender(
            trace_manager=TraceManager(project_name="test"),
            component_attributes=ComponentAttributes(
                component_instance_name="test_slack_sender",
                component_instance_id=uuid.uuid4(),
            ),
            access_token="xoxb-test-token",
        )

        inputs = SlackSenderInputs(
            channel="#nonexistent",
            message="Test",
        )

        with pytest.raises(RuntimeError, match="Failed to send Slack message"):
            await sender._run_without_io_trace(inputs, ctx={})


@pytest.mark.asyncio
async def test_slack_sender_calls_api_with_correct_params():
    """Test that SlackSender calls the API with correct parameters."""

    mock_response = {
        "ok": True,
        "channel": "C01234567",
        "ts": "1234567890.123456",
    }

    with patch("engine.integrations.slack.slack_sender.send_slack_message", return_value=mock_response) as mock_send:
        sender = SlackSender(
            trace_manager=TraceManager(project_name="test"),
            component_attributes=ComponentAttributes(
                component_instance_name="test_slack_sender",
                component_instance_id=uuid.uuid4(),
            ),
            access_token="xoxb-test-token",
        )

        inputs = SlackSenderInputs(
            channel="#test-channel",
            message="Hello world",
            thread_ts="1111111111.222222",
        )

        await sender._run_without_io_trace(inputs, ctx={})

        # Verify send_slack_message was called with correct arguments
        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs

        assert call_kwargs["channel"] == "#test-channel"
        assert call_kwargs["text"] == "Hello world"
        assert call_kwargs["thread_ts"] == "1111111111.222222"
        assert call_kwargs["as_markdown"] is True
