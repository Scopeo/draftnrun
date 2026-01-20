import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ada_backend.database.models import Webhook, WebhookProvider
from ada_backend.repositories.webhook_repository import get_webhook_by_external_client_id
from ada_backend.services.webhooks.errors import (
    WebhookEmptyTokenError,
    WebhookEventIdNotFoundError,
    WebhookNotFoundError,
)

LOGGER = logging.getLogger(__name__)


def get_aircall_webhook_service(session: Session, token: str) -> Optional[Webhook]:
    if not token:
        raise WebhookEmptyTokenError(provider=WebhookProvider.AIRCALL)

    webhook = get_webhook_by_external_client_id(session, WebhookProvider.AIRCALL, token)

    if not webhook:
        raise WebhookNotFoundError(provider=WebhookProvider.AIRCALL, external_client_id=token)
    return webhook


def get_aircall_event_id(payload: Dict[str, Any]) -> str:
    data = payload.get("data", {}) or {}
    event_id = data.get("id") or data.get("message_id")
    if not event_id:
        event_id = payload.get("id") or payload.get("event_id")
    if not event_id:
        raise WebhookEventIdNotFoundError(provider=WebhookProvider.AIRCALL, payload=payload)
    return str(event_id)
