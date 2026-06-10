import hashlib
import json
import secrets
from typing import Any, Dict
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import IntegrationTrigger, Webhook, WebhookProvider
from ada_backend.repositories.project_repository import get_project
from ada_backend.schemas.webhook_schema import TypeformWebhookCreateResponse
from ada_backend.services.errors import ProjectNotFound
from ada_backend.services.webhooks.errors import WebhookConfigurationError
from settings import settings


def create_typeform_webhook_service(
    session: Session,
    project_id: UUID,
    events: Dict[str, Any] | None = None,
    filter_options: Dict[str, Any] | None = None,
    rotate_secret: bool = False,
) -> TypeformWebhookCreateResponse:
    project = get_project(session, project_id)
    if not project:
        raise ProjectNotFound(project_id)

    events_hash = _generate_events_hash(events)
    webhook = _get_typeform_webhook_for_project(session, project_id)
    secret_to_return: str | None = None

    if webhook is None:
        secret_to_return = _generate_signing_secret()
        webhook = Webhook(
            organization_id=project.organization_id,
            provider=WebhookProvider.TYPEFORM,
            external_client_id=f"typeform:{project_id}",
        )
        webhook.set_signing_secret(secret_to_return)
        session.add(webhook)
        session.flush()
    elif rotate_secret or not webhook.get_signing_secret():
        secret_to_return = _generate_signing_secret()
        webhook.set_signing_secret(secret_to_return)
        session.flush()

    trigger = _get_typeform_trigger(session, webhook.id, project_id, events_hash)
    if trigger is None:
        trigger = IntegrationTrigger(
            webhook_id=webhook.id,
            project_id=project_id,
            events=events,
            events_hash=events_hash,
            enabled=True,
            filter_options=filter_options,
        )
        session.add(trigger)
        session.flush()
    else:
        trigger.filter_options = filter_options
        trigger.enabled = True
        session.flush()

    session.commit()
    session.refresh(webhook)
    session.refresh(trigger)

    return TypeformWebhookCreateResponse(
        webhook_id=webhook.id,
        integration_trigger_id=trigger.id,
        callback_url=_build_typeform_callback_url(webhook.id),
        signing_secret=secret_to_return,
        secret_available=secret_to_return is not None,
    )


def _generate_events_hash(events: Dict[str, Any] | None) -> str:
    events_json = json.dumps(events or {}, sort_keys=True)
    return hashlib.sha256(events_json.encode()).hexdigest()


def _generate_signing_secret() -> str:
    return secrets.token_urlsafe(32)


def _get_typeform_webhook_for_project(session: Session, project_id: UUID) -> Webhook | None:
    return (
        session.query(Webhook)
        .join(IntegrationTrigger, IntegrationTrigger.webhook_id == Webhook.id)
        .filter(
            Webhook.provider == WebhookProvider.TYPEFORM,
            IntegrationTrigger.project_id == project_id,
        )
        .first()
    )


def _get_typeform_trigger(
    session: Session,
    webhook_id: UUID,
    project_id: UUID,
    events_hash: str,
) -> IntegrationTrigger | None:
    return (
        session.query(IntegrationTrigger)
        .filter(
            IntegrationTrigger.webhook_id == webhook_id,
            IntegrationTrigger.project_id == project_id,
            IntegrationTrigger.events_hash == events_hash,
        )
        .first()
    )


def _build_typeform_callback_url(webhook_id: UUID) -> str:
    if not settings.ADA_URL:
        raise WebhookConfigurationError(WebhookProvider.TYPEFORM, "ADA_URL is not configured")
    base_url = settings.ADA_URL
    return f"{base_url.rstrip('/')}/webhooks/typeform/{webhook_id}"
