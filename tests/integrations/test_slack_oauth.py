import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from uuid import UUID
import requests

from engine.integrations.utils import (
    get_slack_client,
    refresh_slack_oauth_token,
    get_slack_oauth_access_token,
    needs_new_token,
)
from ada_backend.database import models as db


class TestSlackOAuthUtils:
    """Test suite for Slack OAuth utility functions."""

    def test_get_slack_client(self):
        """Test creating Slack WebClient with access token."""
        access_token = "xoxb-test-token"
        client = get_slack_client(access_token)

        assert client is not None
        assert hasattr(client, "token")
        assert client.token == access_token

    @patch("engine.integrations.utils.requests.post")
    def test_refresh_slack_oauth_token_success(self, mock_post):
        """Test successful Slack OAuth token refresh."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            "ok": True,
            "access_token": "xoxb-new-access-token",
            "refresh_token": "xoxb-new-refresh-token",
            "expires_in": 3600,
        }
        mock_post.return_value = mock_response

        refresh_token = "xoxb-old-refresh-token"
        client_id = "test-client-id"
        client_secret = "test-client-secret"

        access_token, creation_timestamp = refresh_slack_oauth_token(refresh_token, client_id, client_secret)

        assert access_token == "xoxb-new-access-token"
        assert isinstance(creation_timestamp, datetime)
        assert creation_timestamp.tzinfo == timezone.utc

        # Verify the request was made correctly
        mock_post.assert_called_once_with(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
        )

    @patch("engine.integrations.utils.requests.post")
    def test_refresh_slack_oauth_token_api_error(self, mock_post):
        """Test Slack OAuth token refresh with API error."""
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {"ok": False, "error": "invalid_refresh_token"}
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Slack API error: invalid_refresh_token"):
            refresh_slack_oauth_token("invalid-token", "client-id", "client-secret")

    @patch("engine.integrations.utils.requests.post")
    def test_refresh_slack_oauth_token_http_error(self, mock_post):
        """Test Slack OAuth token refresh with HTTP error."""
        mock_response = Mock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="Failed to refresh Slack token: 500 Internal Server Error"):
            refresh_slack_oauth_token("refresh-token", "client-id", "client-secret")

    

    def test_needs_new_token_fresh_token(self):
        """Test token freshness check with valid token."""
        # Create a token that expires in 1 hour
        now = datetime.now(timezone.utc)
        token_last_updated = now - timedelta(hours=1)
        expires_in = 7200  # 2 hours

        mock_integration = Mock()
        mock_integration.token_last_updated = token_last_updated
        mock_integration.expires_in = expires_in

        assert not needs_new_token(mock_integration)

    def test_needs_new_token_expired_token(self):
        """Test token freshness check with expired token."""
        # Create a token that expired 1 hour ago
        now = datetime.now(timezone.utc)
        token_last_updated = now - timedelta(hours=3)
        expires_in = 3600  # 1 hour

        mock_integration = Mock()
        mock_integration.token_last_updated = token_last_updated
        mock_integration.expires_in = expires_in

        assert needs_new_token(mock_integration)

    def test_needs_new_token_near_expiry(self):
        """Test token freshness check with token near expiry (within 2 minute buffer)."""
        # Create a token that expires in 1 minute
        now = datetime.now(timezone.utc)
        token_last_updated = now - timedelta(hours=1)
        expires_in = 3660  # 1 hour + 1 minute

        mock_integration = Mock()
        mock_integration.token_last_updated = token_last_updated
        mock_integration.expires_in = expires_in

        assert needs_new_token(mock_integration)

    def test_needs_new_token_missing_timestamp(self):
        """Test token freshness check with missing timestamp."""
        mock_integration = Mock()
        mock_integration.token_last_updated = None
        mock_integration.expires_in = 3600

        assert needs_new_token(mock_integration)

    def test_needs_new_token_missing_expiry(self):
        """Test token freshness check with missing expiry."""
        mock_integration = Mock()
        mock_integration.token_last_updated = datetime.now(timezone.utc)
        mock_integration.expires_in = None

        assert needs_new_token(mock_integration)


class TestSlackOAuthAccessToken:
    """Test suite for get_slack_oauth_access_token function."""

    @patch("engine.integrations.utils.get_integration_secret")
    @patch("engine.integrations.utils.refresh_slack_oauth_token")
    @patch("engine.integrations.utils.update_integration_secret")
    def test_get_slack_oauth_access_token_refresh_needed(self, mock_update, mock_refresh, mock_get_secret):
        """Test getting access token when refresh is needed."""
        # Mock integration secret that needs refresh
        mock_integration = Mock()
        mock_integration.get_refresh_token.return_value = "xoxb-refresh-token"
        mock_get_secret.return_value = mock_integration

        # Mock refresh function
        mock_refresh.return_value = ("xoxb-new-access-token", datetime.now(timezone.utc))

        # Mock needs_new_token to return True
        with patch("engine.integrations.utils.needs_new_token", return_value=True):
            access_token = get_slack_oauth_access_token(
                session=Mock(),
                integration_secret_id=UUID("12345678-1234-5678-1234-567812345678"),
                slack_client_id="test-client-id",
                slack_client_secret="test-client-secret",
            )

        assert access_token == "xoxb-new-access-token"
        mock_refresh.assert_called_once()
        mock_update.assert_called_once()

    @patch("engine.integrations.utils.get_integration_secret")
    def test_get_slack_oauth_access_token_no_refresh_needed(self, mock_get_secret):
        """Test getting access token when no refresh is needed."""
        # Mock integration secret that doesn't need refresh
        mock_integration = Mock()
        mock_integration.get_access_token.return_value = "xoxb-current-access-token"
        mock_get_secret.return_value = mock_integration

        # Mock needs_new_token to return False
        with patch("engine.integrations.utils.needs_new_token", return_value=False):
            access_token = get_slack_oauth_access_token(
                session=Mock(),
                integration_secret_id=UUID("12345678-1234-5678-1234-567812345678"),
                slack_client_id="test-client-id",
                slack_client_secret="test-client-secret",
            )

        assert access_token == "xoxb-current-access-token"

    @patch("engine.integrations.utils.get_integration_secret")
    def test_get_slack_oauth_access_token_not_found(self, mock_get_secret):
        """Test getting access token when integration secret is not found."""
        mock_get_secret.return_value = None

        with pytest.raises(
            ValueError, match="Integration secret with ID 12345678-1234-5678-1234-567812345678 not found."
        ):
            get_slack_oauth_access_token(
                session=Mock(),
                integration_secret_id=UUID("12345678-1234-5678-1234-567812345678"),
                slack_client_id="test-client-id",
                slack_client_secret="test-client-secret",
            )
