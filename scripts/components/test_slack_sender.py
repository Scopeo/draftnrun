#!/usr/bin/env python3
"""
Test SlackSender component with a provided access token.

Usage:
    uv run python -m scripts.test_slack_sender \
        --access-token "xoxb-your-token-here" \
        --channel "#general" \
        --message "Test message!"
"""

import argparse
import asyncio
import uuid

from dotenv import load_dotenv

from engine.components.types import ComponentAttributes
from engine.integrations.slack.slack_sender import SlackSender, SlackSenderInputs
from engine.trace.trace_context import set_trace_manager
from engine.trace.trace_manager import TraceManager

DEFAULT_TEST_CHANNEL = "#slack-bot-test"


async def test_slack_sender(access_token: str, channel: str, message: str, thread_ts: str | None = None):
    """Test SlackSender component with direct access token."""

    print("Testing SlackSender...")
    print(f"  Channel: {channel}")
    print(f"  Message: {message}")
    if thread_ts:
        print(f"  Thread: {thread_ts}")

    set_trace_manager(TraceManager(project_name="test-slack-sender"))

    sender = SlackSender(
        trace_manager=TraceManager(project_name="test-slack-sender"),
        component_attributes=ComponentAttributes(
            component_instance_name="test_slack_sender", component_instance_id=uuid.uuid4()
        ),
        access_token=access_token,
    )

    print("✅ SlackSender initialized")

    inputs = SlackSenderInputs(
        channel=channel,
        message=message,
        thread_ts=thread_ts,
    )

    result = await sender._run_without_io_trace(inputs, ctx={})

    print("✅ Message sent!")
    print(f"  Status: {result.status}")
    print(f"  Channel: {result.channel}")
    print(f"  Timestamp: {result.ts}")

    return True


def main():
    load_dotenv("credentials.env")

    parser = argparse.ArgumentParser(description="Test Slack Sender component")
    parser.add_argument("--access-token", required=True, help="Slack OAuth access token (xoxb-...)")
    parser.add_argument(
        "--channel",
        required=False,
        help="Slack channel (e.g., #general or C01234567)",
        default=DEFAULT_TEST_CHANNEL,
    )
    parser.add_argument("--message", required=True, help="Message to send")
    parser.add_argument("--thread-ts", default=None, help="Thread timestamp for reply (optional)")

    args = parser.parse_args()

    asyncio.run(
        test_slack_sender(
            args.access_token,
            args.channel,
            args.message,
            args.thread_ts,
        )
    )


if __name__ == "__main__":
    main()
