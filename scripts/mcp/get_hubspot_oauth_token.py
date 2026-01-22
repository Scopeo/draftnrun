"""
Script to obtain HubSpot OAuth access_token.

This script supports two modes:
1. Exchange OAuth code for tokens (initial setup)
2. Refresh access token using refresh_token (recommended for repeated use)

Usage:
    # Mode 1 - Initial OAuth flow (use credentials from settings/.env):
    uv run python scripts/mcp/get_hubspot_oauth_token.py

    # Mode 1 - Override with arguments:
    uv run python scripts/mcp/get_hubspot_oauth_token.py --client-secret other_secret

    # Mode 1 - Pass code directly:
    uv run python scripts/mcp/get_hubspot_oauth_token.py --code abc123

    # Mode 2 - Refresh token (RECOMMENDED - no browser needed):
    uv run python scripts/mcp/get_hubspot_oauth_token.py --refresh-token YOUR_REFRESH_TOKEN

    # Mode 2 - Use refresh token from .env:
    export HUBSPOT_MCP_REFRESH_TOKEN=your_refresh_token
    uv run python scripts/mcp/get_hubspot_oauth_token.py --refresh

Mode 1 flow:
1. Shows the Install URL to open in your browser
2. Waits for you to paste the 'code' from the redirect URL
3. Exchanges the code for access_token and refresh_token
4. Shows the obtained tokens

Mode 2 flow (faster):
1. Uses existing refresh_token (from .env or argument)
2. Requests a new access_token
3. Shows the new access_token (refresh_token stays the same)
"""

import argparse
import asyncio
import sys
from urllib.parse import parse_qs, urlparse

import httpx

from settings import settings

# Default redirect URI for OAuth callback (using port 9999 to avoid conflicts)
DEFAULT_REDIRECT_URI = "http://localhost:9999/oauth-callback"


def build_install_url(client_id: str, redirect_uri: str = DEFAULT_REDIRECT_URI) -> str:
    """Build the Install URL for the HubSpot app."""
    base_url = "https://app-eu1.hubspot.com/oauth/authorize/user"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
    }
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"{base_url}?{query_string}"


def extract_code_from_url(redirect_url: str) -> str | None:
    """Extract the 'code' from an OAuth redirect URL."""
    parsed = urlparse(redirect_url)
    query_params = parse_qs(parsed.query)
    code = query_params.get("code")
    if code:
        return code[0]  # parse_qs returns a list
    return None


async def exchange_code_for_token(
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> dict:
    """Exchange OAuth code for access_token and refresh_token."""
    token_url = "https://api.hubapi.com/oauth/v1/token"

    data = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "code": code,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        response.raise_for_status()
        return response.json()


async def refresh_access_token(
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    """Refresh access_token using refresh_token."""
    token_url = "https://api.hubapi.com/oauth/v1/token"

    data = {
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data)
        response.raise_for_status()
        return response.json()


def main():
    # Read default credentials from settings
    parser = argparse.ArgumentParser(
        description="Obtain HubSpot OAuth access_token for MCP server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples (Mode 1 - Initial OAuth flow):
  # Use credentials from settings/.env:
  uv run python scripts/mcp/get_hubspot_oauth_token.py

  # Override with arguments:
  uv run python scripts/mcp/get_hubspot_oauth_token.py --client-secret other_secret

  # Pass code directly:
  uv run python scripts/mcp/get_hubspot_oauth_token.py --code abc123

Examples (Mode 2 - Refresh token - RECOMMENDED):
  # Use refresh token from .env (fastest):
  uv run python scripts/mcp/get_hubspot_oauth_token.py --refresh

  # Pass refresh token directly:
  uv run python scripts/mcp/get_hubspot_oauth_token.py --refresh-token YOUR_REFRESH_TOKEN
        """,
    )
    parser.add_argument(
        "--client-id",
        default=settings.HUBSPOT_MCP_CLIENT_ID,
        help="HubSpot app Client ID (default: from settings HUBSPOT_MCP_CLIENT_ID)",
    )
    parser.add_argument(
        "--client-secret",
        default=settings.HUBSPOT_MCP_CLIENT_SECRET,
        required=not bool(settings.HUBSPOT_MCP_CLIENT_SECRET),
        help="HubSpot app Client Secret (default: from settings HUBSPOT_MCP_CLIENT_SECRET)",
    )
    parser.add_argument(
        "--redirect-uri",
        default=DEFAULT_REDIRECT_URI,
        help=f"Redirect URI configured in the app (default: {DEFAULT_REDIRECT_URI})",
    )
    parser.add_argument(
        "--code",
        help="OAuth code directly (optional, if not provided, script will prompt for it)",
    )
    parser.add_argument(
        "--url",
        help="Full redirect URL with code (optional, script will extract the code)",
    )
    parser.add_argument(
        "--refresh-token",
        default=settings.HUBSPOT_MCP_REFRESH_TOKEN if hasattr(settings, "HUBSPOT_MCP_REFRESH_TOKEN") else None,
        help="Refresh token to obtain new access_token (default: from settings HUBSPOT_MCP_REFRESH_TOKEN)",
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Use refresh_token from settings/.env to get new access_token (shortcut for --refresh-token from env)",
    )

    args = parser.parse_args()

    if not args.client_id:
        print("❌ Error: --client-id is required")
        print("   Configure it in credentials.env as HUBSPOT_MCP_CLIENT_ID")
        print("   or pass it as argument: --client-id YOUR_CLIENT_ID")
        sys.exit(1)

    if not args.client_secret:
        print("❌ Error: --client-secret is required")
        print("   Configure it in credentials.env as HUBSPOT_MCP_CLIENT_SECRET")
        print("   or pass it as argument: --client-secret YOUR_SECRET")
        sys.exit(1)

    # MODE 2: Refresh token flow (faster, no browser needed)
    if args.refresh or args.refresh_token:
        refresh_token = args.refresh_token
        if not refresh_token:
            print("❌ Error: --refresh-token is required when using --refresh")
            print("   Configure it in credentials.env as HUBSPOT_MCP_REFRESH_TOKEN")
            print("   or pass it as argument: --refresh-token YOUR_REFRESH_TOKEN")
            sys.exit(1)

        print("\n🔄 Refreshing access_token using refresh_token...")
        try:
            result = asyncio.run(
                refresh_access_token(
                    client_id=args.client_id,
                    client_secret=args.client_secret,
                    refresh_token=refresh_token,
                )
            )

            access_token = result.get("access_token")
            expires_in = result.get("expires_in")

            print("\n" + "=" * 80)
            print("✅ Access token refreshed successfully!")
            print("=" * 80)
            print("\n📝 New Access Token:")
            print(f"   {access_token}")
            print(f"\n⏰ Expires in: {expires_in} seconds ({expires_in // 3600 if expires_in else 'N/A'} hours)")
            print("\n" + "=" * 80)
            print("\n💾 Update your credentials.env:")
            print(f"   HUBSPOT_MCP_ACCESS_TOKEN={access_token}")
            print("\n💡 Your refresh token stays the same (no need to update it)")
            print("\n" + "=" * 80)
            return

        except httpx.HTTPStatusError as e:
            print(f"\n❌ HTTP Error: {e.response.status_code}")
            print(f"   Response: {e.response.text}")
            print("\n💡 Tip: Your refresh_token might be expired or invalid.")
            print("   Run the script without --refresh to get a new refresh_token")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error: {e}")
            sys.exit(1)

    # MODE 1: OAuth code flow (initial setup, requires browser)
    install_url = build_install_url(args.client_id, args.redirect_uri)
    print("\n" + "=" * 80)
    print("📋 STEP 1: Install the app using this URL:")
    print("=" * 80)
    print(f"\n{install_url}\n")
    print("=" * 80)
    print("\n💡 Instructions:")
    print("   1. Open the URL above in your browser")
    print("   2. Accept the app scopes")
    print("   3. HubSpot will try to redirect to localhost:3000 (will fail, that's normal)")
    print("   4. Copy the full error/redirect URL that has the 'code=' parameter")
    print("   5. Paste it below or use --url or --code\n")

    # Get code
    code = args.code

    if not code and args.url:
        code = extract_code_from_url(args.url)
        if not code:
            print("❌ Error: Could not extract 'code' from the provided URL")
            sys.exit(1)

    if not code:
        print("Paste the full redirect URL here (or just the code):")
        user_input = input("> ").strip()

        # Try to extract code from URL if it looks like a URL
        if user_input.startswith("http"):
            code = extract_code_from_url(user_input)
            if not code:
                print("❌ Error: Could not find 'code' in the URL")
                sys.exit(1)
        else:
            code = user_input

    if not code:
        print("❌ Error: Code is required")
        sys.exit(1)

    # Exchange code for token
    print("\n🔄 Exchanging code for access_token...")
    try:
        result = asyncio.run(
            exchange_code_for_token(
                client_id=args.client_id,
                client_secret=args.client_secret,
                code=code,
                redirect_uri=args.redirect_uri,
            )
        )

        access_token = result.get("access_token")
        refresh_token = result.get("refresh_token")
        expires_in = result.get("expires_in")

        print("\n" + "=" * 80)
        print("✅ Tokens obtained successfully!")
        print("=" * 80)
        print("\n📝 Access Token:")
        print(f"   {access_token}")
        print("\n🔄 Refresh Token:")
        print(f"   {refresh_token}")
        print(f"\n⏰ Expires in: {expires_in} seconds ({expires_in // 3600 if expires_in else 'N/A'} hours)")
        print("\n" + "=" * 80)
        print("\n💾 Add these to your credentials.env:")
        print(f"   HUBSPOT_MCP_ACCESS_TOKEN={access_token}")
        if refresh_token:
            print(f"   HUBSPOT_MCP_REFRESH_TOKEN={refresh_token}")
        print("\n" + "=" * 80)

    except httpx.HTTPStatusError as e:
        print(f"\n❌ HTTP Error: {e.response.status_code}")
        print(f"   Response: {e.response.text}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
