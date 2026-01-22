#!/usr/bin/env python3
"""
Test OAuth token retrieval and usage (MVP Infrastructure Test).

This script validates that:
1. OAuth tokens are correctly stored in the database
2. Tokens can be decrypted and retrieved
3. Tokens work against the provider's API

Usage:
    uv run python -m scripts.test_oauth_token_usage \
        --connection-id <uuid> \
        --provider slack
"""

import argparse
import asyncio
import sys
from uuid import UUID

import httpx
from dotenv import load_dotenv

from ada_backend.database.setup_db import get_db_session
from ada_backend.services.integration_service import get_oauth_access_token


def print_header(text: str):
    """Print section header."""
    print(f"\n{'=' * 60}")
    print(f"  {text}")
    print(f"{'=' * 60}\n")


def print_success(text: str):
    """Print success message."""
    print(f"✅ {text}")


def print_error(text: str):
    """Print error message."""
    print(f"❌ {text}")


def print_info(text: str):
    """Print info message."""
    print(f"ℹ️  {text}")


async def test_slack_token(access_token: str) -> bool:
    """Test Slack token with auth.test API."""
    print_header("Testing Slack API Connectivity")
    print_info("Calling Slack auth.test endpoint...")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            data = response.json()

            if data.get("ok"):
                print_success("Slack authentication successful!")
                print_info(f"  User: {data.get('user')}")
                print_info(f"  Team: {data.get('team')}")
                print_info(f"  Team ID: {data.get('team_id')}")
                print_info(f"  User ID: {data.get('user_id')}")
                return True
            else:
                print_error(f"Slack authentication failed: {data.get('error')}")
                return False

    except httpx.HTTPError as e:
        print_error(f"HTTP error: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


async def test_hubspot_token(access_token: str) -> bool:
    """Test HubSpot token with access token info API."""
    print_header("Testing HubSpot API Connectivity")
    print_info("Calling HubSpot access token info endpoint...")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get("https://api.hubapi.com/oauth/v1/access-tokens/" + access_token)
            response.raise_for_status()
            data = response.json()

            print_success("HubSpot authentication successful!")
            print_info(f"  Hub ID: {data.get('hub_id')}")
            print_info(f"  User: {data.get('user')}")
            print_info(f"  Scopes: {', '.join(data.get('scopes', []))}")
            return True

    except httpx.HTTPError as e:
        print_error(f"HTTP error: {e}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        return False


async def test_token_usage(oauth_connection_id: str, provider: str):
    """Test OAuth token retrieval and usage."""

    print_header("OAuth Token Usage Test (MVP Infrastructure)")
    print_info(f"Provider: {provider}")
    print_info(f"OAuth Connection ID: {oauth_connection_id}")

    # Step 1: Retrieve token from database
    print_header("Step 1: Retrieve Access Token")
    print_info("Fetching token from database via integration_service...")

    try:
        with get_db_session() as session:
            access_token = await get_oauth_access_token(
                session=session, oauth_connection_id=UUID(oauth_connection_id), provider_config_key=provider
            )

        print_success("Token retrieved and decrypted successfully!")
        print_info(f"Token preview: {access_token[:20]}...{access_token[-10:]}")

    except Exception as e:
        print_error(f"Failed to retrieve token: {e}")
        return False

    # Step 2: Test token against provider API
    if provider == "slack":
        success = await test_slack_token(access_token)
    elif provider == "hubspot":
        success = await test_hubspot_token(access_token)
    else:
        print_error(f"Provider '{provider}' not supported for testing yet")
        print_info("Token was retrieved successfully, but cannot validate against API")
        return False

    # Final result
    if success:
        print_header("✅ Test Complete")
        print_success(f"OAuth infrastructure is working correctly for {provider.upper()}!")
        print_info("The token:")
        print_info("  1. Was correctly stored in the database")
        print_info("  2. Can be decrypted and retrieved")
        print_info("  3. Works against the provider's API")
        print_info("")
        print_info("🎉 MVP Infrastructure is ready!")
        return True
    else:
        print_header("❌ Test Failed")
        print_error("Token validation against provider API failed")
        return False


def main():
    """Main entry point."""
    load_dotenv("credentials.env")

    parser = argparse.ArgumentParser(description="Test OAuth token retrieval and usage")
    parser.add_argument("--connection-id", required=True, help="OAuth Connection UUID")
    parser.add_argument("--provider", required=True, choices=["slack", "hubspot"], help="Provider key")

    args = parser.parse_args()

    print_header("OAuth Infrastructure Test")
    print_info("This script tests the OAuth infrastructure")
    print_info("It validates that tokens are stored and can be used correctly")

    success = asyncio.run(test_token_usage(args.connection_id, args.provider))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
