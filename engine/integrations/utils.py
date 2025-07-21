from uuid import UUID
from datetime import datetime, timedelta, timezone
import requests
import logging

from sqlalchemy.orm import Session
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


from ada_backend.repositories.integration_repository import get_integration_secret, update_integration_secret
from ada_backend.database import models as db

LOGGER = logging.getLogger(__name__)


def needs_new_token(integration_secret: db.SecretIntegration) -> bool:
    if integration_secret.token_last_updated is None or integration_secret.expires_in is None:
        # If we don't know the current token or expiration, assume we need a new one
        return True
    expiration_time = integration_secret.token_last_updated + timedelta(seconds=integration_secret.expires_in)
    now = datetime.now(timezone.utc)
    buffer = timedelta(minutes=2)
    if now >= (expiration_time - buffer):
        return True

    return False


def get_gmail_sender_service(access_token: str):
    creds = Credentials(token=access_token)
    service = build("gmail", "v1", credentials=creds)
    return service


def get_google_user_email(access_token: str) -> str:
    url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers)

    if resp.ok:
        user_info = resp.json()
        print(user_info)
        return user_info.get("email")
    else:
        raise ValueError(f"Failed to fetch user info: {resp.status_code} {resp.text}")


def refresh_oauth_token(refresh_token: str, client_id: str, client_secret: str) -> tuple[str, str]:
    url = "https://www.googleapis.com/oauth2/v3/token"
    print("refresh_token", refresh_token)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(url, data=payload)
    print("resp", resp)
    if resp.ok:
        tokens = resp.json()
        return tokens.get("access_token"), tokens.get("refresh_token")
    else:
        raise ValueError(f"Failed to refresh token: {resp.status_code} {resp.text}")


def get_oauth_access_token(
    session: Session,
    integration_secret_id: UUID,
    google_client_id: str,
    google_client_secret: str,
) -> None:

    integration_secret = get_integration_secret(session, integration_secret_id)
    if integration_secret:
        # If the token is expired or needs to be refreshed
        if needs_new_token(integration_secret):
            refresh_token = integration_secret.get_refresh_token()
            new_access_token, new_refresh_token = refresh_oauth_token(
                refresh_token, google_client_id, google_client_secret
            )
            update_integration_secret(session, integration_secret.id, new_access_token, new_refresh_token)
            return new_access_token
        else:
            return integration_secret.get_access_token()
