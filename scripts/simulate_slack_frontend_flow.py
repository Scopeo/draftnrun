import argparse
import http.server
import json
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Optional

import requests

from ada_backend.scripts.get_supabase_token import get_user_jwt
from settings import get_settings


@dataclass
class OAuthResult:
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    oauth_result: OAuthResult = OAuthResult()

    def do_GET(self):  # noqa: N802 (fast, local script)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            return

        query = urllib.parse.parse_qs(parsed.query)
        OAuthCallbackHandler.oauth_result.code = (query.get("code") or [None])[0]
        OAuthCallbackHandler.oauth_result.state = (query.get("state") or [None])[0]
        OAuthCallbackHandler.oauth_result.error = (query.get("error") or [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h2>Slack OAuth complete.</h2>\n"
            b"<p>You can close this window and return to the terminal.</p></body></html>"
        )

    def log_message(self, format, *args):  # noqa: A003 (suppress noisy logs)
        return


def start_callback_server(host: str, port: int) -> threading.Thread:
    server = http.server.HTTPServer((host, port), OAuthCallbackHandler)

    def _run():
        server.handle_request()  # handle single request then exit

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return t


def build_slack_authorize_url(client_id: str, redirect_uri: str, state: str, scopes: list[str]) -> str:
    base = "https://slack.com/oauth/v2/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        # optional user_scope if you need it
        # "user_scope": "",
        "state": state,
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    resp = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    data = resp.json()
    if not resp.ok or not data.get("ok"):
        raise RuntimeError(f"Slack token exchange failed: {resp.status_code} {data}")
    return data


def put_integration_secret(base_url: str, project_id: str, integration_id: str, jwt: str, payload: dict) -> dict:
    url = f"{base_url}/project/{project_id}/integration/{integration_id}"
    resp = requests.put(
        url, headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}, json=payload, timeout=30
    )
    if not resp.ok:
        raise RuntimeError(f"PUT integration secret failed: {resp.status_code} {resp.text}")
    return resp.json()


def get_project(base_url: str, project_id: str, jwt: str) -> dict:
    url = f"{base_url}/projects/{project_id}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {jwt}"}, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Get project failed: {resp.status_code} {resp.text}")
    return resp.json()


def ensure_redirect_uri_instructions(redirect_uri: str, slack_app_config_url: Optional[str] = None) -> None:
    print("-- Slack App configuration --")
    print("Make sure your Slack App has this Redirect URL added in OAuth & Permissions:")
    print(f"  {redirect_uri}")
    if slack_app_config_url:
        print(f"Admin console link: {slack_app_config_url}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Simulate frontend Slack OAuth flow and register secret")
    parser.add_argument("--project-id", required=True, help="Target project UUID")
    parser.add_argument(
        "--channel",
        default="#slack-bot-test",
        help="Slack channel name or ID (e.g., #general or C123...)",
    )
    parser.add_argument(
        "--backend-url",
        default="http://localhost:8000",
        help="Base URL for the backend",
    )
    parser.add_argument(
        "--redirect-uri",
        default="http://localhost:8765/callback",
        help="Redirect URI for Slack OAuth (must be whitelisted in Slack app)",
    )
    parser.add_argument(
        "--scopes",
        default="chat:write,channels:read,groups:read,im:read,mpim:read",
        help="Comma-separated Slack OAuth scopes",
    )
    parser.add_argument(
        "--integration-id",
        default="a2cc899c-56ef-5ccf-97e5-4250fd915b41",
        help="Slack integration UUID (seeded)",
    )
    args = parser.parse_args()

    settings = get_settings()
    if not settings.SLACK_CLIENT_ID or not settings.SLACK_CLIENT_SECRET:
        raise RuntimeError("SLACK_CLIENT_ID/SLACK_CLIENT_SECRET not configured in credentials.env")
    if not settings.TEST_USER_EMAIL or not settings.TEST_USER_PASSWORD:
        raise RuntimeError("TEST_USER_EMAIL/TEST_USER_PASSWORD not set in credentials.env for Supabase auth")

    # Show redirect URI guidance
    ensure_redirect_uri_instructions(args.redirect_uri)

    # Spin up local callback server
    parsed = urllib.parse.urlparse(args.redirect_uri)
    # Always bind locally; tunnels (e.g., Cloudflare) forward to this local port
    host = "127.0.0.1"
    port = parsed.port or 8765
    start_callback_server(host, port)

    # Build state and authorization URL
    state = f"state-{int(time.time())}"
    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    authorize_url = build_slack_authorize_url(
        client_id=settings.SLACK_CLIENT_ID,
        redirect_uri=args.redirect_uri,
        state=state,
        scopes=scopes,
    )

    print("Opening browser for Slack OAuth…")
    webbrowser.open(authorize_url)

    # Wait for callback (single request)
    print("Waiting for OAuth redirect to be captured at:", args.redirect_uri)
    for _ in range(120):  # up to ~2 minutes
        if OAuthCallbackHandler.oauth_result.code or OAuthCallbackHandler.oauth_result.error:
            break
        time.sleep(1)

    if OAuthCallbackHandler.oauth_result.error:
        raise RuntimeError(f"Slack OAuth error: {OAuthCallbackHandler.oauth_result.error}")
    if not OAuthCallbackHandler.oauth_result.code:
        raise RuntimeError("Timed out waiting for Slack OAuth callback. Ensure redirect URI is configured.")
    if OAuthCallbackHandler.oauth_result.state and OAuthCallbackHandler.oauth_result.state != state:
        raise RuntimeError("State mismatch. Aborting.")

    print("Exchanging authorization code for tokens…")
    token_data = exchange_code_for_tokens(
        code=OAuthCallbackHandler.oauth_result.code,
        client_id=settings.SLACK_CLIENT_ID,
        client_secret=settings.SLACK_CLIENT_SECRET,
        redirect_uri=args.redirect_uri,
    )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")

    print("Obtaining Supabase JWT…")
    jwt = get_user_jwt(settings.TEST_USER_EMAIL, settings.TEST_USER_PASSWORD)

    print("Registering integration secret via backend…")
    registration_payload = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_in": expires_in,
        # token_last_updated optional; backend refresh logic handles it
    }
    secret_resp = put_integration_secret(
        base_url=args.backend_url,
        project_id=args.project_id,
        integration_id=args.integration_id,
        jwt=jwt,
        payload=registration_payload,
    )
    print("Secret registered:", json.dumps(secret_resp, indent=2, default=str))

    print("Fetching project to confirm access…")
    project = get_project(args.backend_url, args.project_id, jwt)
    print("Project:", json.dumps(project, indent=2))

    print()
    print("Next steps to wire Slack Sender in your graph:")
    print("1) In your frontend graph editor, set the Slack Sender component's integration.secret_id to:")
    print(f"   {secret_resp['secret_id']}")
    print("2) Set default_channel to:")
    print(f"   {args.channel}")
    print()
    print("When your graph includes and triggers Slack Sender, it will use the injected secret.")
    print("If you want to test sending immediately, ensure your draft/production graph invokes Slack Sender.")


if __name__ == "__main__":
    main()
