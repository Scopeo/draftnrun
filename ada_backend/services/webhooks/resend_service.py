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
    WebhookConfigurationError,
    WebhookEventIdNotFoundError,
    WebhookInvalidParameterError,
    WebhookNotFoundError,
    WebhookSignatureVerificationError,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


def _parse_data_field(data: Any) -> Dict[str, Any]:
    if isinstance(data, str):
        try:
            return ast.literal_eval(data)
        except (ValueError, SyntaxError) as e:
            LOGGER.warning(f"Failed to parse data field from string: {e}")
            return {}
    return data if isinstance(data, dict) else {}


def get_resend_webhook_service(session: Session) -> Optional[Webhook]:
    """
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
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    required = {
        "svix-id": svix_id,
        "svix-timestamp": svix_timestamp,
        "svix-signature": svix_signature,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise WebhookSignatureVerificationError(f"Missing Svix headers: {', '.join(missing)}")

    message = f"{svix_id}.{svix_timestamp}.{raw_body.decode('utf-8')}"
    expected_signature = _hmac_sha256_base64(signing_secret, message)

    signatures = svix_signature.replace(",", " ").split()

    signature_valid = any(_timing_safe_equal(sig, expected_signature) for sig in signatures)

    if not signature_valid:
        LOGGER.error(
            f"Svix signature verification failed. Expected one of the signatures to match. "
            f"Received {len(signatures)} signature(s)"
        )
        raise WebhookSignatureVerificationError("Invalid Svix signature")

    LOGGER.info(f"Svix signature verified successfully for event {svix_id}")


def _normalize_email_list(field: Any) -> list[str]:
    if isinstance(field, list):
        return [email if isinstance(email, str) else email.get("email", str(email)) for email in field]
    return [str(field)] if field else []


def fetch_resend_email_content(email_id: str) -> Dict[str, Any]:
    if not settings.RESEND_API_KEY:
        raise WebhookConfigurationError(
            provider=WebhookProvider.RESEND,
            message="RESEND_API_KEY not set in environment"
        )

    url = f"https://api.resend.com/emails/receiving/{email_id}"

    try:
        with httpx.Client() as client:
            response = client.get(
                url,
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Accept": "application/json",
                },
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        LOGGER.error(
            f"Resend API error fetching email {email_id}: "
            f"status={e.response.status_code}, response={e.response.text}"
        )
        raise
    except httpx.RequestError as e:
        LOGGER.error(f"Resend API request error for email {email_id}: {str(e)}")
        raise


def prepare_resend_workflow_input(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = _parse_data_field(payload.get("data", {}) or {})
    email_id = data.get("email_id") or data.get("id") or payload.get("id")

    if not email_id:
        LOGGER.error("No email ID found in Resend webhook payload")
        raise WebhookInvalidParameterError(
            parameter="email_id",
            value="",
            reason="email_id not found in Resend webhook payload"
        )

    LOGGER.info(f"Fetching email content for {email_id}")
    api_content = fetch_resend_email_content(email_id)

    subject = api_content.get("subject") or "(no subject)"
    from_field = api_content.get("from") or "(unknown)"
    to_field = api_content.get("to", [])
    cc_field = api_content.get("cc", [])
    bcc_field = api_content.get("bcc", [])
    reply_to_field = api_content.get("reply_to", [])
    text = api_content.get("text") or ""
    html = api_content.get("html") or ""
    attachments = api_content.get("attachments", [])

    if isinstance(from_field, dict):
        from_email = from_field.get("email") or from_field.get("address") or str(from_field)
    else:
        from_email = str(from_field)

    to_emails = _normalize_email_list(to_field)
    cc_emails = _normalize_email_list(cc_field)
    bcc_emails = _normalize_email_list(bcc_field)
    reply_to_emails = _normalize_email_list(reply_to_field)

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
