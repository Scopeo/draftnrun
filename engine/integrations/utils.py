import ipaddress
import json
import logging
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse
from uuid import UUID

import httpx
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from ada_backend.database import models as db
from ada_backend.repositories.integration_repository import get_integration_secret, update_integration_secret

LOGGER = logging.getLogger(__name__)

_DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_DOWNLOAD_REDIRECTS = 5
_DISALLOWED_DOWNLOAD_NETWORKS = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
)


def normalize_str_list(v: Any) -> Any:
    """Pydantic pre-validator helper: ensure a value destined for a list[str] field
    is actually a flat list of strings. Handles bare strings, nested lists, and
    non-string items."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        flattened: list[str] = []
        for item in v:
            if isinstance(item, list):
                flattened.extend(str(i) for i in item)
            else:
                flattened.append(str(item))
        return flattened
    return v


class EmailAttachment(BaseModel):
    url: str = ""
    path: str = ""
    filename: str

    @model_validator(mode="after")
    def validate_source(self) -> "EmailAttachment":
        self.url = self.url.strip()
        self.path = self.path.strip()
        self.filename = Path(self.filename.strip()).name
        if not self.url and not self.path:
            raise ValueError("Attachment must include either 'url' or 'path'.")
        if self.url and self.path:
            raise ValueError("Attachment must include exactly one of 'url' or 'path'.")
        if not self.filename:
            raise ValueError("Attachment must include a non-empty 'filename'.")
        return self


AttachmentInput = str | Path | EmailAttachment


def normalize_email_attachments(v: Any) -> Any:
    if v is None:
        return []
    if isinstance(v, str):
        stripped_value = v.strip()
        if stripped_value.startswith("["):
            v = json.loads(stripped_value)
        else:
            v = [v]
    if not isinstance(v, list):
        return v
    normalized: list[EmailAttachment] = []
    for attachment in v:
        if isinstance(attachment, EmailAttachment):
            normalized.append(attachment)
            continue
        if isinstance(attachment, dict):
            normalized.append(EmailAttachment.model_validate(attachment))
            continue
        source = str(attachment)
        filename = _infer_attachment_filename(source)
        if is_url(source):
            normalized.append(EmailAttachment(url=source, filename=filename))
        else:
            normalized.append(EmailAttachment(path=source, filename=filename))
    return normalized


def get_attachment_source(attachment: AttachmentInput) -> str:
    if isinstance(attachment, EmailAttachment):
        return attachment.url or attachment.path
    return str(attachment)


def get_attachment_filename(attachment: AttachmentInput, local_path: Path) -> str:
    if isinstance(attachment, EmailAttachment):
        return Path(attachment.filename).name
    return local_path.name


def is_url(value: str) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _infer_attachment_filename(source: str) -> str:
    if is_url(source):
        parsed = urlparse(source)
        return Path(parsed.path).name or "attachment"
    return Path(source).name


def download_to_local(url: str, output_dir: Path, filename: str | None = None) -> Path:
    _validate_download_url(url)
    parsed = urlparse(url)
    resolved_filename = Path(filename).name if filename else Path(parsed.path).name or "attachment"
    path = output_dir / resolved_filename
    LOGGER.info("Downloading attachment from URL to %s", path)
    with httpx.Client(timeout=_DOWNLOAD_TIMEOUT, follow_redirects=False) as client:
        response = _open_validated_download_stream(client, url)
        try:
            response.raise_for_status()
            with path.open("wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
        finally:
            response.close()
    return path


def _open_validated_download_stream(client: httpx.Client, url: str) -> httpx.Response:
    current_url = url
    for redirect_count in range(_MAX_DOWNLOAD_REDIRECTS + 1):
        _validate_download_url(current_url)
        request_url, headers, sni_hostname = _build_validated_download_request(current_url)
        request = client.build_request("GET", request_url, headers=headers)
        if sni_hostname:
            request.extensions["sni_hostname"] = sni_hostname
        response = client.send(request, stream=True)
        if not response.is_redirect:
            return response
        location = response.headers.get("location")
        response.close()
        if not location:
            raise ValueError(f"Attachment download redirect missing Location header: {current_url}")
        if redirect_count == _MAX_DOWNLOAD_REDIRECTS:
            raise ValueError(f"Attachment download exceeded {_MAX_DOWNLOAD_REDIRECTS} redirects: {url}")
        current_url = urljoin(current_url, location)
    raise ValueError(f"Attachment download exceeded {_MAX_DOWNLOAD_REDIRECTS} redirects: {url}")


def _validate_download_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported attachment URL scheme: {parsed.scheme}")
    if parsed.username or parsed.password:
        raise ValueError("Attachment URLs must not contain credentials.")
    if not parsed.hostname:
        raise ValueError("Attachment URL must include a hostname.")


def _build_validated_download_request(url: str) -> tuple[str, dict[str, str], str | None]:
    parsed = urlparse(url)
    if not parsed.hostname:
        raise ValueError("Attachment URL must include a hostname.")
    ip = _resolve_download_ip(parsed.hostname, parsed.port)
    host = parsed.hostname if parsed.port is None else f"{parsed.hostname}:{parsed.port}"
    request_host = f"[{ip}]" if isinstance(ip, ipaddress.IPv6Address) else str(ip)
    port = f":{parsed.port}" if parsed.port is not None else ""
    path = parsed.path or "/"
    query = f"?{parsed.query}" if parsed.query else ""
    sni_hostname = parsed.hostname if parsed.scheme == "https" else None
    return f"{parsed.scheme}://{request_host}{port}{path}{query}", {"Host": host}, sni_hostname


def _resolve_download_ip(hostname: str, port: int | None = None) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        addr_infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise ValueError(f"Could not resolve attachment URL hostname: {hostname}") from error
    if not addr_infos:
        raise ValueError(f"Could not resolve attachment URL hostname: {hostname}")
    for addr_info in addr_infos:
        ip = ipaddress.ip_address(addr_info[4][0])
        if not _is_disallowed_download_ip(ip):
            return ip
    raise ValueError(f"Attachment URL resolves to a disallowed address: {addr_infos[0][4][0]}")


def _is_disallowed_download_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or any(ip in network for network in _DISALLOWED_DOWNLOAD_NETWORKS)
    )


# TODO: Delete after full migration to Nango
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


def get_google_service(api_name: str, version: str, access_token: str):
    creds = Credentials(token=access_token)
    return build(api_name, version, credentials=creds)


def get_gmail_sender_service(access_token: str):
    return get_google_service("gmail", "v1", access_token)


def get_google_calendar_service(access_token: str):
    return get_google_service("calendar", "v3", access_token)


def get_google_user_email(access_token: str) -> str:
    url = "https://gmail.googleapis.com/gmail/v1/users/me/profile"
    headers = {"Authorization": f"Bearer {access_token}"}

    resp = requests.get(url, headers=headers)

    if resp.ok:
        user_info = resp.json()
        return user_info.get("email")
    else:
        raise ValueError(f"Failed to fetch user info: {resp.status_code} {resp.text}")


def refresh_oauth_token(refresh_token: str, client_id: str, client_secret: str) -> tuple[str, datetime]:
    url = "https://oauth2.googleapis.com/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    resp = requests.post(url, data=payload)
    if resp.ok:
        creation_timestamp = datetime.now(timezone.utc)
        tokens = resp.json()
        return tokens.get("access_token"), creation_timestamp
    else:
        raise ValueError(f"Failed to refresh token: {resp.status_code} {resp.text}")


def get_oauth_access_token(
    session: Session,
    integration_secret_id: UUID,
    google_client_id: str,
    google_client_secret: str,
) -> str:
    integration_secret = get_integration_secret(session, integration_secret_id)
    if integration_secret:
        # If the token is expired or needs to be refreshed
        if needs_new_token(integration_secret):
            refresh_token = integration_secret.get_refresh_token()
            new_access_token, creation_timestamp = refresh_oauth_token(
                refresh_token, google_client_id, google_client_secret
            )
            update_integration_secret(
                session,
                integration_secret.id,
                new_access_token,
                refresh_token,
                token_last_updated=creation_timestamp,
            )
            return new_access_token
        else:
            return integration_secret.get_access_token()
    else:
        raise ValueError(f"Integration secret with ID {integration_secret_id} not found.")
