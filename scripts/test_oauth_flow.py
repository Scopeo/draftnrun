#!/usr/bin/env python3
"""
Test OAuth flow headless (without Connect UI).

Usage:
    uv run python -m scripts.test_oauth_flow --project-id <uuid> --provider slack
"""

import argparse
import asyncio
import sys
import time
import webbrowser

import httpx
from dotenv import load_dotenv

from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import settings


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


async def test_oauth_flow_headless(project_id: str, provider: str):
    """Test OAuth flow using headless endpoint."""

    backend_url = "http://localhost:8000"

    print_header("OAuth Flow Test (Headless)")
    print_info(f"Provider: {provider}")
    print_info(f"Project ID: {project_id}")

    # Step 0: Authenticate
    print_header("Step 0: Authenticate with Supabase")
    try:
        auth_token = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)
        print_success("Authentication successful")
    except Exception as e:
        print_error(f"Failed to authenticate: {e}")
        return False

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }

    # Step 1: Get OAuth URL (headless)
    print_header("Step 1: Get OAuth URL (Headless)")
    print_info("Calling POST /projects/{project_id}/oauth-connections/authorize...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{backend_url}/projects/{project_id}/oauth-connections/authorize",
                json={
                    "provider_config_key": provider,
                    "end_user_email": f"test-{provider}@draftnrun.com",
                    "name": f"Test {provider.capitalize()} Connection",
                },
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            oauth_url = data.get("oauth_url")
            end_user_id = data.get("end_user_id")

            if not oauth_url:
                print_error("No oauth_url in response")
                return False

            print_success("OAuth URL generated successfully")
            print_info(f"End User ID: {end_user_id}")
            print_info(f"OAuth URL: {oauth_url}")

        except httpx.HTTPStatusError as e:
            print_error(f"HTTP {e.response.status_code}: {e.response.text}")
            return False
        except Exception as e:
            print_error(f"Failed to get OAuth URL: {e}")
            return False

    # Step 2: Open browser and wait
    print_header("Step 2: Complete OAuth in Browser")
    print_info("Opening browser...")

    try:
        webbrowser.open(oauth_url)
        print_success("Browser opened")
    except Exception as e:
        print_error(f"Failed to open browser: {e}")
        print_info(f"Please open this URL manually: {oauth_url}")

    print_info(f"You will be redirected directly to {provider.capitalize()} (no Nango UI)")
    print_info(f"After authorizing, {provider.capitalize()} will redirect back to Nango")
    print_info("You should see a success message from Nango")
    input("\nPress ENTER after you've completed the OAuth flow...")

    # Wait a bit for Nango to process
    print_info("Waiting for provider to process callback...")
    time.sleep(2)

    # Step 3: Confirm connection
    print_header("Step 3: Confirm Connection")
    print_info("Calling POST /projects/{project_id}/oauth-connections...")

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{backend_url}/projects/{project_id}/oauth-connections",
                json={
                    "provider_config_key": provider,
                    "name": f"Test {provider.capitalize()} Connection",
                },
                headers=headers,
            )
            response.raise_for_status()
            result = response.json()

            connection_id = result.get("connection_id")
            if not connection_id:
                print_error("No connection_id in response")
                return False

            print_success("✨ OAuth flow completed successfully!")
            print_info(f"OAuth Connection ID: {connection_id}")

            print_header("✅ Test Complete")
            print_success(f"Successfully set up {provider.upper()} OAuth integration (Headless)")
            print_info("Next steps:")
            print_info(f"  1. Use connection_id={connection_id} to get access tokens")
            print_info("  2. Test token retrieval with test_oauth_token_usage.py")

            return True

        except httpx.HTTPStatusError as e:
            print_error(f"HTTP {e.response.status_code}: {e.response.text}")
            print_info("Connection not found. OAuth may not have completed.")
            print_info("Common causes:")
            print_info("  - OAuth flow was not completed in browser")
            print_info("  - NANGO_SERVER_URL not set correctly in docker-compose")
            print_info("  - Redirect URL incorrect in provider app settings")
            return False
        except Exception as e:
            print_error(f"Failed to confirm connection: {e}")
            return False


def main():
    """Main entry point."""
    load_dotenv("credentials.env")

    parser = argparse.ArgumentParser(description="Test OAuth flow headless")
    parser.add_argument("--project-id", required=True, help="Project UUID")
    parser.add_argument("--provider", default="slack", help="Provider key (slack, hubspot, etc)")

    args = parser.parse_args()

    print_header("Headless OAuth Test")
    print_info("This test uses the headless OAuth flow (no Connect UI)")
    print_info("Make sure:")
    print_info("  1. Backend running on localhost:8000")
    print_info("  2. Nango running on localhost:3003")
    print_info("  3. ngrok exposing port 3003")
    print_info("  4. Provider app redirect URL configured with ngrok URL")

    success = asyncio.run(test_oauth_flow_headless(args.project_id, args.provider))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
