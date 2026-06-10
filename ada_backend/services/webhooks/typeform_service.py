import base64
import hashlib
import hmac
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import Webhook, WebhookProvider
from ada_backend.repositories.webhook_repository import get_webhook_by_id_and_provider
from ada_backend.services.webhooks.errors import (
    WebhookConfigurationError,
    WebhookEventIdNotFoundError,
    WebhookNotFoundError,
    WebhookSignatureVerificationError,
)


def get_typeform_webhook_service(session: Session, webhook_id: UUID) -> Webhook:
    webhook = get_webhook_by_id_and_provider(session, webhook_id, WebhookProvider.TYPEFORM)
    if not webhook:
        raise WebhookNotFoundError(provider=WebhookProvider.TYPEFORM, external_client_id=str(webhook_id))
    if not webhook.get_signing_secret():
        raise WebhookConfigurationError(
            provider=WebhookProvider.TYPEFORM,
            message=f"Webhook {webhook_id} has no signing secret configured",
        )
    return webhook


def get_typeform_event_id(payload: Dict[str, Any]) -> str:
    form_response = payload.get("form_response") or {}
    event_id = payload.get("event_id") or form_response.get("token")
    if not event_id:
        raise WebhookEventIdNotFoundError(provider=WebhookProvider.TYPEFORM, payload=payload)
    return str(event_id)


def verify_typeform_signature(headers: Dict[str, str], raw_body: bytes, signing_secret: str) -> None:
    received_signature = headers.get("typeform-signature")
    if not received_signature:
        raise WebhookSignatureVerificationError("Missing Typeform-Signature header")

    try:
        algorithm, signature = received_signature.split("=", 1)
    except ValueError as e:
        raise WebhookSignatureVerificationError("Malformed Typeform-Signature header") from e

    if algorithm != "sha256" or not signature:
        raise WebhookSignatureVerificationError("Unsupported Typeform signature algorithm")

    digest = hmac.new(signing_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    expected_signature = base64.b64encode(digest).decode()
    if not hmac.compare_digest(signature, expected_signature):
        raise WebhookSignatureVerificationError("Invalid Typeform signature")
