#!/usr/bin/env python3
"""
Test script for Slack OAuth integration
Tests both the old bot token approach and the new OAuth approach
"""

import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from typing import Dict, Any

from engine.agent.agent import AgentPayload, ChatMessage, ComponentAttributes
from engine.integrations.slack_sender import SlackSender
from engine.trace.trace_manager import TraceManager
from ada_backend.database.setup_db import get_db
from ada_backend.database.models import SecretIntegration
from ada_backend.repositories.integration_repository import insert_secret_integration
from ada_backend.database.seed.integrations.seed_integration import INTEGRATION_UUIDS
from settings import settings


async def test_slack_oauth_integration():
    """Test the Slack OAuth integration"""

    print("🚀 Testing Slack OAuth Integration")
    print("=" * 50)

    # Check if OAuth credentials are configured
    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        print("❌ SLACK_CLIENT_ID or SLACK_CLIENT_SECRET not configured")
        print("   Please add your Slack OAuth credentials to credentials.env")
        return

    print(f"✅ SLACK_CLIENT_ID configured: {settings.SLACK_CLIENT_ID}")
    print(f"✅ SLACK_CLIENT_SECRET configured: {settings.SLACK_CLIENT_SECRET[:10]}...")

    # Create trace manager
    trace_manager = TraceManager(project_name="slack-oauth-test")

    # Create component attributes
    component_attributes = ComponentAttributes(
        component_instance_name="test_slack_oauth_sender", component_instance_id=uuid4()
    )

    # Step 1: Create a test secret integration in the database
    print("\n📝 Step 1: Creating test secret integration...")

    session = next(get_db())

    # Create a test secret integration using the existing bot token
    # In a real scenario, this would come from OAuth flow
    test_secret_integration = insert_secret_integration(
        session=session,
        integration_id=INTEGRATION_UUIDS["slack_sender"],  # Use the actual Slack integration UUID
        access_token=settings.SLACK_BOT_TOKEN,  # Using existing bot token for testing
        refresh_token="test_refresh_token",  # Placeholder for testing
        expires_in=3600,  # 1 hour
        token_last_updated=datetime.now(timezone.utc),
    )

    secret_integration_id = str(test_secret_integration.id)
    print(f"✅ Created secret integration with ID: {secret_integration_id}")

    # Step 2: Test the OAuth-based Slack sender
    print("\n📤 Step 2: Testing OAuth-based Slack sender...")

    try:
        # Create the Slack sender component with OAuth approach
        slack_sender = SlackSender(
            trace_manager=trace_manager,
            component_attributes=component_attributes,
            secret_integration_id=secret_integration_id,
            default_channel="slack-bot-test",
        )

        # Test message
        test_message = f"Hello from OAuth integration test! 🚀 (Time: {datetime.now().strftime('%H:%M:%S')})"

        print(f"📤 Sending test message to channel: slack-bot-test")
        print(f"📝 Message: {test_message}")

        # Test the Slack sender
        result = await slack_sender._run_without_trace(message=test_message)

        print("✅ OAuth-based Slack message sent successfully!")
        print(f"📥 Result: {result}")

        if hasattr(result, "messages") and result.messages:
            print(f"💬 Response: {result.messages[0].content}")

    except Exception as e:
        print(f"❌ Error with OAuth-based Slack sender: {e}")
        import traceback

        traceback.print_exc()

    finally:
        # Clean up: Remove the test secret integration
        print("\n🧹 Cleaning up test data...")
        try:
            session.delete(test_secret_integration)
            session.commit()
            print("✅ Test secret integration removed")
        except Exception as e:
            print(f"⚠️  Warning: Could not clean up test data: {e}")
        finally:
            session.close()


if __name__ == "__main__":
    asyncio.run(test_slack_oauth_integration())
