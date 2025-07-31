#!/usr/bin/env python3
"""
Simple test script to send a real message to slack-bot-test channel.
This script will be deleted after testing.
"""

import os
import asyncio
import logging
from uuid import uuid4
from dotenv import load_dotenv

# Load environment variables from credentials.env
load_dotenv("credentials.env")

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_real_slack_message():
    """Test sending a real message to slack-bot-test channel."""
    logger.info("🚀 Testing real Slack message to slack-bot-test channel...")

    # Check if bot token is available
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    if not bot_token:
        logger.error("❌ SLACK_BOT_TOKEN environment variable not set")
        logger.info("Please set SLACK_BOT_TOKEN in your credentials.env file")
        return

    logger.info("✅ Bot token found")

    try:
        # Import the actual SlackSender
        from engine.integrations.slack_sender import SlackSender
        from engine.agent.agent import ComponentAttributes
        from engine.trace.trace_manager import TraceManager

        # Create a mock trace manager and component attributes for testing
        mock_trace_manager = TraceManager(project_name="slack-test")
        mock_component_attributes = ComponentAttributes(component_instance_name="slack-sender-test")

        # Create a temporary integration secret in the database
        from ada_backend.database.setup_db import get_db
        from ada_backend.repositories.integration_repository import create_integration_secret

        session = next(get_db())

        # Create a test integration secret with the bot token
        integration_secret_id = str(uuid4())
        create_integration_secret(
            session=session,
            integration_secret_id=integration_secret_id,
            access_token=bot_token,
            refresh_token=None,  # Bot tokens don't need refresh
            expires_in=None,  # Bot tokens don't expire
        )

        logger.info(f"✅ Created test integration secret: {integration_secret_id}")

        # Create SlackSender instance
        slack_sender = SlackSender(
            trace_manager=mock_trace_manager,
            component_attributes=mock_component_attributes,
            secret_integration_id=integration_secret_id,
            default_channel="slack-bot-test",
        )

        logger.info("✅ SlackSender created successfully")

        # Send a test message
        result = await slack_sender._run_without_trace(
            channel="slack-bot-test",
            message="🧪 Test message from bot token integration! This is a real message sent via the new bot token approach.",
        )

        logger.info("✅ Message sent successfully!")
        logger.info(f"Result: {result}")

        # Clean up - delete the test integration secret
        from ada_backend.repositories.integration_repository import delete_integration_secret

        delete_integration_secret(session, integration_secret_id)
        logger.info(f"✅ Cleaned up test integration secret: {integration_secret_id}")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(test_real_slack_message())
