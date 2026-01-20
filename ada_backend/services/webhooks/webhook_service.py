import logging
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm.session import Session

from ada_backend.database.models import Webhook, WebhookProvider
from ada_backend.repositories.webhook_repository import get_enabled_webhook_triggers
from ada_backend.schemas.webhook_schema import (
    IntegrationTriggerResponse,
    WebhookProcessingResponseSchema,
    WebhookProcessingStatus,
)
from ada_backend.services.webhooks.aircall_service import get_aircall_event_id
from ada_backend.services.webhooks.errors import (
    WebhookEventIdNotFoundError,
    WebhookProcessingError,
    WebhookQueueError,
)
from ada_backend.utils.redis_client import (
    check_and_set_webhook_event,
    push_webhook_event,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


def get_webhook_event_id(payload: Dict[str, Any], provider: WebhookProvider) -> str:
    if provider == WebhookProvider.AIRCALL:
        return get_aircall_event_id(payload)
    else:
        LOGGER.error(f"Webhook event id not found for provider: {provider}")
        raise WebhookEventIdNotFoundError(provider=provider, payload=payload)


async def process_webhook_event(
    provider: WebhookProvider,
    payload: Dict[str, Any],
    webhook: Webhook,
) -> WebhookProcessingResponseSchema:
    try:
        event_id = get_webhook_event_id(payload, provider)
        provider_value = provider.value

        is_new = check_and_set_webhook_event(provider_value, event_id, ttl=settings.REDIS_WEBHOOK_DEDUP_TTL)
        if not is_new:
            LOGGER.info(
                f"Duplicate {provider_value} webhook event detected: event_id={event_id}, webhook_id={webhook.id}"
            )
            return WebhookProcessingResponseSchema(
                status=WebhookProcessingStatus.DUPLICATE, processed=False, event_id=event_id
            )

        LOGGER.info(f"{provider_value} webhook event validated: event_id={event_id}, webhook_id={webhook.id}")

        queued = push_webhook_event(
            webhook_id=webhook.id,
            provider=provider_value,
            payload=payload,
            event_id=event_id,
            organization_id=webhook.organization_id,
        )

        if not queued:
            LOGGER.error(
                f"Failed to queue {provider_value} webhook event: event_id={event_id}, webhook_id={webhook.id}"
            )
            raise WebhookQueueError(webhook=webhook, event_id=event_id)

        LOGGER.info(
            f"{provider_value} webhook event queued for processing: event_id={event_id}, webhook_id={webhook.id}"
        )

        return WebhookProcessingResponseSchema(
            status=WebhookProcessingStatus.RECEIVED, processed=False, event_id=event_id
        )

    except WebhookQueueError as e:
        raise e
    except Exception as e:
        LOGGER.error(f"Error processing {provider.value} webhook: {str(e)}", exc_info=True)
        raise WebhookProcessingError(webhook=webhook, error=e)


def get_webhook_triggers_service(session: Session, webhook_id: UUID) -> List[IntegrationTriggerResponse]:
    triggers = get_enabled_webhook_triggers(session=session, webhook_id=webhook_id)

    return [
        IntegrationTriggerResponse(
            id=str(trigger.id),
            webhook_id=str(trigger.webhook_id),
            project_id=str(trigger.project_id),
            events=trigger.events,
            filter_options=trigger.filter_options,
        )
        for trigger in triggers
    ]
