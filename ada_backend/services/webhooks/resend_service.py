import ast
import base64
import hashlib
import hmac
import logging
from typing import Any, Dict, Optional

import httpx
from sqlalchemy.orm import Session

from ada_backend.database.models import Webhook, WebhookProvider
from ada_backend.services.webhooks.errors import (
    WebhookEventIdNotFoundError,
    WebhookNotFoundError,
)

LOGGER = logging.getLogger(__name__)


def _parse_data_field(data: Any) -> Dict[str, Any]:
    """
    Parse data field from webhook payload.
    Handles case where data might be a string due to repr() serialization in worker.

    Args:
        data: Data field from webhook payload (dict or string)

    Returns:
        Parsed dict, or empty dict if parsing fails
    """
    if isinstance(data, str):
        try:
            return ast.literal_eval(data)
        except (ValueError, SyntaxError) as e:
            LOGGER.warning(f"Failed to parse data field from string: {e}")
            return {}
    return data if isinstance(data, dict) else {}


class WebhookSignatureVerificationError(Exception):
    """Raised when Svix signature verification fails."""

    def __init__(self, message: str = "Invalid Svix signature"):
        self.message = message
        super().__init__(self.message)


def get_resend_webhook_service(session: Session) -> Optional[Webhook]:
    """
    Get the Resend webhook configuration.
    Currently supports single webhook per system (MVP).
    TODO: Add support for multiple webhooks (e.g., by recipient domain or custom identifier).
    """
    webhook = session.query(Webhook).filter(Webhook.provider == WebhookProvider.RESEND).first()

    if not webhook:
        raise WebhookNotFoundError(provider=WebhookProvider.RESEND, external_client_id="N/A")
    return webhook


def get_resend_event_id(payload: Dict[str, Any]) -> str:
    data = _parse_data_field(payload.get("data", {}) or {})

    event_id = data.get("email_id") or data.get("id") or payload.get("id") or payload.get("event_id")
    if not event_id:
        raise WebhookEventIdNotFoundError(provider=WebhookProvider.RESEND, payload=payload)
    return str(event_id)


def _timing_safe_equal(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    if len(a) != len(b):
        return False
    result = 0
    for x, y in zip(a.encode(), b.encode()):
        result |= x ^ y
    return result == 0


def _hmac_sha256_base64(secret: str, message: str) -> str:
    """
    Compute HMAC-SHA256 and return base64-encoded result.
    Handles Svix secrets that start with 'whsec_' prefix.
    """
    if secret.startswith("whsec_"):
        key_bytes = base64.b64decode(secret[6:])
    else:
        key_bytes = secret.encode()

    signature = hmac.new(key_bytes, message.encode(), hashlib.sha256).digest()
    return base64.b64encode(signature).decode()


def verify_svix_signature(headers: Dict[str, str], raw_body: bytes, signing_secret: str) -> None:
    """
    Verify Svix webhook signature.

    Args:
        headers: Request headers (case-insensitive dict)
        raw_body: Raw request body bytes
        signing_secret: Webhook signing secret (starts with whsec_)

    Raises:
        WebhookSignatureVerificationError: If signature verification fails
    """
    svix_id = headers.get("svix-id") or headers.get("Svix-Id") or ""
    svix_timestamp = headers.get("svix-timestamp") or headers.get("Svix-Timestamp") or ""
    svix_signature = headers.get("svix-signature") or headers.get("Svix-Signature") or ""

    if not svix_id or not svix_timestamp or not svix_signature:
        missing = []
        if not svix_id:
            missing.append("svix-id")
        if not svix_timestamp:
            missing.append("svix-timestamp")
        if not svix_signature:
            missing.append("svix-signature")
        raise WebhookSignatureVerificationError(f"Missing Svix headers: {', '.join(missing)}")

    message = f"{svix_id}.{svix_timestamp}.{raw_body.decode('utf-8')}"
    expected_signature = _hmac_sha256_base64(signing_secret, message)

    signatures = []
    for part in svix_signature.replace(",", " ").split():
        part = part.strip()
        if part:
            signatures.append(part)

    signature_valid = any(_timing_safe_equal(sig, expected_signature) for sig in signatures)

    if not signature_valid:
        LOGGER.error(
            f"Svix signature verification failed. Expected one of the signatures to match. "
            f"Received {len(signatures)} signature(s)"
        )
        raise WebhookSignatureVerificationError("Invalid Svix signature")

    LOGGER.info(f"Svix signature verified successfully for event {svix_id}")


def fetch_resend_email_content(email_id: str) -> Dict[str, Any]:
    """
    Fetch full email content from Resend API.

    Args:
        email_id: Email ID from webhook payload

    Returns:
        Email data dict with subject, from, to, text, html

    Raises:
        ValueError: If RESEND_API_KEY not set
        httpx.HTTPStatusError: If API call fails
    """
    from settings import settings

    if not settings.RESEND_API_KEY:
        raise ValueError("RESEND_API_KEY not set in environment")

    url = f"https://api.resend.com/emails/receiving/{email_id}"

    with httpx.Client() as client:
        response = client.get(
            url,
            headers={
                "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                "Accept": "application/json",
            },
            timeout=10,
        )

        if response.status_code != 200:
            error_body = response.text
            LOGGER.error(
                f"Resend API error fetching email {email_id}: "
                f"status={response.status_code}, response={error_body}"
            )

        response.raise_for_status()
        return response.json()


def prepare_resend_workflow_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform Resend webhook payload into workflow input format.
    Fetches full email content from Resend API and formats fields.

    Args:
        payload: Raw webhook payload from Resend

    Returns:
        Dict with formatted email data (subject, from, text, html)

    Raises:
        ValueError: If email_id not found in payload
        httpx.HTTPStatusError: If API call fails
    """
    # Extract email ID from payload
    data = _parse_data_field(payload.get("data", {}) or {})

    email_id = data.get("email_id") or data.get("id") or payload.get("id")

    if not email_id:
        LOGGER.error("No email ID found in Resend webhook payload")
        raise ValueError("Missing email ID in Resend webhook payload")

    LOGGER.info(f"Fetching email content for {email_id}")
    api_content = fetch_resend_email_content(email_id)

    # Extract fields from API response
    subject = api_content.get("subject") or "(no subject)"
    from_field = api_content.get("from") or "(unknown)"
    to_field = api_content.get("to", [])
    cc_field = api_content.get("cc", [])
    bcc_field = api_content.get("bcc", [])
    reply_to_field = api_content.get("reply_to", [])
    text = api_content.get("text") or ""
    html = api_content.get("html") or ""
    attachments = api_content.get("attachments", [])

    # Handle from field (can be string or object)
    if isinstance(from_field, dict):
        from_email = from_field.get("email") or from_field.get("address") or str(from_field)
    else:
        from_email = str(from_field)

    # Handle to field (array of email addresses)
    if isinstance(to_field, list):
        to_emails = [email if isinstance(email, str) else email.get("email", str(email)) for email in to_field]
    else:
        to_emails = [str(to_field)] if to_field else []

    # Handle cc field
    if isinstance(cc_field, list):
        cc_emails = [email if isinstance(email, str) else email.get("email", str(email)) for email in cc_field]
    else:
        cc_emails = [str(cc_field)] if cc_field else []

    # Handle bcc field
    if isinstance(bcc_field, list):
        bcc_emails = [email if isinstance(email, str) else email.get("email", str(email)) for email in bcc_field]
    else:
        bcc_emails = [str(bcc_field)] if bcc_field else []

    # Handle reply_to field
    if isinstance(reply_to_field, list):
        reply_to_emails = [
            email if isinstance(email, str) else email.get("email", str(email)) for email in reply_to_field
        ]
    else:
        reply_to_emails = [str(reply_to_field)] if reply_to_field else []

    LOGGER.info("Successfully fetched and formatted email content from API")

    return {
        "subject": subject,
        "from": from_email,
        "to": to_emails,
        "cc": cc_emails,
        "bcc": bcc_emails,
        "reply_to": reply_to_emails,
        "text": text,
        "html": html,
        "attachments": attachments,
    }
