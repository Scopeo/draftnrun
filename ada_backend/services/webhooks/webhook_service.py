import json
import logging
from typing import Any, Dict, List
from uuid import UUID

from sqlalchemy.orm.session import Session

from ada_backend.database.models import CallType, EnvType, Webhook, WebhookProvider
from ada_backend.repositories.webhook_repository import get_enabled_webhook_triggers
from ada_backend.schemas.webhook_schema import (
    FilterExpression,
    FilterOperator,
    IntegrationTriggerResponse,
    LogicalOperator,
    WebhookExecuteResponse,
    WebhookExecuteResult,
    WebhookProcessingResponseSchema,
    WebhookProcessingStatus,
)
from ada_backend.services.agent_runner_service import run_env_agent
from ada_backend.services.errors import EnvironmentNotFound, MissingDataSourceError, MissingIntegrationError
from ada_backend.services.webhooks.aircall_service import get_aircall_event_id
from ada_backend.services.webhooks.errors import (
    WebhookEventIdNotFoundError,
    WebhookProcessingError,
    WebhookQueueError,
)
from ada_backend.services.webhooks.resend_service import (
    get_resend_event_id,
    prepare_resend_workflow_input,
)
from ada_backend.utils.redis_client import (
    check_and_set_webhook_event,
    push_webhook_event,
)
from settings import settings

LOGGER = logging.getLogger(__name__)


def evaluate_filter(filter_data: Dict[str, Any], webhook_data: Dict[str, Any]) -> bool:
    if not filter_data:
        return True

    try:
        filter_expr = FilterExpression(**filter_data)
    except Exception as e:
        LOGGER.error(f"Invalid filter format: {e}, filter_data: {filter_data}")
        return False

    results = []
    for condition in filter_expr.conditions:
        field_value = webhook_data.get(condition.field)

        if condition.operator == FilterOperator.EQUALS:
            results.append(field_value == condition.value)

        elif condition.operator == FilterOperator.CONTAINS:
            if isinstance(field_value, list):
                normalized = [str(v).lower().strip() for v in field_value]
                target = str(condition.value).lower().strip()
                results.append(target in normalized)
            elif isinstance(field_value, str):
                results.append(str(condition.value).lower() in field_value.lower())
            else:
                results.append(False)

    if filter_expr.operator == LogicalOperator.OR:
        return any(results)
    elif filter_expr.operator == LogicalOperator.AND:
        return all(results)


def get_webhook_event_id(payload: Dict[str, Any], provider: WebhookProvider) -> str:
    if provider == WebhookProvider.AIRCALL:
        return get_aircall_event_id(payload)
    elif provider == WebhookProvider.RESEND:
        return get_resend_event_id(payload)
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


def prepare_workflow_input(payload: Dict[str, Any], provider: str) -> Dict[str, Any]:
    provider_enum = WebhookProvider(provider)
    LOGGER.info(f"Preparing workflow input for provider: {provider_enum}")
    match provider_enum:
        case WebhookProvider.RESEND:
            return prepare_resend_workflow_input(payload)
        case _:
            return {
                "messages": [
                    {"role": "user", "content": json.dumps(payload, default=str)},
                ],
                "webhook_payload": payload,
            }


def get_webhook_triggers_service(
    session: Session, webhook_id: UUID, provider: str = None, event_data: Dict[str, Any] = None
) -> List[IntegrationTriggerResponse]:
    triggers = get_enabled_webhook_triggers(session=session, webhook_id=webhook_id)
    if not triggers:
        LOGGER.info(f"No enabled triggers for webhook {webhook_id}, skipping execute")
        return []

    trigger_responses = [
        IntegrationTriggerResponse(
            id=str(trigger.id),
            webhook_id=str(trigger.webhook_id),
            project_id=str(trigger.project_id),
            events=trigger.events,
            filter_options=trigger.filter_options,
        )
        for trigger in triggers
    ]

    if provider == WebhookProvider.RESEND and event_data:
        data = event_data.get("data", {})
        filtered = [t for t in trigger_responses if evaluate_filter(t.filter_options, data)]
        LOGGER.info(f"Filtered triggers: {len(filtered)}/{len(trigger_responses)}")
        return filtered

    return trigger_responses


async def execute_webhook(
    session: Session,
    webhook_id: UUID,
    provider: str,
    event_id: str,
    payload: Dict[str, Any],
) -> WebhookExecuteResponse:
    """
    Get triggers for the webhook, prepare workflow input (provider-specific),
    and run the workflow for each trigger.
    """
    triggers = get_webhook_triggers_service(
        session=session,
        webhook_id=webhook_id,
        provider=provider,
        event_data=payload,
    )

    if len(triggers) == 0:
        return WebhookExecuteResponse(processed=0, total=0, results=[])

    workflow_input = prepare_workflow_input(payload, provider)
    input_base = {
        **workflow_input,
        "event_id": event_id,
        "provider": provider,
    }

    out: List[WebhookExecuteResult] = []
    for trigger in triggers:
        try:
            r = await _run_trigger(session, trigger, input_base)
            out.append(r)
        except Exception as e:
            LOGGER.exception("Unexpected error in execute_webhook", exc_info=e)
            out.append(
                WebhookExecuteResult(
                    trigger_id=trigger.id,
                    project_id=trigger.project_id,
                    success=False,
                    error=str(e),
                )
            )

    processed = sum(1 for r in out if r.success)
    return WebhookExecuteResponse(
        processed=processed,
        total=len(triggers),
        results=out,
    )


async def _run_trigger(
    session: Session,
    trigger: IntegrationTriggerResponse,
    input_base: Dict[str, Any],
) -> WebhookExecuteResult:
    project_id = UUID(trigger.project_id)
    try:
        response = await run_env_agent(
            session=session,
            project_id=project_id,
            input_data=input_base,
            env=EnvType.PRODUCTION,
            call_type=CallType.API,
        )
        return WebhookExecuteResult(
            trigger_id=trigger.id,
            project_id=trigger.project_id,
            success=True,
            trace_id=response.trace_id,
        )
    except (EnvironmentNotFound, MissingDataSourceError, MissingIntegrationError) as e:
        LOGGER.warning(f"Trigger {trigger.id} run failed: {e}")
        return WebhookExecuteResult(
            trigger_id=trigger.id,
            project_id=trigger.project_id,
            success=False,
            error=str(e),
        )
    except Exception as e:
        LOGGER.exception(f"Trigger {trigger.id} run failed: {e}")
        return WebhookExecuteResult(
            trigger_id=trigger.id,
            project_id=trigger.project_id,
            success=False,
            error=str(e),
        )
