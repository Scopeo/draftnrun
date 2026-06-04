import base64
import logging
import mimetypes
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from engine.integrations.outlook.errors import AttachmentNotFoundError, AttachmentPathError, AttachmentTooLargeError
from engine.integrations.utils import (
    AttachmentInput,
    EmailAttachment,
    download_to_local,
    get_attachment_filename,
    get_attachment_source,
    is_url,
)
from engine.temps_folder_utils import get_output_dir

LOGGER = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"

_INLINE_ATTACHMENT_LIMIT_BYTES = 3 * 1024 * 1024  # 3 MB — Graph API inline attachment limit


def _ensure_paths(attachments: Optional[Iterable[AttachmentInput]]) -> list[tuple[Path, str]]:
    output_dir = get_output_dir().resolve()
    if not attachments:
        return []
    paths: list[tuple[Path, str]] = []
    for attachment in attachments:
        source = get_attachment_source(attachment)
        if is_url(source):
            filename = (
                get_attachment_filename(attachment, Path(source)) if isinstance(attachment, EmailAttachment) else None
            )
            local_path = download_to_local(
                source,
                output_dir,
                filename,
            ).resolve()
        else:
            attachment_path = Path(source)
            if attachment_path.is_absolute():
                local_path = attachment_path.resolve()
            else:
                local_path = (output_dir / attachment_path).resolve()
            if not local_path.is_relative_to(output_dir):
                raise AttachmentPathError(source)
        if not local_path.is_file():
            raise AttachmentNotFoundError(str(local_path))
        paths.append((local_path, get_attachment_filename(attachment, local_path)))
    return paths


def _build_recipients(emails: Optional[list[str]]) -> list[dict[str, Any]]:
    if not emails:
        return []
    return [{"emailAddress": {"address": addr}} for addr in emails]


def _build_attachments(attachments: Optional[Iterable[AttachmentInput]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for path, filename in _ensure_paths(attachments):
        file_size = path.stat().st_size
        if file_size >= _INLINE_ATTACHMENT_LIMIT_BYTES:
            raise AttachmentTooLargeError(filename, file_size, _INLINE_ATTACHMENT_LIMIT_BYTES)
        mime, _ = mimetypes.guess_type(filename)
        content_type = mime or "application/octet-stream"
        data = path.read_bytes()
        result.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": filename,
            "contentType": content_type,
            "contentBytes": base64.b64encode(data).decode(),
        })
    return result


def build_graph_mail_payload(
    subject: str,
    body: Optional[str] = None,
    recipients: Optional[list[str]] = None,
    cc: Optional[list[str]] = None,
    bcc: Optional[list[str]] = None,
    attachments: Optional[Iterable[AttachmentInput]] = None,
    html_body: Optional[str] = None,
) -> dict[str, Any]:
    """Build a Microsoft Graph API message resource JSON payload."""
    if html_body:
        body_payload = {"contentType": "HTML", "content": html_body}
    else:
        body_payload = {"contentType": "Text", "content": body}
    message: dict[str, Any] = {
        "subject": subject,
        "body": body_payload,
        "toRecipients": _build_recipients(recipients),
        "ccRecipients": _build_recipients(cc),
        "bccRecipients": _build_recipients(bcc),
    }

    file_attachments = _build_attachments(attachments)
    if file_attachments:
        message["attachments"] = file_attachments

    return message


def get_outlook_user_email(access_token: str) -> str:
    """Fetch the authenticated user's email address from Microsoft Graph (sync)."""
    response = httpx.get(
        f"{GRAPH_API_BASE}/me",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"$select": "mail,userPrincipalName"},
        timeout=10.0,
    )
    response.raise_for_status()
    data = response.json()
    email = data.get("mail") or data.get("userPrincipalName")
    if not email:
        raise RuntimeError("Could not determine Outlook user email address")
    return email
