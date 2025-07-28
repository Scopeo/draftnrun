#!/usr/bin/env python3
"""
Simple test script for Slack integration
Tests the SlackSender component directly
"""

import asyncio
from uuid import uuid4
from typing import Dict, Any

from engine.agent.agent import AgentPayload, ChatMessage, ComponentAttributes
from engine.integrations.slack_sender import SlackSender
from engine.trace.trace_manager import TraceManager
from settings import settings


async def test_slack_integration():
    """Test the Slack integration directly"""

    print("🚀 Testing Slack Integration")
    print("=" * 50)

    # Check if SLACK_BOT_TOKEN is configured
    if not settings.SLACK_BOT_TOKEN:
        print("❌ SLACK_BOT_TOKEN not configured in settings")
        print("   Please add your Slack bot token to credentials.env")
        return

    print(f"✅ SLACK_BOT_TOKEN configured: {settings.SLACK_BOT_TOKEN[:10]}...")

    # Create trace manager
    trace_manager = TraceManager(project_name="slack-test")

    # Create component attributes
    component_attributes = ComponentAttributes(
        component_instance_name="test_slack_sender", component_instance_id=uuid4()
    )

    # Create the Slack sender component
    slack_sender = SlackSender(
        trace_manager=trace_manager,
        component_attributes=component_attributes,
        bot_token=settings.SLACK_BOT_TOKEN,
        default_channel="slack-bot-test",
    )

    # Test message
    test_message = "Hello from the test script! 🚀"

    print(f"📤 Sending test message to channel: slack-bot-test")
    print(f"📝 Message: {test_message}")

    try:
        # Test the Slack sender directly
        result = await slack_sender._run_without_trace(message=test_message)

        print("✅ Slack message sent successfully!")
        print(f"📥 Result: {result}")

        if hasattr(result, "messages") and result.messages:
            print(f"💬 Response: {result.messages[0].content}")

    except Exception as e:
        print(f"❌ Error sending Slack message: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_slack_integration())
